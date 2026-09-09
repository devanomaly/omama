"""Conflict-safe project settings, privacy bootstrap, ignore, and Git activation."""

import fnmatch
import hashlib
import json
import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .install import (
    FileOperation, InstallError, _ensure_writable_destination, _snapshot_file,
)
from .target import TargetError, safe_destination, validate_command_path


SETTINGS = (".claude/settings.json", ".claude/settings.local.json")
LOCAL_SETTINGS = ".claude/settings.local.json"
GITIGNORE = ".gitignore"
MANAGED_ENV_KEYS = ("OMAMA_CARD", "OMAMA_VALIDATOR", "OMAMA_CHECK_ARTIFACT")
TOKEN_BOOTSTRAP = b"# Add one private literal per line; keep this file gitignored.\n"


@dataclass
class WiringPlan:
    command: str
    operations: list
    ignore_paths: list
    activation_required: bool
    no_git_config: bool
    activation_remedy: str
    config_before: dict
    state_extra: dict


def managed_command(interpreter):
    path = Path(interpreter)
    if not path.is_absolute():
        raise InstallError("interpreter-not-absolute", "receipt interpreter must be absolute")
    validate_command_path(path)
    value = path.as_posix()
    if '"' in value:
        raise InstallError("unsupported-command-path", "interpreter path contains a quote and cannot use the certified command grammar")
    return '"{0}" "$CLAUDE_PROJECT_DIR/tools/omama/receipt-gate/receipt_gate.py"'.format(value)


def _read_json(path, relative):
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None, None
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise InstallError("settings-not-json", "{0} is not valid UTF-8 JSON: {1}".format(relative, type(exc).__name__))
    if not isinstance(doc, dict):
        raise InstallError("settings-shape", "{0} root must be a JSON object".format(relative))
    return doc, raw


def _stop_handlers(doc, relative):
    hooks = doc.get("hooks")
    if hooks is None:
        return []
    if not isinstance(hooks, dict):
        raise InstallError("settings-hooks-shape", "hooks in {0} must be an object".format(relative))
    stop = hooks.get("Stop")
    if stop is None:
        return []
    if not isinstance(stop, list):
        raise InstallError("settings-hooks-shape", "hooks.Stop in {0} must be a list".format(relative))
    handlers = []
    for matcher in stop:
        if not isinstance(matcher, dict) or not isinstance(matcher.get("hooks"), list):
            raise InstallError("settings-hooks-shape", "each Stop matcher in {0} must contain a hooks list".format(relative))
        handlers.extend(matcher["hooks"])
    return handlers


def _mentions_gate(value):
    if isinstance(value, str):
        return "receipt_gate.py" in value.replace("\\", "/").lower()
    if isinstance(value, dict):
        return any(_mentions_gate(item) for item in value.values())
    if isinstance(value, list):
        return any(_mentions_gate(item) for item in value)
    return False


def _compatible_gate(handler, command):
    return (
        isinstance(handler, dict)
        and handler.get("type") == "command"
        and handler.get("command") == command
        and "args" not in handler
        and not handler.get("async")
        and not handler.get("asyncRewake")
        and handler.get("shell") in (None, "bash")
    )


def _settings_plan(target, command):
    docs = {}
    existing_gate = []
    for relative in SETTINGS:
        doc, _raw = _read_json(target.root / relative, relative)
        if doc is None:
            continue
        docs[relative] = doc
        if doc.get("disableAllHooks") is True:
            raise InstallError("settings-hooks-disabled", "disableAllHooks is true in {0}".format(relative))
        env = doc.get("env")
        if isinstance(env, dict):
            overrides = sorted(key for key in MANAGED_ENV_KEYS if key in env)
            if overrides:
                raise InstallError("settings-omama-override", "{0} defines managed override(s): {1}".format(relative, ", ".join(overrides)))
        for handler in _stop_handlers(doc, relative):
            if _mentions_gate(handler):
                if relative != LOCAL_SETTINGS:
                    raise InstallError("settings-gate-conflict", "receipt gate must be machine-local, not registered in {0}".format(relative))
                if not _compatible_gate(handler, command):
                    raise InstallError("settings-gate-conflict", "existing receipt gate is disabled, async, unsupported, or uses a different command")
                existing_gate.append(handler)
    if len(existing_gate) > 1:
        raise InstallError("settings-gate-duplicate", "more than one eligible managed receipt gate is registered")
    local = docs.get(LOCAL_SETTINGS, {})
    if existing_gate:
        return local, False
    hooks = local.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise InstallError("settings-hooks-shape", "hooks in local settings must be an object")
    stop = hooks.setdefault("Stop", [])
    if not isinstance(stop, list):
        raise InstallError("settings-hooks-shape", "hooks.Stop in local settings must be a list")
    stop.append({"hooks": [{"type": "command", "command": command}]})
    return local, True


def _decode_gitignore(path):
    try:
        return path.read_bytes().decode("utf-8")
    except FileNotFoundError:
        return ""
    except UnicodeDecodeError:
        raise InstallError("gitignore-not-utf8", ".gitignore is not UTF-8 and cannot be merged safely")


def _negation_may_match(base, line, target_relative):
    pattern = line[1:].strip()
    if not pattern or pattern.startswith("#"):
        return False
    relative = Path(target_relative).as_posix()
    try:
        scoped = Path(relative).relative_to(base).as_posix() if str(base) != "." else relative
    except ValueError:
        return False
    pattern = pattern.lstrip("/")
    if pattern.endswith("/"):
        return scoped == pattern[:-1] or scoped.startswith(pattern)
    if "/" not in pattern:
        return any(fnmatch.fnmatch(part, pattern) for part in Path(scoped).parts)
    return fnmatch.fnmatch(scoped, pattern)


def _check_nested_negations(root, paths):
    for relative in paths:
        parent = (root / relative).parent
        while parent != root and root in parent.parents:
            ignore = parent / ".gitignore"
            if ignore.is_file():
                text = _decode_gitignore(ignore)
                base = parent.relative_to(root)
                for line in text.splitlines():
                    if line.lstrip().startswith("!") and _negation_may_match(base, line.lstrip(), relative):
                        raise InstallError("ignore-negation-conflict", "nested ignore negation may re-include sensitive path {0}: {1}".format(relative, ignore.relative_to(root).as_posix()))
            parent = parent.parent


def _tracked(target, relative):
    result = subprocess.run(
        ["git", "-C", str(target.root), "ls-files", "--error-unmatch", "--", relative],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    return result.returncode == 0


def _operation(root, relative, data, default_mode):
    path = safe_destination(root, relative)
    _ensure_writable_destination(root, path, relative)
    before = _snapshot_file(path, include_bytes=True)
    if before["kind"] == "other":
        raise InstallError("unsafe-destination", "generated destination is not a regular file: {0}".format(relative))
    mode = before.get("mode", default_mode)
    if before.get("sha256") == hashlib.sha256(data).hexdigest():
        return None
    return FileOperation(relative, data, mode, before)


def _privacy_config(plan):
    root = plan.target.root
    path = root / "privacy-deny.json"
    if path.is_file():
        raw = path.read_bytes()
    else:
        entry = next(item for item in plan.bundle.manifest["files"] if item["destination"] == "privacy-deny.json")
        raw = plan.bundle.files[entry["resource"]]
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise InstallError("privacy-config-invalid", "privacy-deny.json is not valid UTF-8 JSON")
    if not isinstance(doc, dict):
        raise InstallError("privacy-config-invalid", "privacy-deny.json root must be an object")
    token = doc.get("tokens_file")
    if token is None:
        return None
    if not isinstance(token, str) or not token.strip() or "\\" in token:
        raise InstallError("unsafe-tokens-path", "tokens_file must be null/omitted or a nonempty forward-slash relative path")
    try:
        safe_destination(root, token)
    except TargetError as exc:
        raise InstallError("unsafe-tokens-path", exc.message)
    return Path(token).as_posix()


def _git_config_value(target):
    result = subprocess.run(
        ["git", "-C", str(target.root), "config", "--includes", "--get", "core.hooksPath"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", check=False,
    )
    if result.returncode == 1:
        return None
    if result.returncode != 0:
        raise InstallError("git-config-inspection", "cannot inspect local core.hooksPath")
    return result.stdout.strip()


def _effective_hooks_directory(target):
    result = subprocess.run(
        ["git", "-C", str(target.root), "rev-parse", "--git-path", "hooks"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise InstallError("git-config-inspection", "cannot resolve the currently effective hooks directory")
    path = Path(result.stdout.strip())
    if not path.is_absolute():
        path = target.root / path
    return path.resolve()


def _active_hooks(directory):
    if not directory.is_dir():
        return []
    active = []
    for path in directory.iterdir():
        if path.name.endswith(".sample"):
            continue
        try:
            info = path.lstat()
        except OSError:
            active.append(path.name)
            continue
        if path.is_symlink() or (stat.S_ISREG(info.st_mode) and info.st_size > 0 and (os.name == "nt" or info.st_mode & 0o111)):
            active.append(path.name)
    return sorted(active)


def _activation_plan(target):
    value = _git_config_value(target)
    expected = (target.root / ".githooks").resolve()
    if value:
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = target.root / candidate
        if candidate.resolve() != expected:
            active = _active_hooks(_effective_hooks_directory(target))
            detail = "; active hook(s): " + ", ".join(active) if active else ""
            raise InstallError("hooks-path-conflict", "effective core.hooksPath would be replaced: {0}{1}".format(value, detail))
        return False, None, _snapshot_file(target.common_dir / "config", include_bytes=True)
    if target.linked_worktree:
        main = target.common_dir.parent
        remedy = 'git -C "{0}" config --local core.hooksPath .githooks'.format(main.as_posix())
        raise InstallError("linked-worktree-config", "linked worktree cannot enable shared core.hooksPath; run from the main checkout first: {0}".format(remedy))
    config_path = (target.common_dir / "config").resolve()
    try:
        config_path.relative_to(target.root.resolve())
    except ValueError:
        raise InstallError(
            "unsupported-git-config",
            "core.hooksPath activation would write outside the worktree; phase 1 does not activate separate Git directories",
        )
    displaced = _active_hooks(_effective_hooks_directory(target))
    if displaced:
        raise InstallError("hooks-displacement", "activation would displace active hook(s): {0}; integrate them manually before init".format(", ".join(displaced)))
    remedy = 'git -C "{0}" config --local core.hooksPath .githooks'.format(target.root.as_posix())
    return True, remedy, _snapshot_file(target.common_dir / "config", include_bytes=True)


def preflight_wiring(plan, interpreter, no_git_config=False):
    target = plan.target
    command = managed_command(interpreter)
    local, settings_changed = _settings_plan(target, command)
    token = _privacy_config(plan)
    sensitive = [LOCAL_SETTINGS, ".omama/state.json", ".omama/install-journal.json", ".omama/install.lock"]
    if token:
        sensitive.append(token)
    tracked_omama = subprocess.run(
        ["git", "-C", str(target.root), "ls-files", "--", ".omama"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", check=False,
    )
    if tracked_omama.returncode != 0:
        raise InstallError("git-inspection", "cannot inspect tracked .omama paths")
    if tracked_omama.stdout.strip():
        raise InstallError("tracked-local-state", "tracked content exists below .omama; untrack it before init")
    for relative in sensitive:
        if _tracked(target, relative):
            raise InstallError("tracked-local-state", "sensitive/local path is tracked: {0}".format(relative))

    ignore_paths = [
        "CARD.yaml", "CARD.close", "CARD.review.md", "CARD.receipt.json",
        "fixture.receipt.json", LOCAL_SETTINGS, ".omama/state.json",
    ]
    if token:
        ignore_paths.append(token)
    _check_nested_negations(target.root, ignore_paths)
    ignore_lines = [
        "CARD.yaml", "CARD.close", "CARD.review.md", "CARD.receipt.json",
        "*.receipt.json", LOCAL_SETTINGS, ".omama/",
    ] + ([token] if token else [])
    current_ignore = _decode_gitignore(target.root / GITIGNORE)
    present = {line.strip() for line in current_ignore.splitlines() if line.strip() and not line.lstrip().startswith("#")}
    missing = [line for line in ignore_lines if line not in present]
    merged_ignore = current_ignore
    if missing:
        if merged_ignore and not merged_ignore.endswith("\n"):
            merged_ignore += "\n"
        merged_ignore += ("\n" if merged_ignore else "") + "# Omama local state and evidence\n" + "\n".join(missing) + "\n"

    operations = []
    if settings_changed:
        settings_bytes = (json.dumps(local, indent=2, ensure_ascii=True) + "\n").encode("utf-8")
        operation = _operation(target.root, LOCAL_SETTINGS, settings_bytes, 0o600)
        if operation:
            operations.append(operation)
    operation = _operation(target.root, GITIGNORE, merged_ignore.encode("utf-8"), 0o644)
    if operation:
        operations.append(operation)
    token_state = "disabled"
    if token:
        token_path = target.root / token
        if token_path.exists():
            if not token_path.is_file():
                raise InstallError("unsafe-tokens-path", "tokens_file is not a regular file: {0}".format(token))
            token_state = "present"
        elif plan.existing_state and plan.existing_state.get("tokens_file") == token:
            token_state = "missing-preserved"
        else:
            operation = _operation(target.root, token, TOKEN_BOOTSTRAP, 0o600)
            if operation:
                operations.append(operation)
            token_state = "comment-only-bootstrap"

    activation_required, remedy, config_before = _activation_plan(target)
    state_extra = {
        "settings_command": command,
        "settings_path": LOCAL_SETTINGS,
        "hooks_path": ".githooks",
        "activation_status": "manual-required" if activation_required and no_git_config else "active",
        "tokens_file": token,
        "token_state_at_init": token_state,
        "managed_omama_overrides": [],
    }
    return WiringPlan(
        command, operations, ignore_paths, activation_required,
        bool(no_git_config), remedy, config_before, state_extra,
    )


def attach_wiring(plan, wiring):
    plan.operations.extend(wiring.operations)


def finish_wiring(transaction, wiring):
    for relative in wiring.ignore_paths:
        result = subprocess.run(
            ["git", "-C", str(transaction.plan.target.root), "check-ignore", "--no-index", "--quiet", "--", relative],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        if result.returncode != 0:
            raise InstallError("ignore-ineffective", "required local/sensitive path is not effectively ignored: {0}".format(relative))
    for relative in (".githooks/pre-commit", ".githooks/pre-merge-commit", ".githooks/privacy-pre-commit"):
        if not (transaction.plan.target.root / relative).is_file():
            raise InstallError("privacy-wiring-incomplete", "required privacy hook is missing before activation: {0}".format(relative))
    if wiring.activation_required and not wiring.no_git_config:
        transaction.activate_hooks_path(wiring.config_before)
        value = _git_config_value(transaction.plan.target)
        candidate = Path(value) if value else None
        if candidate is not None and not candidate.is_absolute():
            candidate = transaction.plan.target.root / candidate
        if candidate is None or candidate.resolve() != (transaction.plan.target.root / ".githooks").resolve():
            raise InstallError("git-config-activation", "core.hooksPath is not effectively .githooks after activation")
