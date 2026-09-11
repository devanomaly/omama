#!/usr/bin/env python3
"""Built-artifact admission, integration, and lifetime fixture.

Exit 0 means every required case ran. Exit 1 means behavior failed. Exit 2 is
reserved for a named missing prerequisite; this runner never turns a skip into
green. Full child output is retained below the printed disposable root.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).resolve().parent


class NotRun(RuntimeError):
    pass


def clean_env(extra=None):
    env = os.environ.copy()
    for key in list(env):
        if key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "PYTHONHOME", "VIRTUAL_ENV") \
                or key.startswith("GIT_CONFIG_") or key.startswith("OMAMA_"):
            env.pop(key, None)
    env.pop("PYTHONPATH", None)
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "UV_PYTHON_DOWNLOADS": "never"})
    if extra:
        env.update({key: str(value) for key, value in extra.items()})
    return env


def run(argv, cwd, root, name, env=None, input_text=None, timeout=900, expected=(0,)):
    log = root / "logs" / (name + ".log")
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            [str(value) for value in argv], cwd=str(cwd), env=env or clean_env(),
            input=input_text, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise NotRun("{0}: prerequisite unavailable: {1}".format(name, exc))
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + (exc.stderr or "")
        log.write_text(output, encoding="utf-8")
        raise NotRun("{0}: timed out after {1}s; full output: {2}".format(name, timeout, log))
    output = (result.stdout or "") + (result.stderr or "")
    log.write_text(output, encoding="utf-8")
    if result.returncode not in expected:
        raise AssertionError(
            "{0}: exit {1}, expected {2}; full output: {3}\n{4}".format(
                name, result.returncode, expected, log, output))
    return result


def test_root():
    allocated = os.environ.get("OMAMA_CLI_TEST_ROOT")
    if allocated:
        parent = Path(allocated).resolve()
        if not parent.is_dir():
            # Deliberately never created here: an unallocated or mistyped root
            # must be NOT-RUN, not a silent write somewhere else. The detail
            # below makes a recurrence attributable, because this entry starts
            # many minutes after the operator allocates the root and an
            # external cleaner can remove it in between.
            grandparent = parent.parent
            if grandparent.is_dir():
                try:
                    siblings = sorted(item.name for item in grandparent.iterdir())[:10]
                except OSError as exc:
                    siblings = ["<unreadable: {0}>".format(type(exc).__name__)]
                detail = "its parent {0} exists and currently contains: {1}".format(
                    grandparent, ", ".join(siblings) or "nothing")
            else:
                detail = "its parent {0} does not exist either".format(grandparent)
            raise NotRun(
                "OMAMA_CLI_TEST_ROOT is not an existing allocated directory: {0}; {1}. "
                "Allocate it immediately before this run and keep it outside any path "
                "subject to automatic temporary-file cleanup.".format(parent, detail))
        prefix = "f-" if os.name == "nt" else "full-{0}-py{1}{2}-".format(
            sys.platform, sys.version_info[0], sys.version_info[1])
        return Path(tempfile.mkdtemp(prefix=prefix, dir=str(parent)))
    return Path(tempfile.mkdtemp(prefix="omama-cli-full-{0}-py{1}{2}-".format(
        sys.platform.replace("win32", "windows"), sys.version_info[0], sys.version_info[1])))


def overlay_checkout(destination):
    ignored = {".git", "build", ".pytest_cache", "__pycache__"}
    for source in SOURCE.iterdir():
        if source.name in ignored or source.name.endswith(".egg-info"):
            continue
        target = destination / source.name
        if source.is_dir():
            shutil.copytree(str(source), str(target), dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns(".git", "build", "__pycache__", "*.egg-info", "*.pyc"))
        else:
            shutil.copy2(str(source), str(target))


def build_artifacts(root, uv, base_env):
    """Build the phase-1 pilot artifact.

    Phase-1 delivery is wheel-only: no source distribution is built, and no
    wheel-to-sdist equivalence is claimed or tested.  Whether a public release
    requires a source distribution remains a separate, later decision.
    """
    build_source = root / "build-source"
    run(["git", "-c", "safe.directory=" + SOURCE.as_posix(), "clone", "--quiet", "--no-hardlinks", str(SOURCE), str(build_source)],
        root, root, "clone-build-source", env=base_env)
    overlay_checkout(build_source)
    direct = root / "direct-dist"
    direct.mkdir()
    run([uv, "build", "--wheel", "--no-python-downloads", "--python", sys.executable,
         "--out-dir", str(direct)], build_source, root, "build-wheel", env=base_env, timeout=600)
    wheel = next(direct.glob("*.whl"), None)
    if not wheel:
        raise AssertionError("build did not produce a wheel")
    if next(direct.glob("*.tar.gz"), None):
        raise AssertionError("phase-1 delivery is wheel-only but a source distribution was produced")

    alternate_source = root / "alternate-source"
    shutil.copytree(str(build_source), str(alternate_source),
                    ignore=shutil.ignore_patterns(".git", "build", "__pycache__", "*.egg-info", "*.pyc"))
    readme = alternate_source / "cli" / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\nAlternate fixture identity.\n", encoding="utf-8")
    alternate_dir = root / "alternate-dist"
    alternate_dir.mkdir()
    run([uv, "build", "--wheel", "--no-python-downloads", "--python", sys.executable,
         "--out-dir", str(alternate_dir)], alternate_source, root, "build-alternate-bundle", env=base_env, timeout=600)
    alternate = next(alternate_dir.glob("*.whl"))
    run([sys.executable, "-B", str(FIXTURE / "check_artifacts.py"),
         "--wheel", str(wheel), "--source", str(build_source)],
        root, root, "artifact-inspection", env=base_env)
    return wheel, alternate


def venv_python(root):
    return root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def entrypoint(root):
    return root / ("Scripts/omama.exe" if os.name == "nt" else "bin/omama")


def install_tool(root, name, wheel, uv, env):
    tool = root / name
    run([uv, "venv", str(tool), "--python", sys.executable, "--no-python-downloads"], root, root,
        name + "-venv", env=env)
    run([uv, "pip", "install", "--python", str(venv_python(tool)), "--no-deps", "--no-python-downloads",
         "--no-config", "--no-sources", "--link-mode", "copy", str(wheel)], root, root,
        name + "-install", env=env)
    marker = tool / ".omama-test-owner.json"
    marker.write_text(json.dumps({"test_owned": True}) + "\n", encoding="utf-8")
    return tool


def explicit_interpreter(root, uv, env):
    probe = subprocess.run([sys.executable, "-B", "-c", "import yaml"], env=clean_env(),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if probe.returncode == 0:
        return Path(sys.executable)
    explicit = root / "explicit-runtime"
    run([uv, "venv", str(explicit), "--python", sys.executable, "--no-python-downloads"], root, root,
        "explicit-venv", env=env)
    run([uv, "pip", "install", "--python", str(venv_python(explicit)), "--no-python-downloads", "--no-config",
         "--no-sources", "--link-mode", "copy", "PyYAML>=6.0.2,<7"], root, root,
        "explicit-pyyaml", env=env, timeout=600)
    return venv_python(explicit)


def make_repo(root, name):
    repo = root / "targets" / name
    repo.mkdir(parents=True)
    env = clean_env()
    run(["git", "init", "-q", str(repo)], root, root, name + "-git-init", env=env)
    run(["git", "-C", str(repo), "config", "--local", "user.email", "fixture@example.invalid"], root, root, name + "-git-email", env=env)
    run(["git", "-C", str(repo), "config", "--local", "user.name", "Omama fixture"], root, root, name + "-git-name", env=env)
    (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
    (repo / "CARD.yaml").write_text("goal: fixture\nnon_goals: [none]\ntier: S1\ntask_type: implementation\ndone_when: [done]\nverify: 'git diff --quiet HEAD --'\n", encoding="utf-8")
    run(["git", "-C", str(repo), "add", "tracked.txt", "CARD.yaml"], root, root, name + "-git-add", env=env)
    run(["git", "-C", str(repo), "-c", "core.hooksPath=.no-hooks", "commit", "-qm", "base"], root, root, name + "-git-commit", env=env)
    return repo


def public_entrypoint_proof(root, tool, explicit):
    cli = entrypoint(tool)
    if not cli.is_file():
        raise AssertionError("installed console entrypoint is absent: " + str(cli))
    version = run([cli, "--version"], root, root, "entrypoint-version", env=clean_env())
    if "omama 0.1.0" not in version.stdout:
        raise AssertionError("installed public entrypoint returned unexpected version")
    repo = make_repo(root, "public-explicit")
    before_card = (repo / "CARD.yaml").read_bytes()
    before_index = (repo / ".git" / "index").read_bytes()
    result = run([cli, "init", str(repo), "--python", str(explicit)], repo, root,
                 "public-explicit-init", env=clean_env(), timeout=600)
    output = result.stdout + result.stderr
    for marker in ("ADMISSION-OK[receipt-s1]", "ADMISSION-OK[receipt-s3]",
                   "ADMISSION-OK[privacy-pre-commit]", "ADMISSION-OK[privacy-pre-merge-commit]",
                   "ADMISSION-OK[complete-payload-commit]", "INSTALLED"):
        if marker not in output:
            raise AssertionError("public init omitted required proof: " + marker)
    state = json.loads((repo / ".omama" / "state.json").read_text(encoding="utf-8"))
    if state.get("status") != "complete":
        raise AssertionError("public init did not publish complete state")
    doctor = run([cli, "doctor", str(repo)], repo, root, "public-explicit-doctor", env=clean_env(), timeout=300)
    if "DOCTOR-OK" not in doctor.stdout:
        raise AssertionError("public doctor did not report DOCTOR-OK")
    if before_card != (repo / "CARD.yaml").read_bytes() or before_index != (repo / ".git" / "index").read_bytes():
        raise AssertionError("public init/doctor changed protected card or index bytes")


def copy_installed_topology(source, destination):
    shutil.copytree(str(source / "tools"), str(destination / "tools"))
    shutil.copytree(str(source / ".githooks"), str(destination / ".githooks"))
    shutil.copy2(str(source / "privacy-deny.json"), str(destination / "privacy-deny.json"))


def gate_close(root, source, state, name, tier, review):
    repo = make_repo(root, name)
    copy_installed_topology(source, repo)
    verify = "git diff --quiet HEAD --"
    (repo / "CARD.yaml").write_text(
        "goal: lifetime fixture\nnon_goals: [none]\ntier: {0}\ntask_type: implementation\ndone_when: [done]\nverify: '{1}'\n".format(tier, verify), encoding="utf-8")
    paths = ["CARD.yaml"]
    if review is not None:
        (repo / "CARD.review.md").write_text(review, encoding="utf-8")
        paths.append("CARD.review.md")
    env = clean_env()
    run(["git", "-C", str(repo), "add"] + paths, repo, root, name + "-add-card", env=env)
    run(["git", "-C", str(repo), "-c", "core.hooksPath=.no-hooks", "commit", "-qm", "card"], repo, root, name + "-card-commit", env=env)
    (repo / "CARD.close").write_text("CLOSE\n", encoding="utf-8")
    payload = json.dumps({"cwd": str(repo), "stop_hook_active": False, "hook_event_name": "Stop"})
    shell = shell_path()
    result = run([shell, "-c", state["settings_command"]], repo, root, name + "-close",
                 env=clean_env({"CLAUDE_PROJECT_DIR": repo.as_posix(), "UV_OFFLINE": "1", "PIP_NO_INDEX": "1",
                                "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9"}),
                 input_text=payload, timeout=300)
    if "VERIFIED" not in result.stdout or (repo / "CARD.close").exists():
        raise AssertionError(name + ": installed receipt command did not close VERIFIED")


def shell_path():
    if os.name != "nt":
        shell = shutil.which("sh")
        if not shell:
            raise NotRun("required POSIX sh is unavailable")
        return shell
    knob = os.environ.get("CLAUDE_CODE_GIT_BASH_PATH")
    candidates = [Path(knob)] if knob else []
    git = shutil.which("git")
    if git:
        directory = Path(git).resolve().parent
        candidates += [directory.parent / "bin" / "bash.exe", directory.parent.parent / "bin" / "bash.exe"]
    shell = next((path for path in candidates if path.is_file()), None)
    if not shell:
        raise NotRun("required Git Bash is unavailable")
    return str(shell)


def privacy_commit(root, source, name):
    repo = make_repo(root, name)
    copy_installed_topology(source, repo)
    token = "OMAMA_LIFETIME_SYNTHETIC_" + hashlib.sha256(str(repo).encode("utf-8")).hexdigest()[:12]
    (repo / "privacy-deny.json").write_text(json.dumps({"deny_regexes": [], "deny_filenames": [], "tokens_file": ".fixture-tokens"}) + "\n", encoding="utf-8")
    (repo / ".fixture-tokens").write_text(token + "\n", encoding="utf-8")
    run(["git", "-C", str(repo), "config", "--local", "core.hooksPath", ".githooks"], repo, root, name + "-hooks", env=clean_env())
    (repo / "privacy.txt").write_text("clean lifetime content\n", encoding="utf-8")
    run(["git", "-C", str(repo), "add", "privacy.txt"], repo, root, name + "-add", env=clean_env())
    result = run(["git", "-C", str(repo), "commit", "-m", "privacy lifetime green"], repo, root,
                 name + "-commit", env=clean_env({"UV_OFFLINE": "1", "PIP_NO_INDEX": "1",
                                                  "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9"}))
    if result.returncode != 0:
        raise AssertionError("privacy commit failed after CLI removal")


def lifetime_proof(root, tool, uv):
    cli = entrypoint(tool)
    target = make_repo(root, "lifetime-installed-target")
    initialized = run([cli, "init", str(target)], target, root, "lifetime-managed-init", env=clean_env(), timeout=600)
    if "INSTALLED" not in initialized.stdout:
        raise AssertionError("managed lifetime target did not complete public init")
    state = json.loads((target / ".omama" / "state.json").read_text(encoding="utf-8"))
    expected = target / ".omama" / "runtime" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if state.get("receipt_interpreter") != expected.absolute().as_posix():
        raise AssertionError("managed receipt_interpreter lost the venv executable path: expected {0}, got {1}".format(
            expected.absolute().as_posix(), state.get("receipt_interpreter")))
    if json.loads((tool / ".omama-test-owner.json").read_text(encoding="utf-8")) != {"test_owned": True}:
        raise AssertionError("refusing to remove unowned CLI tool environment")
    if tool.parent.resolve() != root.resolve():
        raise AssertionError("CLI tool environment is outside the fixture root")
    shutil.rmtree(str(tool))
    if tool.exists() or cli.exists():
        raise AssertionError("validated CLI tool environment was not removed")
    # The test-owned CLI environment is gone, which is what this proves: the
    # two assertions above check exactly that. An unrelated omama installed
    # elsewhere on the host's PATH is not part of this claim and was never
    # used by it, so it is no longer asserted about.
    valid_review = "<!-- review v1 · tier: S -->\nVerdict: PASS\n\n## Findings\n\n- Clean.\n\n## Non-findings\n\n- Installed checker ran.\n"
    gate_close(root, target, state, "lifetime-s1", "S1", None)
    gate_close(root, target, state, "lifetime-s3", "S3", valid_review)
    privacy_commit(root, target, "lifetime-privacy")
    doctor = venv_python(target / ".omama" / "runtime")
    if not doctor.is_file():
        raise AssertionError("managed runtime disappeared with CLI tool")
    base = Path(state["base_interpreter"])
    if not base.is_file():
        raise AssertionError("recorded base prerequisite is already absent")
    print("OK lifetime: deleted actual installed CLI tool; offline S1/S3 closes and privacy commit passed")
    print("LIMITATION: recorded base Python remains required; doctor detects its removal or repository relocation")


def run_contract_suites(root, wheel, alternate, tool, explicit, env):
    suite_env = clean_env({
        "PYTHONPATH": str(wheel) + os.pathsep + str(FIXTURE),
        "OMAMA_CLI_TEST_ROOT": str(root),
        "OMAMA_PACKAGING_TEST_ROOT": str(root),
        "OMAMA_BUILT_WHEEL": str(wheel),
        "OMAMA_T8_WHEEL": str(wheel),
        "OMAMA_T7_WHEEL": str(alternate),
        "OMAMA_EXPLICIT_PYTHON": str(explicit),
        "OMAMA_T9_CLI_PYTHON": str(venv_python(tool)),
        "OMAMA_INSTALLED_TOOL_PYTHON": str(venv_python(tool)),
        "OMAMA_RUN_MANAGED_RUNTIME": "1",
        "OMAMA_MANAGED_BASE_PYTHON": sys.executable,
    })
    # Runtime is last because its installed-tool lifetime case deliberately
    # removes this marked tool after every other suite has consumed it.
    for module in ("test_packaging", "test_install", "test_wiring", "test_recovery", "test_doctor", "test_admission", "test_runtime"):
        result = run([sys.executable, "-B", "-m", "unittest", "-v", module], FIXTURE, root,
                     "suite-" + module, env=suite_env, timeout=1800)
        output = result.stdout + result.stderr
        if "skipped=" in output or " skipped " in output or " (skipped=" in output:
            raise AssertionError(module + ": required full coverage contained a skip; see retained log")


def main():
    root = test_root()
    print("T10 disposable root: " + str(root))
    (root / "OWNER.json").write_text(json.dumps({"test_owned": True, "source": SOURCE.as_posix()}, indent=2) + "\n", encoding="utf-8")
    missing = [name for name in ("git", "uv") if shutil.which(name) is None]
    if missing:
        raise NotRun("missing prerequisite(s): " + ", ".join(missing))
    shell_path()
    base_env = clean_env({
        "UV_CACHE_DIR": root / "uv-cache", "UV_PYTHON_INSTALL_DIR": root / "uv-python",
        "TMP": root / "tmp", "TEMP": root / "tmp", "TMPDIR": root / "tmp",
    })
    (root / "tmp").mkdir()
    wheel, alternate = build_artifacts(root, shutil.which("uv"), base_env)
    tool = install_tool(root, "cli-tool", wheel, shutil.which("uv"), base_env)
    lifetime_tool = install_tool(root, "lifetime-cli-tool", wheel, shutil.which("uv"), base_env)
    explicit = explicit_interpreter(root, shutil.which("uv"), base_env)
    run([venv_python(tool), "-B", str(FIXTURE / "challenge_installed_bundle.py"), "--source", str(SOURCE)],
        root, root, "installed-bundle-challenges", env=clean_env())
    public_entrypoint_proof(root, tool, explicit)
    run_contract_suites(root, wheel, alternate, tool, explicit, base_env)
    lifetime_proof(root, lifetime_tool, shutil.which("uv"))
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    print("OK artifacts: wheel={0} sha256={1}".format(wheel, digest))
    print("OK platform: {0} Python {1}.{2}; every required local case ran".format(
        sys.platform, sys.version_info[0], sys.version_info[1]))
    print("OK cli fixture: built wheel (phase-1 wheel-only), installed entrypoint, init/doctor, contracts, and lifetime")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except NotRun as exc:
        print("NOT-RUN: " + str(exc), file=sys.stderr)
        raise SystemExit(2)
    except Exception as exc:
        print("FAILED: {0}: {1}".format(type(exc).__name__, exc), file=sys.stderr)
        raise SystemExit(1)
