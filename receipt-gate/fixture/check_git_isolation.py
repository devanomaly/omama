#!/usr/bin/env python3
"""Deterministic regression proof for orchestrator self-test Git isolation.

No Claude session is opened.  The check imports the shipped fixture runner and
orchestrator self-test by path, poisons the process environment with repository
routing and config injection aimed at a decoy repository, then drives the real
self-test setup helpers.  The decoy's Git database and CARD family must remain
byte-identical.
"""
import importlib.util
import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
RUN_FIXTURE = HERE / "run_fixture.py"
SELFTEST = HERE.parent / "adapt" / "selftest_orchestrator_close.py"
GIT_ROUTING = (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR", "GIT_NAMESPACE",
    "GIT_CEILING_DIRECTORIES", "GIT_DISCOVERY_ACROSS_FILESYSTEM",
    "GIT_CONFIG", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT",
    "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM")
GIT_CONFIG_PREFIXES = ("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot build an import spec for %s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def snapshot(root):
    """Every regular file below root, keyed by relative path and exact bytes."""
    result = {}
    for path in sorted(Path(root).rglob("*"), key=lambda item: item.as_posix()):
        if path.is_file():
            result[path.relative_to(root).as_posix()] = path.read_bytes()
    return result


def card_family(snap):
    return {name: body for name, body in snap.items()
            if Path(name).name.startswith("CARD.")}


def rmtree(root):
    def retry(func, path, _exc):
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except OSError:
            pass

    if sys.version_info >= (3, 12):
        shutil.rmtree(str(root), onexc=retry)
    else:
        shutil.rmtree(str(root), onerror=retry)


def main():
    if shutil.which("git") is None:
        print("NOT-RUN: git is not on PATH")
        return 2
    try:
        import yaml  # noqa: F401 -- prerequisite of the helper under test
    except ImportError:
        print("NOT-RUN: this interpreter lacks PyYAML")
        return 2

    fixture = load_module("omama_fixture_isolation_runner", RUN_FIXTURE)
    selftest = load_module("omama_fixture_isolation_selftest", SELFTEST)
    gate = load_module("omama_fixture_isolation_gate", HERE.parent / "receipt_gate.py")
    cross = load_module("omama_fixture_isolation_cross",
                        HERE.parent / "adapt" / "check_cross_repo.py")
    root = Path(tempfile.mkdtemp(prefix="omama-git-isolation-")).resolve()
    prior = dict(os.environ)
    failures = []
    try:
        # This literal oracle is independent of the production/helper tuples.
        # Equality alone cannot catch every copy losing the same name; the
        # gate fixture also has independent literal admission cases.
        for label, module in (("fixture", fixture), ("selftest", selftest),
                              ("gate", gate), ("cross-repo", cross)):
            if set(module.GIT_ROUTING) != set(GIT_ROUTING):
                failures.append("%s routing boundary differs from approved names" % label)
            if tuple(module.GIT_CONFIG_PREFIXES) != GIT_CONFIG_PREFIXES:
                failures.append("%s config prefixes differ from approved prefixes" % label)
        # Build the victim with the fixture's actual repository helper before
        # poisoning the environment.  Its Git database and durable CARD files
        # are the byte-level evidence boundary for the rest of this check.
        decoy = fixture.make_repo(root, "decoy")
        fixture.write_card(decoy)
        (decoy / "CARD.close").write_bytes(b"CLOSE\n")
        (decoy / "CARD.receipt.json").write_bytes(
            b'{"sentinel":"git-isolation"}\n')
        before = snapshot(decoy)

        scratch = root / "scratch"
        scratch.mkdir()
        second = root / "second"
        second.mkdir()
        poison = {
            "GIT_DIR": str(decoy / ".git"),
            "GIT_WORK_TREE": str(decoy),
            "GIT_INDEX_FILE": str(decoy / ".git" / "index"),
            "GIT_OBJECT_DIRECTORY": str(decoy / ".git" / "objects"),
            "GIT_ALTERNATE_OBJECT_DIRECTORIES": str(decoy / ".git" / "objects"),
            "GIT_COMMON_DIR": str(decoy / ".git"),
            "GIT_NAMESPACE": "isolation-poison",
            "GIT_CEILING_DIRECTORIES": str(root),
            "GIT_DISCOVERY_ACROSS_FILESYSTEM": "1",
            "GIT_CONFIG": str(decoy / ".git" / "config"),
            "GIT_CONFIG_PARAMETERS": "'core.worktree=%s'" % decoy.as_posix(),
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_GLOBAL": str(decoy / ".git" / "config"),
            "GIT_CONFIG_SYSTEM": str(decoy / ".git" / "config"),
            "GIT_CONFIG_KEY_0": "core.worktree",
            "GIT_CONFIG_VALUE_0": str(decoy),
            "OMAMA_CARD": str(decoy / "CARD.yaml"),
            # Unknown GIT_* variables are intentionally retained: isolation
            # is bounded to routing/config injection, not all Git behavior.
            "GIT_ISOLATION_UNRELATED": "must-survive",
        }
        if not set(GIT_ROUTING).issubset(poison):
            failures.append("poison omits an approved routing name")
        os.environ.update(poison)

        cleaned = selftest.scrubbed_env()
        exact = set(GIT_ROUTING)
        leaked = sorted(name for name in cleaned
                        if name.startswith("OMAMA_")
                        or name in exact
                        or name.startswith(GIT_CONFIG_PREFIXES))
        if leaked:
            failures.append("scrubbed_env retained routing/config keys: %s"
                            % ", ".join(leaked))
        if cleaned.get("GIT_ISOLATION_UNRELATED") != "must-survive":
            failures.append("scrubbed_env removed an unrelated GIT_* variable")

        try:
            fixture_repo = fixture.make_repo(root, "fixture-under-poison")
            fixture_head = fixture.git(
                fixture_repo, "rev-parse", "HEAD").stdout.strip()
            if not fixture_head:
                failures.append("fixture.git returned an empty scratch HEAD")
            # This path has its own explicit environment for a Git Bash probe;
            # on POSIX it must still let the gate reach its BAD-INPUT response.
            fixture.w_no_git_bash(root / "wiring-under-poison")
        except Exception as exc:  # noqa: BLE001 -- convert crashes to a named red
            failures.append("real fixture setup helpers failed under poison: %s: %s"
                            % (type(exc).__name__, exc))

        try:
            selftest.build_scratch(scratch)
            selftest.build_decoy(second)
            head = selftest.git(scratch, "rev-parse", "HEAD").strip()
            if not head:
                failures.append("selftest.git returned an empty scratch HEAD")
            probe = ("import json, os; "
                     "print(json.dumps(dict(os.environ), sort_keys=True))")
            timed_out, result = selftest.run_bounded(
                [sys.executable, "-c", probe], scratch, 30)
            if timed_out or result.returncode != 0:
                failures.append("run_bounded environment probe failed")
            else:
                child_env = json.loads(result.stdout)
                child_leaks = sorted(name for name in child_env
                                     if name.startswith("OMAMA_")
                                     or name in exact
                                     or name.startswith(GIT_CONFIG_PREFIXES))
                if child_leaks:
                    failures.append("run_bounded child retained routing/config "
                                    "keys: %s" % ", ".join(child_leaks))
                if child_env.get("GIT_ISOLATION_UNRELATED") != "must-survive":
                    failures.append("run_bounded child lost an unrelated "
                                    "GIT_* variable")
        except Exception as exc:  # noqa: BLE001 -- convert crashes to a named red
            failures.append("real self-test setup helpers failed under poison: %s: %s"
                            % (type(exc).__name__, exc))

        after = snapshot(decoy)
        if after != before:
            changed = sorted(set(before).union(after))
            changed = [name for name in changed
                       if before.get(name) != after.get(name)]
            failures.append("decoy repository bytes changed: %s"
                            % ", ".join(changed[:12]))
        if card_family(after) != card_family(before):
            failures.append("decoy CARD family changed")
    finally:
        os.environ.clear()
        os.environ.update(prior)
        rmtree(root)

    if failures:
        for failure in failures:
            print("[FAIL] %s" % failure)
        print("GIT ISOLATION RESULT: self-test helpers are not isolated")
        return 1
    print("[PASS] poisoned setup used scratch repos; decoy Git and CARD family "
          "survived byte-identical")
    print("GIT ISOLATION RESULT: VERIFIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
