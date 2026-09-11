"""Phase-B M2: canonical locking, the finite journal, and bounded recovery.

Interruptions are produced by a child process that genuinely dies at a chosen
durable boundary.  An in-process simulation cannot be used: the simulating
process is itself the live lock owner, and a live owner is never recovered.
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

import test_install as install_fixture

CHILD = Path(__file__).resolve().parent / "interrupt_child.py"


def _helper():
    return install_fixture.InstallerContractTests("test_inherited_git_routing_refuses_before_target_writes")


def _sha(path):
    path = Path(path)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _interrupt(root, window):
    """Run a real installation in a child that dies at ``window``."""
    result = subprocess.run(
        [sys.executable, "-B", str(CHILD), str(root), window],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"), check=False,
    )
    if result.returncode != 137:
        raise AssertionError("interrupt child did not reach {0}: exit {1}\n{2}".format(
            window, result.returncode, result.stderr))
    return result


class RecoveryContractTests(unittest.TestCase):
    def test_post_replace_window_classifies_an_applied_false_entry_as_after(self):
        from omama_cli.install import recover
        from omama_cli.target import resolve_target

        helper = _helper()
        root = helper.make_repo()
        result = _interrupt(root, "post-replace")
        replaced = result.stderr.split("KILLED-AFTER-REPLACE ", 1)[1].strip().splitlines()[0]
        journal = json.loads((root / ".omama" / "install-journal.json").read_text(encoding="utf-8"))
        entry = next(item for item in journal["operations"]
                     if Path(replaced).name == Path(item["relative"]).name)
        # The replacement is durable while the journal still says it is not.
        self.assertEqual("planned", journal["status"])
        self.assertFalse(entry["applied"])
        self.assertEqual(entry["after_sha256"], _sha(replaced))

        report = recover(resolve_target(str(root), environ={}))
        reconciled = [row for row in report["files"]
                      if row["journal_applied_flag"] is False and row["classification"] == "after"]
        self.assertTrue(reconciled, "an applied=false entry whose bytes are the after-image was not reconciled")
        self.assertFalse(Path(replaced).exists(), "the published file was not rolled back to its absent before-image")
        self.assertFalse((root / ".omama" / "install-journal.json").exists())

    def test_post_activation_window_reconciles_state_and_activation(self):
        from omama_cli.install import canonical_lock_path, recover
        from omama_cli.target import resolve_target

        helper = _helper()
        root = helper.make_repo()
        _interrupt(root, "post-activation-wired")
        journal = json.loads((root / ".omama" / "install-journal.json").read_text(encoding="utf-8"))
        # Under the selected ordering the state is written first and activation
        # follows private admission, so the last durable boundary an abrupt
        # death can reach here is `activated`: live hooks with incomplete state.
        self.assertEqual("activated", journal["status"])
        self.assertEqual("installing", json.loads((root / ".omama" / "state.json").read_text(encoding="utf-8"))["status"])
        activation = [item for item in journal.get("config_operations") or [] if item.get("applied")]
        self.assertTrue(activation, "the wired interruption did not record an applied activation")
        target = resolve_target(str(root), environ={})
        report = recover(target)
        self.assertFalse((root / ".omama" / "state.json").exists(), "incomplete install state survived recovery")
        self.assertTrue(any(row.get("kind") == "core.hooksPath" for row in report["config"]),
                        "recovery did not reconcile the activation entry")
        hooks = subprocess.run(["git", "-C", str(root), "config", "--local", "--get", "core.hooksPath"],
                               stdout=subprocess.PIPE, text=True, check=False)
        self.assertNotEqual(0, hooks.returncode, "activation was not rolled back: " + hooks.stdout.strip())
        self.assertFalse(canonical_lock_path(target).exists())

    def test_external_edit_after_failure_is_preserved_and_recovery_stops(self):
        from omama_cli.install import InstallError, canonical_lock_path, recover
        from omama_cli.target import resolve_target

        helper = _helper()
        root = helper.make_repo()
        result = _interrupt(root, "post-replace")
        replaced = result.stderr.split("KILLED-AFTER-REPLACE ", 1)[1].strip().splitlines()[0]
        Path(replaced).write_text("adopter edited this file after the failure\n", encoding="utf-8")
        edited = _sha(replaced)
        other = [item["relative"] for item in
                 json.loads((root / ".omama" / "install-journal.json").read_text(encoding="utf-8"))["operations"]]
        target = resolve_target(str(root), environ={})
        with self.assertRaises(InstallError) as caught:
            recover(target)
        self.assertEqual("recovery-ambiguous", caught.exception.reason)
        self.assertTrue(caught.exception.incomplete)
        # Nothing at all was changed: the ambiguous entry does not cost the
        # evidence held by the unambiguous ones.
        self.assertEqual(edited, _sha(replaced), "a possible external edit was overwritten")
        self.assertTrue((root / ".omama" / "install-journal.json").exists(), "the journal was discarded")
        self.assertFalse(canonical_lock_path(target).exists(), "recovery kept the lock after stopping")
        self.assertIn(Path(replaced).name, caught.exception.message)
        self.assertTrue(other)

    def test_live_and_uncertain_owners_are_never_stolen_and_pid_alone_is_not_identity(self):
        from omama_cli.install import owner_liveness, process_identity

        current = process_identity()
        # The running process itself is live and must never be reclaimed.
        self.assertEqual("live", owner_liveness(dict(current, owner="x"))[0])
        # A different host cannot be inspected from here.
        self.assertEqual("uncertain", owner_liveness(dict(current, host="some-other-host"))[0])
        # A PID that exists but is demonstrably a different process is dead:
        # PID reuse must not be mistaken for the original owner.
        if current["start_token"]:
            reused = dict(current, start_token=str(int(current["start_token"]) + 1))
            self.assertEqual("dead", owner_liveness(reused)[0])
            # Without a per-process token, an existing PID stays uncertain:
            # the PID alone is not identity.
            self.assertEqual("uncertain", owner_liveness(dict(current, start_token=None))[0])
        # Age is never consulted.
        self.assertEqual("live", owner_liveness(dict(current, started_at=0, owner="x"))[0])

    def test_simultaneous_owners_produce_one_winner_and_an_explicit_loser(self):
        from omama_cli.install import InstallError, acquire_canonical_lock, release_canonical_lock
        from omama_cli.target import resolve_target

        helper = _helper()
        root = helper.make_repo()
        target = resolve_target(str(root), environ={})
        outcomes = []
        barrier = threading.Barrier(6)

        def attempt(index):
            barrier.wait()
            try:
                acquire_canonical_lock(target, "owner-{0}".format(index))
                outcomes.append(("acquired", index))
            except InstallError as exc:
                outcomes.append((exc.reason, index))

        threads = [threading.Thread(target=attempt, args=(index,)) for index in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            # A bounded refusal never waits: any thread that hangs is a defect.
            thread.join(timeout=30)
            self.assertFalse(thread.is_alive(), "lock acquisition did not terminate")
        acquired = [index for reason, index in outcomes if reason == "acquired"]
        refused = [reason for reason, _index in outcomes if reason != "acquired"]
        self.assertEqual(1, len(acquired), "expected exactly one owner, got {0}".format(outcomes))
        self.assertEqual(5, len(refused))
        self.assertEqual({"installer-locked"}, set(refused))
        release_canonical_lock(target, "owner-{0}".format(acquired[0]))

    def test_canonical_lock_is_shared_across_linked_worktrees(self):
        from omama_cli.install import InstallError, acquire_canonical_lock, canonical_lock_path, release_canonical_lock
        from omama_cli.target import resolve_target

        helper = _helper()
        main = helper.make_repo()
        self.assertEqual(0, subprocess.run(
            ["git", "-C", str(main), "-c", "core.hooksPath=.no-hooks", "commit", "-qm", "base"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False).returncode)
        linked = Path(tempfile.mkdtemp(prefix="linked-", dir=install_fixture._test_root())) / "worktree"
        created = subprocess.run(["git", "-C", str(main), "worktree", "add", "--detach", str(linked)],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        if created.returncode != 0:
            raise AssertionError("linked worktree could not be created: " + created.stderr)
        main_target = resolve_target(str(main), environ={})
        linked_target = resolve_target(str(linked), environ={})
        self.assertTrue(linked_target.linked_worktree)
        self.assertEqual(canonical_lock_path(main_target), canonical_lock_path(linked_target),
                         "linked worktrees did not contend for one canonical lock")
        acquire_canonical_lock(main_target, "main-owner")
        try:
            with self.assertRaises(InstallError) as caught:
                acquire_canonical_lock(linked_target, "linked-owner")
            self.assertEqual("installer-locked", caught.exception.reason)
        finally:
            release_canonical_lock(main_target, "main-owner")

    def test_durable_write_is_verified_before_it_is_recorded_as_applied(self):
        from omama_cli.install import InstallError, _atomic_write_verified

        base = Path(tempfile.mkdtemp(prefix="durable-", dir=install_fixture._test_root()))
        path = base / "payload.txt"
        written = _atomic_write_verified(path, b"durable bytes\n", 0o644)
        self.assertEqual(hashlib.sha256(b"durable bytes\n").hexdigest(), written["sha256"])
        self.assertEqual(b"durable bytes\n", path.read_bytes())
        if os.name != "nt":
            self.assertEqual(0o644, written["mode"])
        # A write that does not read back as written is never reported as done.
        from omama_cli import install as install_module
        real = install_module._snapshot_file

        def lying_snapshot(target, include_bytes=True):
            value = real(target, include_bytes=include_bytes)
            if Path(target) == path and value.get("kind") == "file":
                value["sha256"] = "0" * 64
            return value

        install_module._snapshot_file = lying_snapshot
        try:
            with self.assertRaises(InstallError) as caught:
                _atomic_write_verified(path, b"other bytes\n", 0o644)
            self.assertEqual("durable-write-unverified", caught.exception.reason)
            self.assertTrue(caught.exception.incomplete)
        finally:
            install_module._snapshot_file = real

    def test_legacy_worktree_lock_still_blocks_and_is_not_stolen(self):
        from omama_cli.install import InstallError, LOCK_REL, recover
        from omama_cli.target import resolve_target

        helper = _helper()
        root = helper.make_repo()
        _interrupt(root, "post-replace")
        # A pre-canonical-lock installation is represented by the legacy lock
        # with no host, boot or per-process identity recorded.
        legacy = root / LOCK_REL
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text(json.dumps({"schema": 1, "owner": "legacy", "pid": os.getpid()}) + "\n",
                          encoding="utf-8")
        with self.assertRaises(InstallError) as caught:
            recover(resolve_target(str(root), environ={}))
        self.assertEqual("recovery-owner-uncertain", caught.exception.reason)
        self.assertTrue(legacy.exists(), "an uncertain legacy lock was removed")
        self.assertTrue((root / ".omama" / "install-journal.json").exists())


if __name__ == "__main__":
    unittest.main()
