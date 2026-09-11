"""Finite, target-owned publication and conditional recovery for ``omama init``."""

import base64
import hashlib
import json
import os
import shutil
import socket
import stat
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from .identity import ExistingState, classify_existing
from .target import TargetError, ensure_no_reparse, safe_destination


STATE_REL = ".omama/state.json"
JOURNAL_REL = ".omama/install-journal.json"
# Retained legacy per-worktree lock.  Installations interrupted before the
# canonical lock existed still hold this one; it continues to block.
LOCK_REL = ".omama/install.lock"
# The canonical lock lives in the Git common directory, so every linked
# worktree of one repository contends for the same lock.
CANONICAL_LOCK_NAME = "omama-install.lock"
MANIFEST_REL = "tools/omama/manifest.json"
STATE_SCHEMA = 1
LOCK_SCHEMA = 2


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


def _fsync_directory(path):
    try:
        descriptor = os.open(str(path), getattr(os, "O_DIRECTORY", os.O_RDONLY))
    except (OSError, AttributeError):
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _atomic_write_verified(path, data, mode):
    """Replace ``path`` atomically and prove the durable result immediately.

    A write that is not read back is a claim.  The replacement, its bytes and
    its mode are verified before the caller may record the operation as
    applied, so the journal never records an after-image that is not on disk.
    """
    path = Path(path)
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
    _fsync_directory(path.parent)
    written = _snapshot_file(path, include_bytes=False)
    if written.get("kind") != "file" or written.get("sha256") != _sha(data):
        raise InstallError(
            "durable-write-unverified",
            "durable write did not read back as written: {0}".format(path),
            incomplete=True,
        )
    if os.name != "nt" and written.get("mode") != stat.S_IMODE(mode):
        raise InstallError(
            "durable-write-unverified",
            "durable write did not retain mode {0:o}: {1}".format(stat.S_IMODE(mode), path),
            incomplete=True,
        )
    return written


def canonical_lock_path(target):
    return Path(target.common_dir) / CANONICAL_LOCK_NAME


def _boot_identity():
    """A value that changes when the machine restarts, when one is available."""
    for candidate in ("/proc/sys/kernel/random/boot_id",):
        try:
            return Path(candidate).read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            continue
    return None


def _process_start_token(pid):
    """A per-process value that distinguishes a reused PID from the original."""
    try:
        fields = Path("/proc/{0}/stat".format(int(pid))).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError, TypeError):
        return None
    # The executable name is parenthesized and may contain spaces.
    tail = fields.rpartition(")")[2].split()
    # Field 22 overall is the 20th field after the state field.
    return tail[19] if len(tail) > 19 else None


def process_identity():
    pid = os.getpid()
    return {
        "pid": pid,
        "host": socket.gethostname(),
        "boot_id": _boot_identity(),
        "start_token": _process_start_token(pid),
    }


def _pid_exists(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    if pid <= 0:
        return None
    if os.name == "nt":
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return None
    return True


def owner_liveness(record, current=None):
    """Classify a recorded lock owner as ``live``, ``dead`` or ``uncertain``.

    PID alone is not identity because PIDs are reused, and age alone is not
    identity because a slow install is not a dead one.  Only a same-host,
    same-boot observation that the recorded process is gone -- or is a
    different process than the one that took the lock -- proves death.
    """
    current = current or process_identity()
    if not isinstance(record, dict):
        return "uncertain", "lock payload is unreadable"
    if record.get("host") and record["host"] != current["host"]:
        return "uncertain", "lock was taken on host {0!r}, not this host".format(record["host"])
    recorded_boot = record.get("boot_id")
    if recorded_boot and current["boot_id"] and recorded_boot != current["boot_id"]:
        return "dead", "lock predates the current boot of this machine"
    exists = _pid_exists(record.get("pid"))
    if exists is False:
        return "dead", "recorded process {0} is not running on this host".format(record.get("pid"))
    if exists is None:
        return "uncertain", "process identity cannot be established on this platform"
    recorded_token = record.get("start_token")
    live_token = _process_start_token(record.get("pid"))
    if recorded_token and live_token and recorded_token != live_token:
        return "dead", "process {0} exists but is a different process than the lock owner".format(record.get("pid"))
    if not recorded_token or not live_token:
        return "uncertain", "process {0} exists and cannot be distinguished from the lock owner".format(record.get("pid"))
    return "live", "process {0} is the running lock owner".format(record.get("pid"))


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


def _lock_payload(owner):
    identity = process_identity()
    value = {"schema": LOCK_SCHEMA, "owner": owner}
    value.update(identity)
    return (json.dumps(value, sort_keys=True) + "\n").encode("utf-8")


def read_lock(target):
    path = canonical_lock_path(target)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError, ValueError):
        # An unreadable lock is uncertain ownership, never an absent one.
        return {}


def acquire_canonical_lock(target, owner, reclaim_dead=False):
    """Take the one repository-wide lock, or refuse with a bounded diagnostic.

    Acquisition is a single atomic ``O_EXCL`` create: concurrent attempts
    produce exactly one owner and an explicit loser.  No attempt waits, retries
    indefinitely or steals a lock whose owner may still be live.
    """
    path = canonical_lock_path(target)
    payload = _lock_payload(owner)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        existing = read_lock(target)
        liveness, detail = owner_liveness(existing)
        if reclaim_dead and liveness == "dead":
            # Not theft: the recorded owner is provably gone on this host.  The
            # old lock is quarantined as evidence rather than deleted, and the
            # re-create below is still exclusive, so a racing reclaimer loses.
            quarantine = path.with_name(path.name + ".reclaimed-" + owner)
            try:
                os.rename(str(path), str(quarantine))
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise InstallError("installer-locked", "dead lock could not be quarantined: {0}".format(type(exc).__name__))
            return acquire_canonical_lock(target, owner, reclaim_dead=False)
        raise InstallError(
            "installer-locked",
            "another omama operation holds the repository lock at {0} ({1}: {2}); "
            "no stale-lock theft is attempted. If that operation is finished, rerun "
            "`omama init` in this repository to reconcile it, or ask a maintainer to "
            "inspect the lock before removing it."
            .format(path, liveness, detail),
        )
    except OSError as exc:
        raise InstallError("installer-locked", "repository lock could not be created at {0}: {1}".format(path, type(exc).__name__))
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    _fsync_directory(path.parent)
    return path


def release_canonical_lock(target, owner):
    path = canonical_lock_path(target)
    value = read_lock(target)
    if isinstance(value, dict) and value.get("owner") == owner:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return True
    return False


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
    canonical = canonical_lock_path(target)
    if canonical.exists():
        liveness, detail = owner_liveness(read_lock(target))
        raise InstallError(
            "installer-locked",
            "the repository lock at {0} is held ({1}: {2}); no stale-lock theft is attempted"
            .format(canonical, liveness, detail),
        )

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
        elif classification == ExistingState.GENERATED_DRIFT:
            raise InstallError("generated-wiring-conflict", "generated hook differs from this bundle: {0}".format(destination))
        elif classification == ExistingState.PACKAGE_UPDATE:
            # Unreachable: the top-level semantic-bundle guard above refuses a
            # different recorded bundle before any file is classified, which
            # was confirmed by instrumenting the classifier (zero per-file
            # PACKAGE_UPDATE classifications during a different-bundle
            # preflight).  It is retained as an assertion rather than as a
            # duplicate policy arm, so a future change that makes it reachable
            # fails loudly instead of being reported as an immutable conflict.
            raise InstallError(
                "package-update",
                "per-file package-update reached despite the top-level bundle guard: {0}".format(destination),
            )
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
        self.lock_path = canonical_lock_path(plan.target)
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
        _atomic_write_verified(path, data, mode)

    def acquire(self):
        # The canonical lock lives in the Git common directory, which is
        # outside this worktree for a linked worktree; it is deliberately not
        # routed through the in-repository destination guards.
        # The legacy per-worktree lock still blocks: an installation that was
        # interrupted before the canonical lock existed must not be overrun.
        if (self.plan.target.root / LOCK_REL).exists():
            raise InstallError("installer-locked", "legacy installer lock exists at {0}; recover it before retrying".format(LOCK_REL))
        acquire_canonical_lock(self.plan.target, self.owner)
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
        # Preflight can become stale while another owner holds the lock. Once
        # this transaction acquires it, an existing journal belongs to the
        # earlier unfinished attempt and must never be replaced.
        if self.journal_path.exists():
            raise InstallError(
                "unfinished-install",
                "unfinished journal exists at {0}; recover it before retrying".format(JOURNAL_REL),
            )
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
        release_canonical_lock(self.plan.target, self.owner)
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


# --- Bounded, evidence-preserving recovery ---------------------------------
#
# Recovery first establishes one owner, then classifies every journal entry --
# including entries still marked ``applied=false`` -- against the bytes that
# are actually on disk.  "Before" is unapplied, "after" is applied, and
# "neither" is a possible external edit that is preserved while recovery stops.
# Classification is completed for every entry before anything is changed, so an
# ambiguous entry never costs the evidence held by the unambiguous ones.

def _matches_snapshot(current, before):
    return all(current.get(key) == before.get(key) for key in ("kind", "sha256", "size", "mode"))


def _matches_after(current, record):
    after_sha = record.get("after_sha256")
    if current.get("kind") != "file" or not after_sha:
        return False
    if current.get("sha256") != after_sha:
        return False
    after_mode = record.get("after_mode")
    if os.name != "nt" and after_mode is not None and current.get("mode") != stat.S_IMODE(after_mode):
        return False
    return True


def classify_journal_entry(path, record):
    """Classify current bytes as ``before``, ``after`` or ``neither``."""
    current = _snapshot_file(path, include_bytes=False)
    before = record.get("before") or {}
    if _matches_snapshot(current, before):
        return "before", current
    if _matches_after(current, record):
        return "after", current
    return "neither", current


def _restore_before(path, before):
    if before.get("kind") == "missing":
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return "removed"
    if before.get("kind") == "file":
        _atomic_write_verified(path, base64.b64decode(before["bytes_b64"]), before.get("mode", 0o644))
        return "restored"
    raise InstallError("recovery-ambiguous", "recorded before-image for {0} is not a regular file or absence".format(path))


def _recover_classify(target, journal):
    """Classify every entry without changing anything."""
    plan = {"files": [], "config": [], "trees": [], "ambiguous": []}
    for record in journal.get("operations") or []:
        path = safe_destination(target.root, record["relative"])
        state, current = classify_journal_entry(path, record)
        row = {
            "relative": record["relative"], "path": str(path), "classification": state,
            "journal_applied_flag": record.get("applied"),
            "recorded_before_sha256": (record.get("before") or {}).get("sha256"),
            "recorded_after_sha256": record.get("after_sha256"),
            "current_sha256": current.get("sha256"), "current_kind": current.get("kind"),
        }
        if state == "neither":
            plan["ambiguous"].append(row)
        else:
            plan["files"].append((row, path, record))
    for record in journal.get("config_operations") or []:
        path = Path(record["path"])
        state, current = classify_journal_entry(path, record)
        row = {
            "kind": record.get("kind"), "path": str(path), "classification": state,
            "journal_applied_flag": record.get("applied"),
            "recorded_after_sha256": record.get("after_sha256"),
            "current_sha256": current.get("sha256"),
        }
        if not record.get("applied") and state == "before":
            row["classification"] = "before"
            plan["config"].append((row, path, record))
        elif state == "neither":
            plan["ambiguous"].append(row)
        else:
            plan["config"].append((row, path, record))
    for record in journal.get("owned_trees") or []:
        relative = record["relative"]
        path = safe_destination(target.root, relative)
        staging = safe_destination(target.root, record["staging_relative"])
        row = {"relative": relative, "path": str(path), "published": bool(record.get("published"))}
        if path.exists():
            marker = path / ".omama-runtime-owner.json"
            marker_snapshot = _snapshot_file(marker, include_bytes=False)
            owned = (record.get("published")
                     and marker_snapshot.get("sha256") == record.get("marker_sha256")
                     and _tree_digest(path) == record.get("tree_sha256"))
            if not owned:
                row["classification"] = "neither"
                row["detail"] = "runtime tree is not byte-identical to the tree this transaction published"
                plan["ambiguous"].append(row)
                continue
            row["classification"] = "after"
        else:
            row["classification"] = "before"
        plan["trees"].append((row, path, staging, record))
    return plan


def recover(target, owner=None):
    """Reconcile one interrupted installation, or preserve it and stop.

    Returns ``None`` when there is nothing to recover.
    """
    journal_path = target.root / JOURNAL_REL
    if not journal_path.exists():
        return None
    owner = owner or uuid.uuid4().hex
    legacy_lock = target.root / LOCK_REL
    if legacy_lock.exists():
        try:
            legacy = json.loads(legacy_lock.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            legacy = {}
        liveness, detail = owner_liveness(legacy)
        if liveness != "dead":
            raise InstallError(
                "recovery-owner-uncertain",
                "the interrupted installation's lock at {0} is {1} ({2}); its owner is not "
                "recovered automatically. Confirm that no omama process is running in this "
                "repository, then ask a maintainer to inspect and remove that lock."
                .format(LOCK_REL, liveness, detail),
            )
    acquire_canonical_lock(target, owner, reclaim_dead=True)
    try:
        try:
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise InstallError(
                "recovery-ambiguous",
                "the installation journal at {0} cannot be parsed ({1}); it is preserved for "
                "maintainer-assisted recovery and nothing was changed."
                .format(JOURNAL_REL, type(exc).__name__),
            )
        if not isinstance(journal, dict) or journal.get("schema") != 1:
            raise InstallError(
                "recovery-ambiguous",
                "the installation journal at {0} has an unsupported shape; it is preserved "
                "and nothing was changed.".format(JOURNAL_REL),
            )
        classified = _recover_classify(target, journal)
        if classified["ambiguous"]:
            detail = "; ".join(
                "{0} (recorded before={1}, after={2}, current={3})".format(
                    row.get("relative") or row.get("path"),
                    row.get("recorded_before_sha256"), row.get("recorded_after_sha256"),
                    row.get("current_sha256") or row.get("detail"))
                for row in classified["ambiguous"])
            raise InstallError(
                "recovery-ambiguous",
                "recovery stopped without changing anything: {0} path(s) match neither the "
                "recorded before-image nor the recorded after-image, so they may be external "
                "edits made after the failure: {1}. The journal, lock and all bytes are "
                "preserved. A maintainer should compare these paths against the recorded "
                "hashes in {2} and reconcile them deliberately."
                .format(len(classified["ambiguous"]), detail, JOURNAL_REL),
                incomplete=True,
            )
        report = {"owner": owner, "journal_status": journal.get("status"),
                  "files": [], "config": [], "trees": []}
        for row, path, record in reversed(classified["config"]):
            if row["classification"] == "after":
                row["action"] = _restore_before(path, record["before"])
            else:
                row["action"] = "unapplied"
            report["config"].append(row)
        for row, path, record in reversed(classified["files"]):
            if row["classification"] == "after":
                row["action"] = _restore_before(path, record["before"])
            else:
                row["action"] = "unapplied"
            report["files"].append(row)
        for row, path, staging, _record in reversed(classified["trees"]):
            if row["classification"] == "after":
                shutil.rmtree(str(path))
                row["action"] = "removed transaction-owned runtime"
            else:
                row["action"] = "absent"
            if staging.exists():
                try:
                    staging.resolve().relative_to(target.root.resolve())
                except ValueError:
                    pass
                else:
                    shutil.rmtree(str(staging))
                    row["staging"] = "removed transaction-owned staging"
            report["trees"].append(row)
        journal_path.unlink()
        if legacy_lock.exists():
            legacy_lock.unlink()
        return report
    finally:
        release_canonical_lock(target, owner)
