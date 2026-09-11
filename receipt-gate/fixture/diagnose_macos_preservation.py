#!/usr/bin/env python3
"""Bounded macOS evidence for two historical fixture preservation failures.

This is diagnostic support, not a replacement for either counted fixture. It
uses only a new child of ``OMAMA_MACOS_DIAGNOSTIC_ROOT`` (under runner.temp),
retains strict byte equality, and records only synthetic target snapshots plus
the argv/PID/timing of fixture children and Git Trace2 events started here.
"""

import hashlib
import importlib.util
import json
import os
import platform
import subprocess
import sys
import threading
import time
import types
from pathlib import Path


HERE = Path(__file__).resolve().parent
GATE = HERE.parent / "receipt_gate.py"
WIRING = HERE.parent / "adapt" / "check_wiring.py"
PYTHON = Path(sys.executable).resolve()
GIT_ROUTING = (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR", "GIT_NAMESPACE",
    "GIT_CEILING_DIRECTORIES", "GIT_DISCOVERY_ACROSS_FILESYSTEM",
    "GIT_CONFIG", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT",
    "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM",
)
GIT_CONFIG_PREFIXES = ("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")


def _required_root():
    supplied = os.environ.get("OMAMA_MACOS_DIAGNOSTIC_ROOT")
    runner_temp = os.environ.get("RUNNER_TEMP")
    if not supplied or not runner_temp:
        raise RuntimeError("OMAMA_MACOS_DIAGNOSTIC_ROOT and RUNNER_TEMP are required")
    parent = Path(supplied).resolve()
    boundary = Path(runner_temp).resolve()
    try:
        parent.relative_to(boundary)
    except ValueError:
        raise RuntimeError("diagnostic root must be below runner.temp")
    root = parent / "owned-macos-preservation-v1"
    if root.exists():
        raise RuntimeError("refusing to reuse diagnostic root: " + str(root))
    root.mkdir(parents=True)
    return root


ROOT = _required_root()
SNAPSHOTS = ROOT / "snapshots"
OUTPUTS = ROOT / "outputs"
TRACES = ROOT / "git-trace2"
for directory in (SNAPSHOTS, OUTPUTS, TRACES):
    directory.mkdir()
PROCESS_LOG = ROOT / "processes.jsonl"
CHILD_LOG = ROOT / "fixture-children.jsonl"
SEQUENCE = 0
IMMEDIATE_SNAPSHOTS = {}


def _json_write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _clean_env(extra=None):
    env = {
        key: value for key, value in os.environ.items()
        if key not in GIT_ROUTING
        and not key.startswith(GIT_CONFIG_PREFIXES)
        and not key.startswith("OMAMA_")
        and not key.startswith("GIT_TRACE")
    }
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if extra:
        env.update({key: str(value) for key, value in extra.items()})
    return env


def _relative(path):
    path = Path(path).resolve()
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        if path in (PYTHON, GATE.resolve(), WIRING.resolve()):
            return path.as_posix()
        return "outside-diagnostic-root"


def _log_process(value):
    with PROCESS_LOG.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, sort_keys=True) + "\n")


def _run(
    label, argv, cwd, env=None, input_text=None, timeout=120,
    trace_git=False, immediate_scope=None,
):
    global SEQUENCE
    SEQUENCE += 1
    child_env = dict(env or _clean_env())
    trace = TRACES / ("{0:03d}-{1}.jsonl".format(SEQUENCE, label))
    if trace_git:
        child_env["GIT_TRACE2_EVENT"] = str(trace)
    started = time.time_ns()
    process = subprocess.Popen(
        [str(value) for value in argv], cwd=str(cwd), env=child_env,
        stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace",
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(input=input_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        stdout, stderr = process.communicate()
    child_completed = time.time_ns()
    if immediate_scope is not None:
        # This must be the first operation after child completion. In
        # particular, do not write process/output diagnostics before sampling
        # a detached Git maintenance lock left by the setup commit.
        immediate = _snapshot(immediate_scope)
        IMMEDIATE_SNAPSHOTS[label] = immediate
        _json_write(SNAPSHOTS / (label + "-immediate.json"), immediate)
    ended = time.time_ns()
    record = {
        "sequence": SEQUENCE,
        "label": label,
        "argv": [str(value) for value in argv],
        "cwd": _relative(cwd),
        "pid": process.pid,
        "returncode": process.returncode,
        "started_ns": started,
        "child_completed_ns": child_completed,
        "ended_ns": ended,
        "timed_out": timed_out,
        "trace2": trace.relative_to(ROOT).as_posix() if trace.exists() else None,
    }
    _log_process(record)
    (OUTPUTS / ("{0:03d}-{1}.stdout".format(SEQUENCE, label))).write_text(stdout or "", encoding="utf-8")
    (OUTPUTS / ("{0:03d}-{1}.stderr".format(SEQUENCE, label))).write_text(stderr or "", encoding="utf-8")
    if timed_out:
        raise RuntimeError(label + " timed out")
    return process.returncode, stdout or "", stderr or ""


def _git(label, repo, *args, trace_git=False, immediate_scope=None):
    result = _run(
        label, ["git", "-C", repo] + list(args), ROOT,
        trace_git=trace_git, immediate_scope=immediate_scope,
    )
    if result[0] != 0:
        raise RuntimeError("git setup failed ({0}): {1}".format(label, result[2][-1000:]))
    return result


def _snapshot(root):
    root = Path(root)
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            data = path.read_bytes()
            result[path.relative_to(root).as_posix()] = {
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
            }
    return result


def _delta(before, after):
    before_names = set(before)
    after_names = set(after)
    return {
        "added": sorted(after_names - before_names),
        "removed": sorted(before_names - after_names),
        "changed": sorted(
            name for name in before_names & after_names
            if before[name]["sha256"] != after[name]["sha256"]
        ),
    }


def _capture(label, root):
    value = _snapshot(root)
    _json_write(SNAPSHOTS / (label + ".json"), value)
    return value


def _start_scope_watcher(label, scope, baseline):
    stop = threading.Event()
    observations = {}
    read_errors = []

    def watch():
        while not stop.is_set():
            try:
                current = _snapshot(scope)
            except OSError as exc:
                read_errors.append({"type": type(exc).__name__, "time_ns": time.time_ns()})
                continue
            if current == baseline:
                continue
            delta = _delta(baseline, current)
            changed_names = sorted(set(delta["added"] + delta["removed"] + delta["changed"]))
            states = {
                name: {"baseline": baseline.get(name), "observed": current.get(name)}
                for name in changed_names
            }
            key = json.dumps(states, sort_keys=True)
            now = time.time_ns()
            row = observations.setdefault(key, {
                "delta": delta,
                "states": states,
                "first_seen_ns": now,
                "last_seen_ns": now,
                "observations": 0,
            })
            row["last_seen_ns"] = now
            row["observations"] += 1

    thread = threading.Thread(target=watch, name=label + "-scope-watcher")
    thread.start()
    return stop, thread, observations, read_errors


def _finish_scope_watcher(label, watcher):
    stop, thread, observations, read_errors = watcher
    stop.set()
    thread.join()
    value = {
        "transient_states": sorted(observations.values(), key=lambda row: row["first_seen_ns"]),
        "read_errors": read_errors,
    }
    _json_write(ROOT / (label + "-scope-watcher.json"), value)
    return value


def _make_repo(path, prefix, trace_git=False):
    path.mkdir(parents=True)
    _git(prefix + "-git-init", path, "init", "-q", trace_git=trace_git)
    _git(prefix + "-git-email", path, "config", "user.email", "macos-diagnostic@example.invalid", trace_git=trace_git)
    _git(prefix + "-git-name", path, "config", "user.name", "macOS diagnostic", trace_git=trace_git)
    (path / "tracked.txt").write_text("base\n", encoding="utf-8")
    _git(prefix + "-git-add", path, "add", "tracked.txt", trace_git=trace_git)
    commit_label = prefix + "-git-commit"
    git_database = path / ".git"
    stop_watcher = threading.Event()
    lock_observations = {}

    def watch_maintenance_locks():
        objects = git_database / "objects"
        while not stop_watcher.is_set():
            try:
                candidates = list(objects.glob("maintenance*.lock"))
            except OSError:
                candidates = []
            for candidate in candidates:
                try:
                    data = candidate.read_bytes()
                except OSError:
                    continue
                key = candidate.name + ":" + hashlib.sha256(data).hexdigest()
                now = time.time_ns()
                row = lock_observations.setdefault(key, {
                    "path": "objects/" + candidate.name,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "size": len(data),
                    "first_seen_ns": now,
                    "last_seen_ns": now,
                    "observations": 0,
                })
                row["last_seen_ns"] = now
                row["observations"] += 1

    watcher = threading.Thread(target=watch_maintenance_locks, name=prefix + "-maintenance-lock-watcher")
    watcher.start()
    try:
        _git(
            commit_label, path, "commit", "-qm", "base",
            trace_git=trace_git, immediate_scope=git_database,
        )
    finally:
        stop_watcher.set()
        watcher.join()
    after_bookkeeping = _capture(prefix + "-post-commit-bookkeeping", git_database)
    _json_write(ROOT / (prefix + "-commit-transition.json"), {
        "immediate_to_post_bookkeeping": _delta(
            IMMEDIATE_SNAPSHOTS[commit_label], after_bookkeeping,
        ),
        "immediate_snapshot": "snapshots/" + commit_label + "-immediate.json",
        "post_bookkeeping_snapshot": "snapshots/" + prefix + "-post-commit-bookkeeping.json",
        "maintenance_lock_observations": sorted(lock_observations.values(), key=lambda row: row["path"]),
    })


def _card_text(verify):
    quoted = "'" + verify.replace("'", "''") + "'"
    return (
        "goal: 'macOS diagnostic'\n"
        "non_goals: ['nothing']\n"
        "tier: S1\n"
        "task_type: implementation\n"
        "done_when: ['observable thing']\n"
        "verify: {0}\n".format(quoted)
    )


def _plant_settings(repo):
    settings = repo / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    command = '"{0}" "{1}"'.format(PYTHON.as_posix(), GATE.as_posix())
    value = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": command}]}]}}
    _json_write(settings, value)


def _logged_popen_prefix():
    return (
        "import json, os, subprocess, time\n"
        "_omama_original_popen = subprocess.Popen\n"
        "_omama_child_log = " + repr(str(CHILD_LOG)) + "\n"
        "def _omama_logged_popen(*a, **kw):\n"
        "    p = _omama_original_popen(*a, **kw)\n"
        "    argv = a[0] if a else kw.get('args')\n"
        "    row = {'pid': p.pid, 'parent_pid': os.getpid(), 'argv': [str(x) for x in argv] if isinstance(argv, (list, tuple)) else str(argv), 'cwd': str(kw.get('cwd') or os.getcwd()), 'spawned_ns': time.time_ns()}\n"
        "    with open(_omama_child_log, 'a', encoding='utf-8') as s: s.write(json.dumps(row, sort_keys=True) + '\\n')\n"
        "    return p\n"
        "subprocess.Popen = _omama_logged_popen\n"
    )


def _phase(label, scope, baseline, argv, cwd, env, expected_rc, required_text, input_text=None):
    before = _capture(label + "-before", scope)
    rc, stdout, stderr = _run(label, argv, cwd, env=env, input_text=input_text)
    after = _capture(label + "-after", scope)
    record = {
        "label": label,
        "returncode": rc,
        "expected_returncode": expected_rc,
        "required_text": required_text,
        "required_text_present": required_text in stdout + stderr,
        "interval_equal": before == after,
        "interval_delta": _delta(before, after),
        "equal_to_post_setup_baseline": baseline == after,
        "from_post_setup_delta": _delta(baseline, after),
    }
    _json_write(ROOT / (label + "-result.json"), record)
    return record


def _routing_case():
    repo = ROOT / "routing-response" / "target"
    _make_repo(repo, "routing")
    _plant_settings(repo)
    baseline = _capture("routing-post-setup", repo)
    watcher = _start_scope_watcher("routing", repo, baseline)
    results = []
    variables = ("GIT_DIR", "GIT_CONFIG_COUNT", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM")
    try:
        for variable in variables:
            env = _clean_env({variable: "private-routing-value"})
            results.append(_phase(
                "routing-control-" + variable.lower(), repo, baseline,
                [PYTHON, "-B", "-c", "pass"], repo, env, 0, "",
            ))
        wrapper = _logged_popen_prefix() + (
            "import runpy, sys\n"
            "target = sys.argv.pop(1)\n"
            "runpy.run_path(target, run_name='__main__')\n"
        )
        for variable in variables:
            env = _clean_env({variable: "private-routing-value"})
            results.append(_phase(
                "routing-invoke-" + variable.lower(), repo, baseline,
                [PYTHON, "-B", "-c", wrapper, WIRING, repo], repo, env, 1,
                "gate responded with GIT-ROUTING",
            ))
    finally:
        _finish_scope_watcher("routing", watcher)
    return results


def _setup_trace_control():
    """Trace only a separate setup/no-gate control.

    The challenged repositories deliberately do not enable Git Trace2: its
    extra setup I/O could change the short interval in which a detached Git
    maintenance writer races the first preservation snapshot.
    """
    repo = ROOT / "setup-trace-control" / "target"
    _make_repo(repo, "trace-control", trace_git=True)
    baseline = _capture("trace-control-post-setup", repo)
    return [_phase(
        "trace-control-no-gate", repo, baseline,
        [PYTHON, "-B", "-c", "pass"], repo, _clean_env(), 0, "",
    )]


def _load_original_fixture():
    path = HERE / "run_fixture.py"
    spec = importlib.util.spec_from_file_location("omama_original_receipt_fixture", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_original_case(module, label, function, expected_snapshot_calls):
    case_root = ROOT / "original-cases" / label
    case_root.mkdir(parents=True)
    captures = []
    original_snapshot = module._binding_snapshot

    def capture_after_original_returns(scope):
        value = original_snapshot(scope)
        # Do not hash, sort, or write here. The original byte collection has
        # already completed; retain only its returned map and one timestamp in
        # RAM so the next original instruction runs with minimal disturbance.
        captures.append((Path(scope), time.time_ns(), dict(value)))
        return value

    module._binding_snapshot = capture_after_original_returns
    failure = None
    try:
        function(case_root)
    except Exception as exc:
        failure = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        module._binding_snapshot = original_snapshot

    maps = []
    baseline = captures[0][2] if captures else None
    aggregate_delta = {"added": set(), "removed": set(), "changed": set()}
    for index, (scope, captured_ns, raw) in enumerate(captures, 1):
        hashes = {
            name: {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
            for name, data in raw.items()
        }
        name = "original-{0}-snapshot-{1:02d}.json".format(label, index)
        _json_write(SNAPSHOTS / name, hashes)
        delta = _delta(
            {key: {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)} for key, data in baseline.items()},
            hashes,
        ) if baseline is not None else None
        if delta is not None:
            for kind in aggregate_delta:
                aggregate_delta[kind].update(delta[kind])
        maps.append({
            "scope": _relative(scope),
            "captured_ns": captured_ns,
            "snapshot": "snapshots/" + name,
            "delta_from_first": delta,
        })
    aggregate_delta = {kind: sorted(names) for kind, names in aggregate_delta.items()}
    collection_complete = len(captures) == expected_snapshot_calls
    has_delta = any(aggregate_delta.values())
    byte_equality = False if has_delta else (True if collection_complete else None)
    record = {
        "label": "original-" + label,
        "returncode": 0 if failure is None else 1,
        "expected_returncode": 0,
        "required_text": "original case assertions",
        "required_text_present": failure is None,
        "interval_equal": byte_equality,
        "interval_delta": aggregate_delta,
        "equal_to_post_setup_baseline": byte_equality,
        "from_post_setup_delta": aggregate_delta,
        "failure": failure,
        "snapshot_collection_complete": collection_complete,
        "expected_snapshot_calls": expected_snapshot_calls,
        "original_snapshot_calls": maps,
    }
    _json_write(ROOT / ("original-" + label + "-result.json"), record)
    return record


def _original_cases():
    module = _load_original_fixture()
    return [
        _run_original_case(module, "mount", module.a_nongit_mount_outer_marker, 4),
        _run_original_case(module, "routing", module.w_routing_response, 5),
    ]


def _collector_selftest():
    def raw_snapshot(scope):
        return {
            path.relative_to(scope).as_posix(): path.read_bytes()
            for path in Path(scope).rglob("*") if path.is_file()
        }

    module = types.SimpleNamespace(_binding_snapshot=raw_snapshot)

    def unchanged(case_root):
        (case_root / "owned.txt").write_bytes(b"same\n")
        module._binding_snapshot(case_root)
        module._binding_snapshot(case_root)

    def mutation(case_root):
        path = case_root / "owned.txt"
        path.write_bytes(b"before\n")
        module._binding_snapshot(case_root)
        path.write_bytes(b"after\n")
        module._binding_snapshot(case_root)

    def semantic_failure(case_root):
        (case_root / "owned.txt").write_bytes(b"same\n")
        module._binding_snapshot(case_root)
        module._binding_snapshot(case_root)
        raise RuntimeError("controlled semantic failure")

    green = _run_original_case(module, "collector-green", unchanged, 2)
    red = _run_original_case(module, "collector-mutation", mutation, 2)
    semantic = _run_original_case(module, "collector-semantic", semantic_failure, 2)
    if not (
        green["returncode"] == 0 and green["interval_equal"] is True
        and red["returncode"] == 0 and red["interval_equal"] is False
        and red["interval_delta"] == {"added": [], "removed": [], "changed": ["owned.txt"]}
        and semantic["returncode"] == 1 and semantic["interval_equal"] is True
        and semantic["failure"]["message"] == "controlled semantic failure"
    ):
        raise RuntimeError("original snapshot collector self-test failed")
    result = {"green": green, "owned_mutation": red, "semantic_only_failure": semantic, "result": "VERIFIED"}
    _json_write(ROOT / "collector-selftest.json", result)
    return result


def _mount_wrapper(outer, plain):
    return _logged_popen_prefix() + (
        "import pathlib, runpy, subprocess, sys, types\n"
        "boundary = pathlib.Path(" + repr(str(outer)) + ").resolve()\n"
        "start = pathlib.Path(" + repr(str(plain)) + ").resolve()\n"
        "original_run = subprocess.run\n"
        "original_stat = pathlib.Path.stat\n"
        "def stat(path, *a, **kw):\n"
        "    result = original_stat(path, *a, **kw)\n"
        "    if path == start:\n"
        "        return types.SimpleNamespace(st_dev=-1, st_mode=result.st_mode)\n"
        "    return result\n"
        "def discovery(argv, *a, **kw):\n"
        "    if argv[0] == 'git' and argv[-2:] == ['rev-parse', '--show-toplevel']:\n"
        "        return subprocess.CompletedProcess(argv, 128, '', 'fatal: not a git repository (or any parent up to mount point ' + str(boundary) + ')\\nStopping at filesystem boundary (GIT_DISCOVERY_ACROSS_FILESYSTEM not set).\\n')\n"
        "    return original_run(argv, *a, **kw)\n"
        "pathlib.Path.stat = stat\n"
        "subprocess.run = discovery\n"
        "runpy.run_path(sys.argv[1], run_name='__main__')\n"
    )


def _mount_case():
    outer = ROOT / "mounted-boundary" / "outer"
    _make_repo(outer, "mount")
    plain = outer / "mounted"
    plain.mkdir()
    git_database = outer / ".git"
    baseline = _capture("mount-post-setup", git_database)
    watcher = _start_scope_watcher("mount", git_database, baseline)
    results = []
    wrapper = _mount_wrapper(outer, plain)
    payload = json.dumps({"cwd": str(plain), "stop_hook_active": False, "hook_event_name": "Stop"})
    verify = '"{0}" -c "import sys; sys.exit(0)"'.format(PYTHON)
    try:
        for intent in ("no-card", "wip", "honest"):
            if intent != "no-card":
                (plain / "CARD.yaml").write_text(_card_text(verify), encoding="utf-8")
            if intent == "honest":
                (plain / "CARD.close").write_bytes(b"FAILED: genuinely non-Git")
            env = _clean_env({
                "OMAMA_VALIDATOR": str(HERE.parent.parent / "work-order" / "validate_work_order.py"),
                "OMAMA_CHECK_ARTIFACT": str(HERE.parent.parent / "output-discipline" / "scripts" / "check_artifact.py"),
            })
            results.append(_phase(
                "mount-control-" + intent, git_database, baseline,
                [PYTHON, "-B", "-c", "pass"], plain, env, 0, "",
            ))
            marker = {"no-card": "NO-CARD:", "wip": "WIP:", "honest": "CLOSE: FAILED"}[intent]
            results.append(_phase(
                "mount-invoke-" + intent, git_database, baseline,
                [PYTHON, "-B", "-c", wrapper, GATE], plain, env, 0, marker,
                input_text=payload,
            ))
    finally:
        _finish_scope_watcher("mount", watcher)
    receipt = json.loads((plain / "CARD.receipt.json").read_text(encoding="utf-8"))
    if receipt.get("verdict") != "FAILED" or (plain / "CARD.close").exists():
        raise RuntimeError("mounted honest-close semantics did not complete")
    return results


def main():
    _json_write(ROOT / "OWNER.json", {
        "owned": True,
        "scope": "synthetic macOS preservation diagnostics",
        "runner_temp": str(Path(os.environ["RUNNER_TEMP"]).resolve()),
    })
    git_version = _run("git-version", ["git", "--version"], ROOT)
    # Preserve the historical fixture order: the mounted case is first and
    # routing-response follows later. Only the two challenged cases run here.
    # Load-bearing replays call the original two fixture functions. The
    # instrumented reconstructions below are controls only.
    collector = _collector_selftest()
    results = _original_cases() + _setup_trace_control() + _mount_case() + _routing_case()
    failures = [
        item for item in results
        if item["returncode"] != item["expected_returncode"]
        or not item["required_text_present"]
        or not item["equal_to_post_setup_baseline"]
    ]
    summary = {
        "schema": 1,
        "platform": platform.platform(),
        "python": sys.version,
        "source_head": os.environ.get("GITHUB_SHA"),
        "git_version": (git_version[1] + git_version[2]).strip(),
        "cases": results,
        "strict_failures": [item["label"] for item in failures],
        "result": "VERIFIED" if not failures else "FAILED",
        "collector_selftest": collector["result"],
        "setup_commit_transitions": {
            prefix: json.loads((ROOT / (prefix + "-commit-transition.json")).read_text(encoding="utf-8"))
            for prefix in ("trace-control", "mount", "routing")
        },
        "scope_watchers": {
            label: json.loads((ROOT / (label + "-scope-watcher.json")).read_text(encoding="utf-8"))
            for label in ("mount", "routing")
        },
        "historical_scope": [
            "run 34313675810 / 275c1f5 routing-response target bytes",
            "run 34314782101 / 9f2608a mounted outer-Git bytes",
        ],
    }
    _json_write(ROOT / "summary.json", summary)
    print("MACOS-PRESERVATION-DIAGNOSTIC: " + summary["result"])
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        _json_write(ROOT / "fatal.json", {"type": type(exc).__name__, "message": str(exc)})
        raise
