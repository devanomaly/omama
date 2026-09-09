"""Finite, target-owned publication and conditional recovery for ``omama init``."""

import base64
import hashlib
import json
import os
import shutil
import stat
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from .identity import ExistingState, classify_existing
from .target import TargetError, ensure_no_reparse, safe_destination


STATE_REL = ".omama/state.json"
JOURNAL_REL = ".omama/install-journal.json"
LOCK_REL = ".omama/install.lock"
MANIFEST_REL = "tools/omama/manifest.json"
STATE_SCHEMA = 1


class InstallError(RuntimeError):
    def __init__(self, reason, message, incomplete=False):
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.incomplete = incomplete


@dataclass(frozen=True)
class FileOperation:
    relative: str
    data: bytes
    mode: int
    before: dict


@dataclass
class InstallPlan:
    target: object
    bundle: object
    operations: list
    state: dict
    state_before: dict
    protected: dict
    existing_state: dict = None


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _snapshot_file(path, include_bytes=True):
    path = Path(path)
    try:
        info = path.lstat()
    except FileNotFoundError:
        return {"kind": "missing"}
    if path.is_symlink() or not stat.S_ISREG(info.st_mode):
        return {"kind": "other", "mode": stat.S_IMODE(info.st_mode)}
    data = path.read_bytes()
    value = {
        "kind": "file", "sha256": _sha(data), "size": len(data),
        "mode": stat.S_IMODE(info.st_mode),
    }
    if include_bytes:
        value["bytes_b64"] = base64.b64encode(data).decode("ascii")
    return value


def _tree_digest(path):
    root = Path(path)
    if not root.is_dir() or root.is_symlink():
        return None
    digest = hashlib.sha256()
    for current, directories, files in os.walk(str(root), topdown=True, followlinks=False):
        current_path = Path(current)
        names = sorted(directories + files)
        for name in names:
            item = current_path / name
            relative = item.relative_to(root).as_posix()
            try:
                info = item.lstat()
            except OSError:
                return None
            if item.is_symlink():
                kind = "symlink"
                content = os.readlink(str(item)).encode("utf-8", "surrogateescape")
                if name in directories:
                    directories.remove(name)
            elif stat.S_ISDIR(info.st_mode):
                kind = "directory"
                content = b""
            elif stat.S_ISREG(info.st_mode):
                kind = "file"
                try:
                    content = item.read_bytes()
                except OSError:
                    return None
            else:
                kind = "other"
                content = b""
            digest.update(relative.encode("utf-8") + b"\0" + kind.encode("ascii") + b"\0")
            digest.update(str(stat.S_IMODE(info.st_mode)).encode("ascii") + b"\0")
            digest.update(hashlib.sha256(content).digest())
    return digest.hexdigest()


def _same_snapshot(path, before):
    current = _snapshot_file(path, include_bytes=False)
    return all(current.get(key) == before.get(key) for key in ("kind", "sha256", "size", "mode"))


def _protected_snapshot(target):
    root = target.root
    paths = {
        "index": target.index_path,
        "CARD.yaml": root / "CARD.yaml",
        "CARD.close": root / "CARD.close",
        "CARD.review.md": root / "CARD.review.md",
        "CARD.receipt.json": root / "CARD.receipt.json",
    }
    for receipt in root.glob("*.receipt.json"):
        paths["receipt:" + receipt.name] = receipt
    return {name: _snapshot_file(path, include_bytes=False) for name, path in paths.items()}


def _git(target, *args):
    import subprocess
    result = subprocess.run(
        ["git", "-C", str(target.root)] + list(args),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise InstallError("git-inspection", "git {0} failed: {1}".format(args[0], detail[-1][:300] if detail else "no diagnostic"))
    return result.stdout.strip()


def _tracked(target, relative):
    result = __import__("subprocess").run(
        ["git", "-C", str(target.root), "ls-files", "--error-unmatch", "--", relative],
        stdout=__import__("subprocess").PIPE, stderr=__import__("subprocess").PIPE,
        check=False,
    )
    return result.returncode == 0


def read_state(target):
    path = target.root / STATE_REL
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise InstallError("invalid-install-state", "cannot parse {0}: {1}".format(STATE_REL, type(exc).__name__))
    if not isinstance(value, dict) or value.get("schema") != STATE_SCHEMA:
        raise InstallError("invalid-install-state", "unsupported or malformed {0}".format(STATE_REL))
    return value


def _expected_mode(destination):
    return 0o755 if destination.startswith(".githooks/") else 0o644


def _ensure_writable_destination(root, path, relative):
    candidate = Path(path)
    current = candidate if candidate.exists() else candidate.parent
    while not current.exists() and current != Path(root):
        current = current.parent
    mode = stat.S_IMODE(current.stat().st_mode)
    if not (mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)):
        raise InstallError("read-only-destination", "destination is read-only: {0}".format(relative))


def preflight_bundle(target, bundle):
    if (target.root / "CARD.close").exists():
        raise InstallError("active-close", "CARD.close is active; finish or remove the close attempt before init")
    for relative in (STATE_REL, JOURNAL_REL, LOCK_REL, ".claude/settings.local.json"):
        if _tracked(target, relative):
            raise InstallError("tracked-local-state", "local installer/settings path is tracked: {0}; untrack it before init".format(relative))
    if (target.root / JOURNAL_REL).exists():
        raise InstallError("unfinished-install", "unfinished journal exists at {0}; recover it before retrying".format(JOURNAL_REL))
    if (target.root / LOCK_REL).exists():
        raise InstallError("installer-locked", "installer lock already exists at {0}; no stale-lock theft is attempted".format(LOCK_REL))

    state = read_state(target)
    current_bundle = bundle.manifest["bundle_id"]
    recorded_bundle = state.get("bundle_id") if state else None
    # This must precede per-file MISSING classification: missing bytes never
    # turn a different recorded bundle into implicit update permission.
    if recorded_bundle is not None and recorded_bundle != current_bundle:
        raise InstallError(
            "package-update",
            "installed bundle {0} differs from selected bundle {1}; phase 1 does not update implicitly"
            .format(recorded_bundle, current_bundle),
        )
    if state and state.get("status") not in ("prepared", "complete"):
        raise InstallError("unfinished-install", "installation state is {0!r}, not prepared/complete".format(state.get("status")))

    operations = []
    file_state = {}
    entries = list(bundle.manifest["files"])
    for entry in entries:
        destination = entry["destination"]
        path = safe_destination(target.root, destination)
        _ensure_writable_destination(target.root, path, destination)
        before = _snapshot_file(path, include_bytes=True)
        if before["kind"] == "other":
            raise InstallError("unsafe-destination", "destination is not a regular file: {0}".format(destination))
        existing = path.read_bytes() if before["kind"] == "file" else None
        classification = classify_existing(bundle, entry, existing, recorded_bundle)
        ownership = entry["ownership"]
        disposition = classification.value
        write = False
        if classification == ExistingState.MISSING:
            # Editable bootstrap files become team-owned after first creation.
            # A later deletion is preserved rather than silently repaired.
            write = not (state is not None and ownership == "editable-bootstrap")
            if not write:
                disposition = "editable-missing-preserved"
        elif classification in (ExistingState.ADOPTABLE_IDENTICAL, ExistingState.SAME_BUNDLE):
            pass
        elif classification == ExistingState.EDITABLE_PRESERVE:
            pass
        elif classification == ExistingState.PACKAGE_UPDATE:
            raise InstallError("package-update", "different bundle requires an explicit future update: {0}".format(destination))
        elif classification == ExistingState.GENERATED_DRIFT:
            raise InstallError("generated-wiring-conflict", "generated hook differs from this bundle: {0}".format(destination))
        else:
            raise InstallError("immutable-conflict", "immutable or unowned file differs from this bundle: {0}".format(destination))
        if write:
            operations.append(FileOperation(destination, bundle.files[entry["resource"]], _expected_mode(destination), before))
        file_state[destination] = {
            "ownership": ownership,
            "expected_sha256": entry["sha256"],
            "observed_sha256": before.get("sha256"),
            "disposition": disposition,
        }

    manifest_path = safe_destination(target.root, MANIFEST_REL)
    _ensure_writable_destination(target.root, manifest_path, MANIFEST_REL)
    manifest_before = _snapshot_file(manifest_path, include_bytes=True)
    if manifest_before["kind"] == "other":
        raise InstallError("unsafe-destination", "manifest destination is not a regular file")
    if manifest_before["kind"] == "missing":
        operations.append(FileOperation(MANIFEST_REL, bundle.manifest_bytes, 0o644, manifest_before))
        manifest_disposition = "missing"
    elif manifest_before.get("sha256") == _sha(bundle.manifest_bytes):
        manifest_disposition = "same-bundle" if state else "adoptable-identical"
    else:
        raise InstallError("immutable-conflict", "installed manifest differs from the selected validated bundle")

    install_state = {
        "schema": STATE_SCHEMA,
        "status": "installing",
        "bundle_id": current_bundle,
        "package_version": bundle.manifest["package_version"],
        "manifest_sha256": _sha(bundle.manifest_bytes),
        "manifest_disposition": manifest_disposition,
        "source": bundle.manifest["source"],
        "worktree_root": target.root.as_posix(),
        "files": file_state,
    }
    state_before = _snapshot_file(target.root / STATE_REL, include_bytes=True)
    _ensure_writable_destination(target.root, target.root / STATE_REL, STATE_REL)
    return InstallPlan(target, bundle, operations, install_state, state_before, _protected_snapshot(target), state)


class InstallationTransaction:
    def __init__(self, plan):
        self.plan = plan
        self.owner = uuid.uuid4().hex
        self.lock_path = plan.target.root / LOCK_REL
        self.journal_path = plan.target.root / JOURNAL_REL
        self.applied = []
        self.owned_trees = []
        self.config_operations = []
        self.created_dirs = []
        self._locked = False
        self._owns_journal = False
        self.current_state = None
        self._state_after_sha256 = None

    def _mkdirs(self, parent):
        missing = []
        current = parent
        root = self.plan.target.root
        while current != root and not current.exists():
            missing.append(current)
            current = current.parent
        ensure_no_reparse(root, current, include_leaf=True)
        for directory in reversed(missing):
            directory.mkdir()
            self.created_dirs.append(directory)

    def _atomic_write(self, path, data, mode):
        self._mkdirs(path.parent)
        ensure_no_reparse(self.plan.target.root, path, include_leaf=True)
        descriptor, temp_name = tempfile.mkstemp(prefix=".omama-write-", dir=str(path.parent))
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temp_name, mode)
            os.replace(temp_name, str(path))
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass

    def acquire(self):
        self._mkdirs(self.lock_path.parent)
        payload = (json.dumps({"schema": 1, "owner": self.owner, "pid": os.getpid()}, sort_keys=True) + "\n").encode("utf-8")
        try:
            descriptor = os.open(str(self.lock_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            raise InstallError("installer-locked", "installer lock already exists; no stale-lock theft is attempted")
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        self._locked = True

    def _journal(self, status, error=None):
        value = {
            "schema": 1,
            "owner": self.owner,
            "bundle_id": self.plan.bundle.manifest["bundle_id"],
            "status": status,
            "operations": self.applied,
            "owned_trees": self.owned_trees,
            "config_operations": self.config_operations,
        }
        if error:
            value["error"] = error
        data = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
        self._atomic_write(self.journal_path, data, 0o600)
        self._owns_journal = True

    def begin(self):
        self.acquire()
        # Capture every finite before-image before the first payload write.
        for operation in self.plan.operations:
            path = safe_destination(self.plan.target.root, operation.relative)
            before = operation.before
            if not _same_snapshot(path, before):
                raise InstallError("concurrent-edit", "destination changed after preflight: {0}".format(operation.relative))
            self.applied.append({
                "relative": operation.relative,
                "before": before,
                "after_sha256": _sha(operation.data),
                "after_mode": operation.mode,
                "applied": False,
            })
        self._journal("planned")

    def publish(self):
        for operation, record in zip(self.plan.operations, self.applied):
            path = safe_destination(self.plan.target.root, operation.relative)
            if not _same_snapshot(path, record["before"]):
                raise InstallError("concurrent-edit", "destination changed after preflight: {0}".format(operation.relative))
            self._atomic_write(path, operation.data, operation.mode)
            record["applied"] = True
            self._journal("publishing")
        self._journal("published")

    def reserve_owned_tree(self, relative):
        path = safe_destination(self.plan.target.root, relative)
        if path.exists():
            raise InstallError("incompatible-runtime", "owned runtime destination already exists without reusable state: {0}".format(relative))
        staging_relative = ".omama/.runtime-{0}.tmp".format(self.owner)
        staging = safe_destination(self.plan.target.root, staging_relative)
        if staging.exists():
            raise InstallError("incompatible-runtime", "owned runtime staging path already exists")
        record = {
            "relative": relative, "staging_relative": staging_relative,
            "owner": self.owner, "published": False,
        }
        self.owned_trees.append(record)
        self._journal("runtime-reserved")
        return staging

    def publish_owned_tree(self, staging, relative):
        path = safe_destination(self.plan.target.root, relative)
        record = next((item for item in self.owned_trees if item["relative"] == relative), None)
        if record is None or Path(staging) != safe_destination(self.plan.target.root, record["staging_relative"]):
            raise InstallError("incompatible-runtime", "runtime publication was not reserved by this transaction")
        if path.exists() or not Path(staging).is_dir():
            raise InstallError("concurrent-edit", "runtime destination changed or staging is incomplete")
        marker = Path(staging) / ".omama-runtime-owner.json"
        marker_data = (json.dumps({"schema": 1, "owner": self.owner}, sort_keys=True) + "\n").encode("utf-8")
        self._atomic_write(marker, marker_data, 0o600)
        os.replace(str(staging), str(path))
        record["published"] = True
        record["marker_sha256"] = _sha(marker_data)
        record["tree_sha256"] = _tree_digest(path)
        self._journal("runtime-published")

    def activate_hooks_path(self, before):
        import subprocess
        path = self.plan.target.common_dir / "config"
        if self.plan.target.linked_worktree:
            raise InstallError("linked-worktree-config", "linked worktree activation may not mutate shared Git config")
        record = {
            "kind": "core.hooksPath", "path": str(path), "before": before,
            "after_sha256": None, "applied": False,
        }
        self.config_operations.append(record)
        self._journal("activation-planned")
        if not _same_snapshot(path, before):
            raise InstallError("concurrent-edit", "Git config changed after preflight")
        result = subprocess.run(
            ["git", "-C", str(self.plan.target.root), "config", "--local", "core.hooksPath", ".githooks"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", check=False,
        )
        after = _snapshot_file(path, include_bytes=False)
        if after.get("kind") == "file" and after.get("sha256") != before.get("sha256"):
            record["after_sha256"] = after["sha256"]
            record["applied"] = True
            self._journal("activated")
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip().splitlines()
            raise InstallError("git-config-activation", "git config failed: {0}".format(detail[-1][:300] if detail else "no diagnostic"))
        if not record["applied"]:
            raise InstallError("git-config-activation", "git config reported success without recording core.hooksPath")

    def _state_value(self, status, extra=None, base=None):
        state = dict(self.plan.state if base is None else base)
        state["status"] = status
        if extra:
            state.update(extra)
        return state

    def _write_state_value(self, state, before):
        data = (json.dumps(state, indent=2, sort_keys=True) + "\n").encode("utf-8")
        operation = FileOperation(STATE_REL, data, 0o600, before)
        path = safe_destination(self.plan.target.root, operation.relative)
        if not _same_snapshot(path, operation.before):
            raise InstallError("concurrent-edit", "installation state changed after preflight: {0}".format(STATE_REL))
        record = {
            "relative": operation.relative,
            "before": operation.before,
            "after_sha256": _sha(data), "after_mode": operation.mode,
            "applied": False,
        }
        self.applied.append(record)
        self._journal("writing-state")
        self._atomic_write(path, data, operation.mode)
        record["applied"] = True
        self.current_state = state
        self._state_after_sha256 = record["after_sha256"]
        self._journal("state-written")

    def write_state(self, status, extra=None):
        self._write_state_value(self._state_value(status, extra), self.plan.state_before)

    def promote_state(self, status):
        if self.current_state is None or self._state_after_sha256 is None:
            raise InstallError("admission-state", "cannot promote installation state before the private admission state exists")
        path = safe_destination(self.plan.target.root, STATE_REL)
        before = _snapshot_file(path, include_bytes=True)
        if before.get("kind") != "file" or before.get("sha256") != self._state_after_sha256:
            raise InstallError("concurrent-edit", "installation state changed during mandatory admission: {0}".format(STATE_REL))
        self._write_state_value(self._state_value(status, base=self.current_state), before)

    def _protected_unchanged(self):
        return self.plan.protected == _protected_snapshot(self.plan.target)

    def finish(self):
        if not self._protected_unchanged():
            raise InstallError("protected-state-changed", "card family or Git index changed while init ran", incomplete=True)
        if not self._owns_journal:
            raise InstallError("journal-ownership", "transaction does not own the installation journal")
        self.journal_path.unlink()
        self._owns_journal = False
        self._release_lock()

    def _release_lock(self):
        if not self._locked:
            return
        try:
            value = json.loads(self.lock_path.read_text(encoding="utf-8"))
        except Exception:
            value = None
        if isinstance(value, dict) and value.get("owner") == self.owner:
            self.lock_path.unlink()
        self._locked = False

    def rollback(self, cause):
        conflicts = []
        for record in reversed(self.config_operations):
            if not record.get("applied"):
                continue
            path = Path(record["path"])
            current = _snapshot_file(path, include_bytes=False)
            if current.get("kind") != "file" or current.get("sha256") != record.get("after_sha256"):
                conflicts.append("core.hooksPath")
                continue
            before = record["before"]
            if before["kind"] == "file":
                self._atomic_write(path, base64.b64decode(before["bytes_b64"]), before["mode"])
            elif before["kind"] == "missing":
                path.unlink()
            else:
                conflicts.append("core.hooksPath")
        for record in reversed(self.applied):
            if not record.get("applied"):
                continue
            path = safe_destination(self.plan.target.root, record["relative"])
            current = _snapshot_file(path, include_bytes=False)
            if current.get("kind") != "file" or current.get("sha256") != record["after_sha256"]:
                conflicts.append(record["relative"])
                continue
            before = record["before"]
            if before["kind"] == "missing":
                path.unlink()
            elif before["kind"] == "file":
                self._atomic_write(path, base64.b64decode(before["bytes_b64"]), before["mode"])
            else:
                conflicts.append(record["relative"])
        for record in reversed(self.owned_trees):
            path = safe_destination(self.plan.target.root, record["relative"])
            staging = safe_destination(self.plan.target.root, record["staging_relative"])
            if record.get("published") and path.exists():
                marker = path / ".omama-runtime-owner.json"
                marker_snapshot = _snapshot_file(marker, include_bytes=False)
                if (marker_snapshot.get("sha256") == record.get("marker_sha256")
                        and _tree_digest(path) == record.get("tree_sha256")):
                    shutil.rmtree(str(path))
                else:
                    conflicts.append(record["relative"])
            if staging.exists():
                # The UUID-named staging path was reserved by this live owner
                # and never became the durable runtime.
                try:
                    staging.resolve().relative_to(self.plan.target.root.resolve())
                except ValueError:
                    conflicts.append(record["staging_relative"])
                else:
                    shutil.rmtree(str(staging))
        if conflicts and self._owns_journal:
            self._journal("recovery-required", "external bytes preserved: " + ", ".join(conflicts))
        elif not conflicts and self._owns_journal:
            try:
                self.journal_path.unlink()
            except FileNotFoundError:
                pass
            self._owns_journal = False
        self._release_lock()
        for directory in reversed(self.created_dirs):
            try:
                directory.rmdir()
            except OSError:
                pass
        if conflicts:
            raise InstallError(
                "recovery-required",
                "install failed ({0}); externally changed bytes were preserved: {1}"
                .format(cause, ", ".join(conflicts)),
                incomplete=True,
            )


def run_asset_transaction(plan, status="prepared", prepare=None, after_publication=None, before_finish=None, state_extra=None):
    if status == "complete" and before_finish is None:
        raise InstallError("admission-missing", "complete state requires the mandatory private admission callback")
    transaction = InstallationTransaction(plan)
    try:
        transaction.begin()
        prepared_extra = prepare(transaction) if prepare else None
        transaction.publish()
        if after_publication:
            after_publication(transaction)
        combined_extra = dict(state_extra or {})
        if prepared_extra:
            combined_extra.update(prepared_extra)
        if status == "complete":
            transaction.write_state("installing", combined_extra)
            before_finish(transaction)
            transaction.promote_state("complete")
        else:
            transaction.write_state(status, combined_extra)
            if before_finish:
                before_finish(transaction)
        transaction.finish()
    except Exception as exc:
        try:
            transaction.rollback(str(exc))
        except InstallError:
            raise
        if isinstance(exc, (InstallError, TargetError)):
            raise
        raise InstallError("installation-failed", "installation failed: {0}: {1}".format(type(exc).__name__, exc))
    return transaction
