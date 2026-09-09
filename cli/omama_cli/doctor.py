"""Non-mutating installation inventory for ``omama doctor``."""

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .install import JOURNAL_REL, LOCK_REL, STATE_REL, InstallError, _snapshot_file, read_state
from .runtime import _probe
from .wiring import (
    LOCAL_SETTINGS, MANAGED_ENV_KEYS, SETTINGS, _compatible_gate,
    _git_config_value, _mentions_gate, _read_json, _stop_handlers,
    managed_command,
)


@dataclass(frozen=True)
class InternalDoctorContext:
    owner: str
    state: dict
    scratch_root: object = None


@dataclass(frozen=True)
class DoctorItem:
    status: str
    name: str
    detail: str


class DoctorReport:
    def __init__(self):
        self.items = []

    def add(self, status, name, detail):
        self.items.append(DoctorItem(status, name, detail))

    @property
    def exit_code(self):
        if any(item.status == "VIOLATION" for item in self.items):
            return 1
        if any(item.status == "NOT-RUN" for item in self.items):
            return 2
        return 0

    def emit(self, stdout=None, stderr=None):
        stdout = stdout or sys.stdout
        stderr = stderr or sys.stderr
        for item in self.items:
            stream = stderr if item.status in ("VIOLATION", "NOT-RUN") else stdout
            stream.write("{0}[{1}]: {2}\n".format(item.status, item.name, item.detail))
        if self.exit_code == 0:
            stdout.write("DOCTOR-OK: all required dynamic checks evaluated and passed\n")
        elif self.exit_code == 2:
            stderr.write("DOCTOR-NOT-RUN: no known violation, but required coverage is incomplete\n")
        else:
            stderr.write("DOCTOR-FAILED: one or more known violations; incomplete rows do not mask them\n")
        return self.exit_code


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _clean_env(extra=None):
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env.pop("VIRTUAL_ENV", None)
    if extra:
        env.update(extra)
    return env


def _run(argv, cwd, input_text=None, timeout=60, env=None):
    try:
        return subprocess.run(
            [str(value) for value in argv], cwd=str(cwd), input=input_text,
            env=env or _clean_env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return exc


def _manifest_semantics(manifest):
    if not isinstance(manifest, dict):
        raise ValueError("manifest root is not an object")
    source = manifest.get("source")
    source_keys = (
        "url", "revision", "dirty", "exact_revision", "dirty_digest",
        "identity_inputs_digest", "modified_after_identity_capture", "dirty_digest_policy",
    )
    if not isinstance(source, dict) or any(key not in source for key in source_keys):
        raise ValueError("source identity is incomplete")
    entries = manifest.get("files")
    required = manifest.get("required_destinations")
    if not isinstance(entries, list) or not isinstance(required, list) or not required:
        raise ValueError("resource inventory is missing")
    destinations = [entry.get("destination") for entry in entries if isinstance(entry, dict)]
    if len(destinations) != len(entries) or len(destinations) != len(set(destinations)) or set(destinations) != set(required):
        raise ValueError("resource inventory is inconsistent")
    for entry in entries:
        destination = entry.get("destination")
        if (not isinstance(destination, str) or not destination or "\\" in destination
                or Path(destination).is_absolute() or ".." in Path(destination).parts):
            raise ValueError("unsafe resource destination")
        if entry.get("ownership") not in ("immutable", "editable-bootstrap", "generated-wiring"):
            raise ValueError("unknown ownership for {0}".format(entry.get("destination")))
        if not re.match(r"^[0-9a-f]{64}$", str(entry.get("sha256", ""))):
            raise ValueError("invalid resource hash for {0}".format(entry.get("destination")))
    license_identity = manifest.get("license")
    if license_identity != {"destination": "tools/omama/LICENSE", "expression": "MIT"}:
        raise ValueError("license identity is missing")
    basis = {
        "package_version": manifest.get("package_version"), "source": source,
        "license": license_identity,
        "files": [{key: entry[key] for key in ("destination", "ownership", "sha256")} for entry in entries],
        "generated_local": manifest.get("generated_local"),
        "ownership_policy": manifest.get("ownership_policy"),
    }
    actual = _sha(json.dumps(basis, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    if actual != manifest.get("bundle_id"):
        raise ValueError("bundle identity does not match manifest semantics")
    installed = manifest.get("installed_identity")
    if not isinstance(installed, dict) or installed.get("destination") != "tools/omama/manifest.json":
        raise ValueError("installed manifest identity is missing")
    return entries


def _load_installed_identity(target, package_bundle, state, report):
    path = target.root / "tools" / "omama" / "manifest.json"
    try:
        raw = path.read_bytes()
        manifest = json.loads(raw.decode("utf-8"))
        entries = _manifest_semantics(manifest)
    except FileNotFoundError:
        report.add("VIOLATION", "vendor-manifest", "installed manifest is missing")
        return None, {}, False
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        report.add("VIOLATION", "vendor-manifest", "installed manifest is invalid: {0}".format(exc))
        return None, {}, False
    trusted = True
    if not state or state.get("manifest_sha256") != _sha(raw):
        report.add("VIOLATION", "vendor-manifest", "installed manifest hash does not match local installation state")
        trusted = False
    else:
        report.add("OK", "vendor-manifest", "manifest semantics and state hash agree; local provenance is traceability, not cryptographic authenticity")
    if state and state.get("bundle_id") != manifest.get("bundle_id"):
        report.add("VIOLATION", "vendor-state", "recorded bundle does not match the installed manifest")
        trusted = False
    if package_bundle.manifest.get("bundle_id") != manifest.get("bundle_id"):
        report.add("WARNING", "package-bundle", "running CLI bundle differs from installed bundle; no update or corruption inference was made")
    else:
        report.add("OK", "package-bundle", "running CLI and installed bundle IDs agree")
    by_destination = {}
    for entry in entries:
        destination = entry["destination"]
        file_path = target.root / Path(destination)
        by_destination[destination] = entry
        try:
            info = file_path.lstat()
        except FileNotFoundError:
            if entry["ownership"] == "editable-bootstrap":
                report.add("WARNING", "editable-material", "editable bootstrap is absent/preserved: {0}".format(destination))
            else:
                report.add("VIOLATION", "immutable-missing", destination)
                trusted = False
            continue
        if file_path.is_symlink() or not stat.S_ISREG(info.st_mode):
            report.add("VIOLATION", "vendor-path", "installed destination is not a regular file: {0}".format(destination))
            trusted = False
            continue
        actual = _sha(file_path.read_bytes())
        if actual != entry["sha256"]:
            if entry["ownership"] == "editable-bootstrap":
                report.add("OK", "editable-drift", "team-owned bytes preserved: {0}".format(destination))
            else:
                report.add("VIOLATION", "immutable-drift", destination)
                trusted = False
    if trusted:
        report.add("OK", "vendor-identity", "all immutable/generated installed bytes match the recorded inventory")
    return manifest, by_destination, trusted


def _partial_state(target, context, report):
    found = []
    foreign = []
    for relative in (LOCK_REL, JOURNAL_REL):
        path = target.root / relative
        if not path.exists():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            owner = value.get("owner") if isinstance(value, dict) else None
        except Exception:
            owner = None
        found.append(relative)
        if context is None or owner != context.owner:
            foreign.append(relative)
    if foreign:
        report.add("VIOLATION", "partial-install", "unfinished or foreign owner state: {0}; recover before retrying".format(", ".join(foreign)))
        return False
    if found:
        report.add("OK", "partial-install", "private admission recognized only expected owner state: {0}".format(", ".join(found)))
    else:
        report.add("OK", "partial-install", "no unfinished lock or journal")
    return True


def _state(target, context, report):
    if context is not None:
        state = context.state
        if not isinstance(state, dict):
            report.add("VIOLATION", "installation-state", "private admission state is not an object")
            return None
    else:
        try:
            state = read_state(target)
        except InstallError as exc:
            report.add("VIOLATION", "installation-state", exc.message)
            return None
    if state is None:
        report.add("VIOLATION", "installation-state", "state is missing; run `omama init {0}`".format(target.root.as_posix()))
        return None
    if state.get("worktree_root") != target.root.as_posix():
        report.add("VIOLATION", "relocation", "recorded worktree root differs; rerun init in this checkout")
    else:
        report.add("OK", "relocation", "state is bound to this worktree root")
    status = state.get("status")
    if status == "complete" or (context is not None and status == "installing"):
        report.add("OK", "admission-state", "installation state is {0}".format(status))
    elif status == "prepared":
        report.add("NOT-RUN", "admission-state", "installation is prepared but mandatory admission has not completed")
    else:
        report.add("VIOLATION", "admission-state", "installation state is {0!r}".format(status))
    return state


def _scratch_directory(target, context, report):
    if context is None or context.scratch_root is None:
        return None, True
    root = Path(context.scratch_root)
    try:
        resolved = root.resolve()
        resolved.relative_to((target.root / ".omama").resolve())
    except (OSError, ValueError):
        report.add("VIOLATION", "admission-scratch", "private doctor scratch must stay below the target's .omama directory")
        return None, False
    if not root.is_dir() or root.is_symlink():
        report.add("VIOLATION", "admission-scratch", "private doctor scratch is missing or unsafe")
        return None, False
    report.add("OK", "admission-scratch", "private doctor probes are confined to target-owned transaction scratch")
    return resolved, True


def _settings(target, state, report):
    docs = {}
    gates = []
    siblings = []
    project_env = {}
    for relative in SETTINGS:
        try:
            doc, _raw = _read_json(target.root / relative, relative)
        except InstallError as exc:
            report.add("VIOLATION", "settings", exc.message)
            continue
        if doc is None:
            continue
        docs[relative] = doc
        if doc.get("disableAllHooks") is True:
            report.add("VIOLATION", "settings-disabled", "disableAllHooks is true in {0}".format(relative))
        env = doc.get("env")
        if env is not None and not isinstance(env, dict):
            report.add("VIOLATION", "settings-env", "env in {0} is not an object".format(relative))
        elif isinstance(env, dict):
            for key in MANAGED_ENV_KEYS + ("OMAMA_VERIFY_TIMEOUT",):
                if key in env:
                    project_env.setdefault(key, []).append((relative, env[key]))
        try:
            handlers = _stop_handlers(doc, relative)
        except InstallError as exc:
            report.add("VIOLATION", "settings", exc.message)
            continue
        for handler in handlers:
            if _mentions_gate(handler):
                gates.append((relative, handler))
            else:
                siblings.append((relative, handler))
    report.add("OK", "settings-siblings", "statically inspected {0} sibling Stop registration(s); none were selected for doctor execution".format(len(siblings)))
    for relative, sibling in siblings:
        if not isinstance(sibling, dict):
            report.add("WARNING", "settings-sibling", "non-object sibling in {0} is not a doctor execution candidate".format(relative))
        elif sibling.get("type") == "command":
            flags = [name for name in ("async", "asyncRewake", "args", "shell") if name in sibling]
            report.add("WARNING", "settings-sibling", "command sibling in {0} inspected only; fields={1}".format(relative, ",".join(flags) if flags else "plain"))
    expected = None
    try:
        expected = managed_command(state.get("receipt_interpreter", "")) if state else None
    except InstallError as exc:
        report.add("VIOLATION", "settings-command", exc.message)
    managed_gates = [
        (relative, handler) for relative, handler in gates
        if relative == LOCAL_SETTINGS and _compatible_gate(handler, expected)
    ]
    for relative, handler in gates:
        if (relative, handler) not in managed_gates:
            report.add("WARNING", "settings-gate-sibling", "gate-like sibling in {0} was statically inspected and will not be executed".format(relative))
    if len(gates) != 1:
        report.add("VIOLATION", "settings-command", "expected exactly one managed receipt gate, found {0}".format(len(gates)))
    elif gates[0][0] != LOCAL_SETTINGS:
        report.add("VIOLATION", "settings-command", "managed gate is not in ignored settings.local.json")
    elif not _compatible_gate(gates[0][1], expected):
        report.add("VIOLATION", "settings-command", "managed gate command/form differs from recorded certified command")
    elif state.get("settings_command") != expected:
        report.add("VIOLATION", "settings-command", "recorded command differs from the canonical interpreter/gate command")
    else:
        report.add("OK", "settings-command", "exactly one eligible synchronous local gate uses the recorded absolute interpreter")
    return docs, project_env, expected, bool(managed_gates)


def _environment(project_env, defaults, report):
    resolved = {}
    for key, default in defaults.items():
        entries = project_env.get(key, [])
        usable = [(source, value.strip()) for source, value in entries if isinstance(value, str) and value.strip()]
        if len({value for _source, value in usable}) > 1 or any(not isinstance(value, str) for _source, value in entries):
            report.add("VIOLATION", "environment-ambiguity", "project settings disagree or are unmodeled for {0}".format(key))
            resolved[key] = (None, "ambiguous")
            continue
        project = usable[-1] if usable else None
        process = os.environ.get(key)
        process = process.strip() if isinstance(process, str) and process.strip() else None
        if process and project and process != project[1]:
            report.add("VIOLATION", "environment-ambiguity", "process and project settings disagree for {0}".format(key))
            resolved[key] = (None, "ambiguous")
            continue
        if process:
            value, source = process, "process environment"
        elif project:
            value, source = project[1], "project setting " + project[0]
        else:
            value, source = default, "gate-relative default"
        resolved[key] = (value, source)
        report.add("OK", "environment-resolution", "{0} source: {1}".format(key, source))
        if key == "OMAMA_VERIFY_TIMEOUT":
            try:
                if float(value) <= 0:
                    raise ValueError()
            except (TypeError, ValueError):
                report.add("VIOLATION", "environment-timeout", "OMAMA_VERIFY_TIMEOUT is not a positive number")
    report.add("WARNING", "environment-boundary", "only project settings and this process environment are visible; user/managed/CLI-session settings are not claimed observable")
    return resolved


def _trusted_path(target, by_destination, destination):
    entry = by_destination.get(destination)
    path = target.root / destination
    if not entry or not path.is_file() or path.is_symlink():
        return None
    if _sha(path.read_bytes()) != entry.get("sha256"):
        return None
    return path


def _interpreter(target, state, report, static_only=False):
    if not state:
        return None
    raw = state.get("receipt_interpreter")
    if not isinstance(raw, str) or not Path(raw).is_absolute():
        report.add("VIOLATION", "interpreter", "recorded receipt interpreter is not absolute")
        return None
    path = Path(raw)
    if state.get("runtime_mode") == "managed":
        expected = target.root / ".omama" / "runtime"
        expected_interpreter = expected / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if path.absolute() != expected_interpreter.absolute():
            report.add("VIOLATION", "interpreter", "managed receipt interpreter is outside .omama/runtime")
            return None
    base = Path(str(state.get("base_interpreter", "")))
    if not base.is_file():
        report.add("VIOLATION", "base-interpreter", "recorded base interpreter is missing; rerun init with a durable Python")
    else:
        report.add("OK", "base-interpreter", "recorded effective base exists ({0} mode)".format(state.get("runtime_mode")))
    if static_only:
        if not path.is_file():
            report.add("VIOLATION", "interpreter-static", "recorded receipt interpreter is not an existing regular file")
            return None
        report.add("OK", "interpreter-static", "recorded receipt interpreter exists; execution was not attempted")
        report.add("NOT-RUN", "interpreter", "static-only skipped Python/PyYAML execution and version/import qualification")
        return path
    try:
        value = _probe(path, require_yaml=True)
    except InstallError as exc:
        report.add("VIOLATION", "interpreter", "{0}: {1}".format(exc.reason, exc.message))
        return None
    if str(value.get("pyyaml")) != str(state.get("pyyaml_version")):
        report.add("VIOLATION", "interpreter", "resolved PyYAML version differs from local state")
        return None
    report.add("OK", "interpreter", "Python {0}; PyYAML {1}; source=recorded receipt interpreter".format(".".join(str(x) for x in value["version"]), value["pyyaml"]))
    return path


def _probe_managed_gate(wiring_checker, expected_command, target, report):
    try:
        name = "_omama_installed_check_wiring_" + _sha(str(wiring_checker).encode("utf-8"))[:12]
        namespace = {"__name__": name, "__file__": str(wiring_checker)}
        source = wiring_checker.read_bytes()
        exec(compile(source, str(wiring_checker), "exec"), namespace)
        shell_reason = namespace["_git_bash_missing"]()
        violations = [shell_reason] if shell_reason else namespace["_check_command"](expected_command, str(target.root), False)
    except Exception as exc:
        report.add("VIOLATION", "settings-execution", "trusted installed wiring parser could not run: {0}".format(type(exc).__name__))
        return
    if violations:
        report.add("VIOLATION", "settings-execution", "managed gate failed certified parser/dynamic probe: {0}".format(violations[0]))
    else:
        report.add("OK", "settings-execution", "trusted installed certified parser executed only the identified managed gate; BAD-INPUT response verified")


def _probe_validator(interpreter, validator, scratch, report):
    valid = scratch / "valid-card.yaml"
    invalid = scratch / "invalid-card.yaml"
    valid.write_text(
        "goal: synthetic doctor validator probe\n"
        "non_goals:\n  - no target mutation\n"
        "tier: S1\ntask_type: implementation\n"
        "done_when:\n  - probe exits\n"
        "verify: 'python -c \"raise SystemExit(0)\"'\n",
        encoding="utf-8",
    )
    invalid.write_text("{}\n", encoding="utf-8")
    good = _run([interpreter, "-B", validator, valid], scratch)
    bad = _run([interpreter, "-B", validator, invalid], scratch)
    if isinstance(good, Exception) or isinstance(bad, Exception):
        report.add("VIOLATION", "validator-probe", "installed validator could not execute")
    elif good.returncode == 0 and bad.returncode == 1 and "VIOLATION:" in (bad.stderr or ""):
        report.add("OK", "validator-probe", "installed validator accepted valid synthetic card (0) and rejected invalid card (1)")
    else:
        report.add("VIOLATION", "validator-probe", "unexpected valid/invalid exits: {0}/{1}".format(good.returncode, bad.returncode))


def _probe_checker(interpreter, checker, scratch, report):
    valid = scratch / "valid-review.md"
    invalid = scratch / "malformed-review.md"
    valid.write_text(
        "# Synthetic review\n<!-- review v1 · tier: S -->\nVerdict: PASS\n"
        "## Findings\nNone.\n## Non-findings\n- No target data used.\n",
        encoding="utf-8",
    )
    invalid.write_text(
        "# Synthetic review\n<!-- review v1 · tier: S -->\nVerdict: PASS\n"
        "## Findings\nNone.\n",
        encoding="utf-8",
    )
    good = _run([interpreter, "-B", checker, "--budgets-advisory", valid], scratch)
    bad = _run([interpreter, "-B", checker, "--budgets-advisory", invalid], scratch)
    bad_output = "" if isinstance(bad, Exception) else (bad.stdout or "") + (bad.stderr or "")
    if isinstance(good, Exception) or isinstance(bad, Exception):
        report.add("VIOLATION", "checker-probe", "installed S3 checker could not execute")
    elif good.returncode == 0 and bad.returncode == 1 and "missing-non-findings" in bad_output:
        report.add("OK", "checker-probe", "installed checker with --budgets-advisory accepted valid review (0) and rejected malformed S3 review for missing-non-findings (1)")
    else:
        report.add("VIOLATION", "checker-probe", "unexpected valid/malformed exits: {0}/{1}".format(good.returncode, bad.returncode))


def _bash_path():
    if os.name != "nt":
        return shutil.which("sh")
    knob = os.environ.get("CLAUDE_CODE_GIT_BASH_PATH")
    if knob and Path(knob).is_file():
        return knob
    candidates = []
    git = shutil.which("git")
    if git:
        directory = Path(git).resolve().parent
        candidates.extend([directory.parent / "bin" / "bash.exe", directory.parent.parent / "bin" / "bash.exe"])
    for name in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "LocalAppData"):
        base = os.environ.get(name)
        if base:
            candidates.extend([Path(base) / "Git" / "bin" / "bash.exe", Path(base) / "Programs" / "Git" / "bin" / "bash.exe"])
    return str(next((path for path in candidates if path.is_file()), "")) or None


def _privacy(target, by_destination, interpreter, static_only, scratch, report, base_trusted=True):
    value = _git_config_value(target)
    candidate = Path(value) if value else None
    if candidate is not None and not candidate.is_absolute():
        candidate = target.root / candidate
    if candidate is None or candidate.resolve() != (target.root / ".githooks").resolve():
        report.add("VIOLATION", "privacy-hooks-path", "effective core.hooksPath is not .githooks")
    else:
        report.add("OK", "privacy-hooks-path", "effective core.hooksPath resolves to this worktree's .githooks")
    required = {
        ".githooks/pre-commit": "generated-wiring",
        ".githooks/pre-merge-commit": "generated-wiring",
        ".githooks/privacy-pre-commit": "immutable",
        "tools/omama/privacy-hook/scan_staged.py": "immutable",
    }
    privacy_trusted = bool(base_trusted)
    for destination in required:
        path = _trusted_path(target, by_destination, destination)
        if path is None:
            privacy_trusted = False
            report.add("VIOLATION", "privacy-component", "missing or drifted: {0}".format(destination))
            continue
        data = path.read_bytes()
        if destination.startswith(".githooks/") and (b"\r\n" in data or not data.endswith(b"\n")):
            privacy_trusted = False
            report.add("VIOLATION", "privacy-mode", "hook is not LF/terminal-newline clean: {0}".format(destination))
        elif os.name != "nt" and destination.startswith(".githooks/") and not (path.stat().st_mode & 0o111):
            privacy_trusted = False
            report.add("VIOLATION", "privacy-mode", "hook is not executable: {0}".format(destination))
    if privacy_trusted:
        report.add("OK", "privacy-components", "both chainers, wrapper and scanner match installed identity; LF/mode checks passed for this OS")

    config = target.root / "privacy-deny.json"
    token = None
    try:
        doc = json.loads(config.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            raise ValueError("root is not an object")
        for row in doc.get("deny_regexes", []):
            if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not isinstance(row.get("pattern"), str):
                raise ValueError("bad deny_regexes entry")
            re.compile(row["pattern"])
        for pattern in doc.get("deny_filenames", []):
            if not isinstance(pattern, str):
                raise ValueError("bad deny_filenames entry")
            re.compile(pattern)
        token = doc.get("tokens_file")
        if token is not None and (not isinstance(token, str) or not token.strip()):
            raise ValueError("tokens_file is neither null/omitted nor a path")
        report.add("OK", "privacy-config", "privacy config is readable and regex entries compile")
    except (OSError, UnicodeDecodeError, ValueError, re.error) as exc:
        report.add("VIOLATION", "privacy-config", "privacy-deny.json is invalid: {0}".format(type(exc).__name__))
    if isinstance(token, str):
        token_path = target.root / token
        try:
            token_path.resolve().relative_to(target.root.resolve())
        except ValueError:
            report.add("VIOLATION", "token-state", "configured token path escapes the worktree")
        else:
            if token_path.is_symlink():
                report.add("VIOLATION", "token-state", "configured token file is a symlink; use an in-repository regular file")
                token_path = target.root / ".omama" / "refused-token-symlink"
            try:
                lines = token_path.read_text(encoding="utf-8").splitlines()
            except FileNotFoundError:
                report.add("VIOLATION", "token-state", "configured token file is missing at {0}; create the gitignored file (comment-only is allowed) or set tokens_file=null".format(token))
            except (OSError, UnicodeDecodeError):
                report.add("VIOLATION", "token-state", "configured token file is unreadable")
            else:
                count = sum(1 for line in lines if line.strip() and not line.lstrip().startswith("#"))
                if count:
                    report.add("OK", "token-state", "configured token file is populated ({0} literal line(s)); values not displayed".format(count))
                else:
                    report.add("WARNING", "token-state", "configured token file has zero literals; fill it or set tokens_file=null explicitly")
    elif token is None:
        report.add("OK", "token-state", "literal token layer is deliberately disabled by null/omitted configuration")

    if static_only:
        report.add("NOT-RUN", "privacy-interpreter", "static-only skipped execution of the trusted wrapper interpreter route")
    elif not privacy_trusted:
        report.add("NOT-RUN", "privacy-interpreter", "wrapper route skipped because installed privacy identity is not trusted")
    else:
        shell = _bash_path()
        if not shell:
            report.add("NOT-RUN", "privacy-interpreter", "required sh/Git Bash route could not be established")
        else:
            probe = scratch / "privacy-interpreter-probe.py"
            probe.write_text("import json,sys;print(json.dumps({'executable':sys.executable,'version':list(sys.version_info[:3])},sort_keys=True))\n", encoding="utf-8")
            env = _clean_env({"PRIVACY_HOOK_SCANNER": probe.as_posix()})
            result = _run([shell, "-c", "exec sh .githooks/privacy-pre-commit"], target.root, env=env)
            try:
                value = json.loads(result.stdout.strip()) if not isinstance(result, Exception) else None
            except ValueError:
                value = None
            if (not isinstance(result, Exception) and result.returncode == 0
                    and isinstance(value, dict) and tuple(value.get("version", ())) >= (3, 8)):
                report.add("OK", "privacy-interpreter", "wrapper-selected Python {0}; receipt runtime remains independently selected".format(".".join(str(x) for x in value["version"])))
            else:
                report.add("VIOLATION", "privacy-interpreter", "trusted wrapper could not select a runnable Python >=3.8")


def doctor(target, package_bundle, static_only=False, context=None):
    report = DoctorReport()
    partial_ok = _partial_state(target, context, report)
    state = _state(target, context, report)
    scratch_directory, scratch_ok = _scratch_directory(target, context, report)
    manifest, by_destination, vendor_trusted = _load_installed_identity(target, package_bundle, state, report)
    docs, project_env, expected_command, managed_gate_identified = _settings(target, state, report)
    defaults = {
        "OMAMA_VALIDATOR": str(target.root / "tools" / "omama" / "work-order" / "validate_work_order.py"),
        "OMAMA_CHECK_ARTIFACT": str(target.root / "tools" / "omama" / "output-discipline" / "scripts" / "check_artifact.py"),
        "OMAMA_CARD": str(target.root / "CARD.yaml"),
        "OMAMA_VERIFY_TIMEOUT": "600",
    }
    resolutions = _environment(project_env, defaults, report)
    card_value, card_source = resolutions.get("OMAMA_CARD", (None, "ambiguous"))
    if card_value is not None:
        card_path = Path(card_value)
        if not card_path.is_absolute():
            card_path = target.root / card_path
        if card_path.resolve() != (target.root / "CARD.yaml").resolve():
            report.add("VIOLATION", "card-resolution", "OMAMA_CARD resolves outside this worktree's active card (source={0})".format(card_source))
        else:
            report.add("OK", "card-resolution", "OMAMA_CARD resolves to this worktree's card (source={0})".format(card_source))
    interpreter = _interpreter(target, state, report, static_only=static_only)
    if state and state.get("runtime_mode") == "managed":
        runtime = target.root / ".omama" / "runtime"
        if runtime.is_dir():
            report.add("OK", "clone-worktree", "managed runtime and local state exist in this worktree; base-Python and relocation remain explicit dependencies")
        else:
            report.add("VIOLATION", "clone-worktree", "managed runtime is absent; rerun init in this clone/worktree")
    elif state:
        report.add("OK", "clone-worktree", "explicit interpreter state exists for this worktree; re-check after clone/relocation")

    validator = _trusted_path(target, by_destination, "tools/omama/work-order/validate_work_order.py")
    checker = _trusted_path(target, by_destination, "tools/omama/output-discipline/scripts/check_artifact.py")
    wiring_checker = _trusted_path(target, by_destination, "tools/omama/receipt-gate/adapt/check_wiring.py")
    gate = _trusted_path(target, by_destination, "tools/omama/receipt-gate/receipt_gate.py")
    expected_paths = {
        "OMAMA_VALIDATOR": validator,
        "OMAMA_CHECK_ARTIFACT": checker,
    }
    resolution_trusted = True
    for key, expected in expected_paths.items():
        value, source = resolutions.get(key, (None, "ambiguous"))
        if value is None or expected is None:
            resolution_trusted = False
            report.add("VIOLATION", "dependency-resolution", "{0} is unavailable or ambiguous (source={1})".format(key, source))
            continue
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = target.root / candidate
        if candidate.resolve() != expected.resolve():
            resolution_trusted = False
            report.add("VIOLATION", "dependency-resolution", "{0} resolves outside the trusted installed identity (source={1})".format(key, source))
        else:
            report.add("OK", "dependency-resolution", "{0} resolves to trusted installed bytes (source={1})".format(key, source))

    if static_only:
        report.add("NOT-RUN", "settings-execution", "static-only skipped installed check_wiring and gate BAD-INPUT execution")
        report.add("NOT-RUN", "validator-probe", "static-only skipped valid/invalid validator execution")
        report.add("NOT-RUN", "checker-probe", "static-only skipped valid/malformed checker execution")
        scratch_parent = None
    elif not (partial_ok and scratch_ok and state and vendor_trusted and interpreter and wiring_checker and gate and resolution_trusted and expected_command and managed_gate_identified):
        report.add("NOT-RUN", "settings-execution", "dynamic gate check skipped because trusted prerequisites failed")
        report.add("NOT-RUN", "validator-probe", "validator execution skipped because trusted prerequisites failed")
        report.add("NOT-RUN", "checker-probe", "checker execution skipped because trusted prerequisites failed")
        scratch_parent = None
    else:
        _probe_managed_gate(wiring_checker, expected_command, target, report)
        scratch_parent = tempfile.TemporaryDirectory(
            prefix="omama-doctor-", dir=str(scratch_directory) if scratch_directory else None)
        scratch = Path(scratch_parent.name)
        _probe_validator(interpreter, validator, scratch, report)
        _probe_checker(interpreter, checker, scratch, report)

    if scratch_parent is not None:
        scratch_parent.cleanup()
    if static_only or not scratch_ok:
        _privacy(target, by_destination, interpreter, True, target.root, report, vendor_trusted)
    else:
        with tempfile.TemporaryDirectory(
                prefix="omama-doctor-privacy-",
                dir=str(scratch_directory) if scratch_directory else None) as privacy_temp:
            _privacy(target, by_destination, interpreter, False, Path(privacy_temp), report, vendor_trusted)
    return report
