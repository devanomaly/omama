import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


def _test_root():
    value = os.environ.get("OMAMA_CLI_TEST_ROOT")
    if not value:
        raise RuntimeError("OMAMA_CLI_TEST_ROOT must name the allocated disposable root")
    root = Path(value).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return str(root)


def _run(*args, cwd=None, env=None):
    return subprocess.run(
        list(args), cwd=str(cwd) if cwd else None, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", check=False,
    )


def _tree_bytes(root):
    root = Path(root)
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


class InstallerContractTests(unittest.TestCase):
    def make_repo(self):
        root = Path(tempfile.mkdtemp(prefix="install-", dir=_test_root()))
        self.assertEqual(0, _run("git", "init", str(root)).returncode)
        self.assertEqual(0, _run("git", "-C", str(root), "config", "user.email", "fixture@example.invalid").returncode)
        self.assertEqual(0, _run("git", "-C", str(root), "config", "user.name", "Fixture").returncode)
        (root / "sentinel.txt").write_bytes(b"preserve me\n")
        (root / "CARD.yaml").write_bytes(b"synthetic protected card\n")
        self.assertEqual(0, _run("git", "-C", str(root), "add", "sentinel.txt").returncode)
        return root

    def run_cli(self, root, extra_env=None):
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)
        return _run(sys.executable, "-m", "omama_cli", "init", str(root), env=env)

    def bundle(self, bundle_id_seed="current", destination_override=None):
        from omama_cli.bundle import _validate_manifest

        payload = {
            "tools/omama/a.py": b"print('immutable')\n",
            ".githooks/pre-commit": b"#!/bin/sh\nexit 0\n",
            ".githooks/pre-merge-commit": b"#!/bin/sh\nexit 0\n",
            ".githooks/privacy-pre-commit": b"#!/bin/sh\nexit 0\n",
            "tools/omama/privacy-hook/scan_staged.py": b"print('synthetic scanner')\n",
            "privacy-deny.json": b'{"tokens_file":"privacy-tokens.txt"}\n',
            "tools/omama/LICENSE": b"synthetic MIT fixture\n",
        }
        ownership = {
            "tools/omama/a.py": "immutable",
            ".githooks/pre-commit": "generated-wiring",
            ".githooks/pre-merge-commit": "generated-wiring",
            ".githooks/privacy-pre-commit": "immutable",
            "tools/omama/privacy-hook/scan_staged.py": "immutable",
            "privacy-deny.json": "editable-bootstrap",
            "tools/omama/LICENSE": "immutable",
        }
        entries = []
        resources = {}
        for number, (destination, data) in enumerate(payload.items()):
            actual_destination = destination_override if number == 0 and destination_override else destination
            resource = "files/" + str(number)
            resources[resource] = data
            entries.append({
                "source": "fixture/" + str(number), "destination": actual_destination,
                "resource": resource, "ownership": ownership[destination],
                "sha256": hashlib.sha256(data).hexdigest(), "size": len(data),
            })
        source = {
            "url": "https://example.invalid/fixture", "revision": bundle_id_seed,
            "dirty": True, "exact_revision": None,
            "dirty_digest": hashlib.sha256(bundle_id_seed.encode()).hexdigest(),
            "identity_inputs_digest": hashlib.sha256(bundle_id_seed.encode()).hexdigest(),
            "modified_after_identity_capture": False,
            "dirty_digest_policy": "fixture",
        }
        license_identity = {"destination": "tools/omama/LICENSE", "expression": "MIT"}
        ownership_policy = {"fixture": True}
        generated_local = []
        basis = {
            "package_version": "0.1.0", "source": source, "license": license_identity,
            "files": [{key: entry[key] for key in ("destination", "ownership", "sha256")} for entry in entries],
            "generated_local": generated_local, "ownership_policy": ownership_policy,
        }
        bundle_id = hashlib.sha256(json.dumps(basis, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        manifest = {
            "schema": 1, "package_version": "0.1.0", "bundle_id": bundle_id,
            "source": source, "license": license_identity, "files": entries,
            "required_destinations": [entry["destination"] for entry in entries],
            "generated_local": generated_local, "ownership_policy": ownership_policy,
            "installed_identity": {"destination": "tools/omama/manifest.json"},
        }
        raw = (json.dumps(manifest, sort_keys=True) + "\n").encode()
        return _validate_manifest(manifest, resources.get, raw)

    def test_inherited_git_routing_refuses_before_target_writes(self):
        root = self.make_repo()
        decoy = Path(tempfile.mkdtemp(prefix="decoy-", dir=_test_root()))
        before = _tree_bytes(root)
        result = self.run_cli(root, {"GIT_DIR": str(decoy)})
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertIn("inherited-git-routing", result.stderr)
        self.assertEqual(before, _tree_bytes(root))
        self.assertFalse((root / ".omama").exists())

    def test_subdirectory_resolves_worktree_and_fresh_publication_preserves_evidence(self):
        from omama_cli.install import preflight_bundle, run_asset_transaction
        from omama_cli.target import resolve_target

        root = self.make_repo()
        subdir = root / "nested" / "child"
        subdir.mkdir(parents=True)
        before_card = (root / "CARD.yaml").read_bytes()
        before_index = (root / ".git" / "index").read_bytes()
        before_head = _run("git", "-C", str(root), "rev-parse", "--verify", "HEAD").stdout
        target = resolve_target(str(subdir), environ={})
        self.assertEqual(root.resolve(), target.root)
        plan = preflight_bundle(target, self.bundle())
        run_asset_transaction(plan, status="prepared")
        self.assertEqual(b"print('immutable')\n", (root / "tools/omama/a.py").read_bytes())
        self.assertEqual(before_card, (root / "CARD.yaml").read_bytes())
        self.assertEqual(before_index, (root / ".git" / "index").read_bytes())
        self.assertEqual(before_head, _run("git", "-C", str(root), "rev-parse", "--verify", "HEAD").stdout)
        self.assertFalse((root / ".omama" / "install.lock").exists())
        self.assertFalse((root / ".omama" / "install-journal.json").exists())
        state = json.loads((root / ".omama" / "state.json").read_text(encoding="utf-8"))
        self.assertEqual("prepared", state["status"])

    def test_same_bundle_preserves_edited_and_deleted_editable_material(self):
        from omama_cli.install import preflight_bundle, run_asset_transaction
        from omama_cli.target import resolve_target

        root = self.make_repo()
        target = resolve_target(str(root), environ={})
        bundle = self.bundle()
        run_asset_transaction(preflight_bundle(target, bundle), status="prepared")
        edited = b'{"team":"preserved"}\n'
        (root / "privacy-deny.json").write_bytes(edited)
        run_asset_transaction(preflight_bundle(target, bundle), status="prepared")
        self.assertEqual(edited, (root / "privacy-deny.json").read_bytes())
        (root / "privacy-deny.json").unlink()
        run_asset_transaction(preflight_bundle(target, bundle), status="prepared")
        self.assertFalse((root / "privacy-deny.json").exists())

    def test_same_bundle_repairs_missing_immutable_but_refuses_generated_drift(self):
        from omama_cli.install import InstallError, preflight_bundle, run_asset_transaction
        from omama_cli.target import resolve_target

        root = self.make_repo()
        target = resolve_target(str(root), environ={})
        bundle = self.bundle()
        run_asset_transaction(preflight_bundle(target, bundle), status="prepared")
        immutable = root / "tools" / "omama" / "a.py"
        immutable.unlink()
        run_asset_transaction(preflight_bundle(target, bundle), status="prepared")
        self.assertEqual(b"print('immutable')\n", immutable.read_bytes())
        chainer = root / ".githooks" / "pre-commit"
        chainer.write_bytes(b"#!/bin/sh\necho changed\n")
        before = _tree_bytes(root)
        with self.assertRaises(InstallError) as caught:
            preflight_bundle(target, bundle)
        self.assertEqual("generated-wiring-conflict", caught.exception.reason)
        self.assertEqual(before, _tree_bytes(root))

    def test_global_bundle_mismatch_dominates_missing_file_without_writes(self):
        from omama_cli.install import InstallError, preflight_bundle, run_asset_transaction
        from omama_cli.target import resolve_target

        root = self.make_repo()
        target = resolve_target(str(root), environ={})
        first = self.bundle("first")
        run_asset_transaction(preflight_bundle(target, first), status="prepared")
        (root / "tools/omama/a.py").unlink()
        before = _tree_bytes(root)
        with self.assertRaisesRegex(InstallError, "does not update implicitly") as caught:
            preflight_bundle(target, self.bundle("second"))
        self.assertEqual("package-update", caught.exception.reason)
        self.assertEqual(before, _tree_bytes(root))
        self.assertFalse((root / "tools/omama/a.py").exists())

    def test_immutable_drift_and_active_close_refuse_before_publication(self):
        from omama_cli.install import InstallError, preflight_bundle
        from omama_cli.target import resolve_target

        root = self.make_repo()
        target = resolve_target(str(root), environ={})
        (root / "tools" / "omama").mkdir(parents=True)
        (root / "tools" / "omama" / "a.py").write_bytes(b"team bytes\n")
        before = _tree_bytes(root)
        with self.assertRaises(InstallError) as caught:
            preflight_bundle(target, self.bundle())
        self.assertEqual("immutable-conflict", caught.exception.reason)
        self.assertEqual(before, _tree_bytes(root))
        (root / "tools" / "omama" / "a.py").unlink()
        (root / "CARD.close").write_bytes(b"CLOSE\n")
        before = _tree_bytes(root)
        with self.assertRaises(InstallError) as caught:
            preflight_bundle(target, self.bundle())
        self.assertEqual("active-close", caught.exception.reason)
        self.assertEqual(before, _tree_bytes(root))

    def test_competing_init_lock_is_not_stolen(self):
        from omama_cli.install import InstallError, preflight_bundle
        from omama_cli.target import resolve_target

        root = self.make_repo()
        lock = root / ".omama" / "install.lock"
        lock.parent.mkdir()
        lock.write_bytes(b'{"owner":"other"}\n')
        before = _tree_bytes(root)
        with self.assertRaises(InstallError) as caught:
            preflight_bundle(resolve_target(str(root), environ={}), self.bundle())
        self.assertEqual("installer-locked", caught.exception.reason)
        self.assertEqual(before, _tree_bytes(root))
        self.assertEqual(b'{"owner":"other"}\n', lock.read_bytes())

    def test_competing_lock_created_after_preflight_is_not_stolen(self):
        from omama_cli.install import InstallError, preflight_bundle, run_asset_transaction
        from omama_cli.target import resolve_target

        root = self.make_repo()
        plan = preflight_bundle(resolve_target(str(root), environ={}), self.bundle())
        lock = root / ".omama" / "install.lock"
        lock.parent.mkdir()
        lock.write_bytes(b'{"owner":"racer"}\n')
        with self.assertRaises(InstallError) as caught:
            run_asset_transaction(plan)
        self.assertEqual("installer-locked", caught.exception.reason)
        self.assertEqual(b'{"owner":"racer"}\n', lock.read_bytes())
        self.assertFalse((root / "tools").exists())

    def test_losing_preflighted_contender_preserves_winner_lock_and_journal(self):
        from omama_cli.install import InstallationTransaction, InstallError, preflight_bundle, run_asset_transaction
        from omama_cli.target import resolve_target

        root = self.make_repo()
        target = resolve_target(str(root), environ={})
        bundle = self.bundle()
        first_plan = preflight_bundle(target, bundle)
        second_plan = preflight_bundle(target, bundle)
        winner = InstallationTransaction(first_plan)
        winner.begin()
        lock_before = winner.lock_path.read_bytes()
        journal_before = winner.journal_path.read_bytes()
        with self.assertRaises(InstallError) as caught:
            run_asset_transaction(second_plan)
        self.assertEqual("installer-locked", caught.exception.reason)
        self.assertEqual(lock_before, winner.lock_path.read_bytes())
        self.assertEqual(journal_before, winner.journal_path.read_bytes())

    def test_stale_preflight_refuses_prior_recovery_journal_after_lock(self):
        from omama_cli.install import InstallError, preflight_bundle, run_asset_transaction
        from omama_cli.target import resolve_target

        root = self.make_repo()
        target = resolve_target(str(root), environ={})
        bundle = self.bundle()
        first_plan = preflight_bundle(target, bundle)
        stale_plan = preflight_bundle(target, bundle)

        def prepare(transaction):
            staging = transaction.reserve_owned_tree(".omama/runtime")
            staging.mkdir()
            (staging / "owned.txt").write_bytes(b"owned synthetic runtime\n")
            transaction.publish_owned_tree(staging, ".omama/runtime")

        external = root / ".omama" / "runtime" / "external.txt"

        def edit_then_fail(_transaction):
            external.write_bytes(b"ordinary external edit after publication\n")
            raise RuntimeError("injected stale-preflight recovery")

        with self.assertRaises(InstallError) as first_error:
            run_asset_transaction(first_plan, prepare=prepare, after_publication=edit_then_fail)
        self.assertEqual("recovery-required", first_error.exception.reason)
        journal = root / ".omama" / "install-journal.json"
        prior_journal = journal.read_bytes()
        prior_runtime = _tree_bytes(root / ".omama" / "runtime")
        prior_card = (root / "CARD.yaml").read_bytes()
        self.assertFalse((root / ".omama" / "install.lock").exists())

        with self.assertRaises(InstallError) as stale_error:
            run_asset_transaction(stale_plan, prepare=prepare)
        self.assertEqual("unfinished-install", stale_error.exception.reason)
        self.assertEqual(prior_journal, journal.read_bytes())
        self.assertEqual(prior_runtime, _tree_bytes(root / ".omama" / "runtime"))
        self.assertEqual(b"ordinary external edit after publication\n", external.read_bytes())
        self.assertEqual(prior_card, (root / "CARD.yaml").read_bytes())
        self.assertFalse((root / ".omama" / "install.lock").exists())

    def test_failure_after_publication_conditionally_rolls_back(self):
        from omama_cli.install import InstallError, preflight_bundle, run_asset_transaction
        from omama_cli.target import resolve_target

        root = self.make_repo()
        before = _tree_bytes(root)
        plan = preflight_bundle(resolve_target(str(root), environ={}), self.bundle())

        def fail(_transaction):
            raise RuntimeError("injected-after-publication")

        with self.assertRaisesRegex(InstallError, "injected-after-publication"):
            run_asset_transaction(plan, after_publication=fail)
        self.assertEqual(before, _tree_bytes(root))
        self.assertFalse((root / ".omama").exists())

    def test_intervening_write_after_preflight_is_preserved_and_refused(self):
        from omama_cli.install import InstallError, preflight_bundle, run_asset_transaction
        from omama_cli.target import resolve_target

        root = self.make_repo()
        plan = preflight_bundle(resolve_target(str(root), environ={}), self.bundle())
        path = root / "tools" / "omama" / "a.py"
        path.parent.mkdir(parents=True)
        external = b"arrived after preflight\n"
        path.write_bytes(external)
        with self.assertRaises(InstallError) as caught:
            run_asset_transaction(plan)
        self.assertEqual("concurrent-edit", caught.exception.reason)
        self.assertEqual(external, path.read_bytes())
        self.assertFalse((root / ".omama").exists())

    def test_intervening_edit_survives_and_leaves_recovery_journal(self):
        from omama_cli.install import InstallError, preflight_bundle, run_asset_transaction
        from omama_cli.target import resolve_target

        root = self.make_repo()
        plan = preflight_bundle(resolve_target(str(root), environ={}), self.bundle())
        external = b"#!/bin/sh\necho external\n"

        def edit_then_fail(_transaction):
            (root / ".githooks" / "pre-commit").write_bytes(external)
            raise RuntimeError("injected-intervening-edit")

        with self.assertRaises(InstallError) as caught:
            run_asset_transaction(plan, after_publication=edit_then_fail)
        self.assertEqual("recovery-required", caught.exception.reason)
        self.assertTrue(caught.exception.incomplete)
        self.assertEqual(external, (root / ".githooks" / "pre-commit").read_bytes())
        journal = json.loads((root / ".omama" / "install-journal.json").read_text(encoding="utf-8"))
        self.assertEqual("recovery-required", journal["status"])
        self.assertFalse((root / ".omama" / "install.lock").exists())

    @unittest.skipUnless(
        os.environ.get("OMAMA_INSTALLED_TOOL_PYTHON") and os.environ.get("OMAMA_EXPLICIT_PYTHON"),
        "installed public recovery proof requires the installed tool and explicit interpreter",
    )
    def test_documented_manual_recovery_preserves_external_edit_and_allows_public_retry(self):
        import base64

        from omama_cli.bundle import load_bundle
        from omama_cli.install import InstallError, preflight_bundle, run_asset_transaction
        from omama_cli.target import resolve_target, safe_destination

        source = Path(__file__).resolve().parents[2]
        recovery_en = source / "cli" / "RECOVERY.md"
        recovery_pt = source / "cli" / "RECOVERY.pt-BR.md"
        self.assertTrue(recovery_en.is_file(), "paired English manual-recovery procedure is absent")
        self.assertTrue(recovery_pt.is_file(), "paired PT-BR manual-recovery procedure is absent")
        self.assertIn("RECOVERY.md", (source / "cli" / "README.md").read_text(encoding="utf-8"))
        self.assertIn("cli/RECOVERY.md", (source / "QUICKSTART.md").read_text(encoding="utf-8"))
        self.assertIn("cli/RECOVERY.pt-BR.md", (source / "QUICKSTART.pt-BR.md").read_text(encoding="utf-8"))

        root = self.make_repo()
        review = root / "CARD.review.md"
        review.write_bytes(b"synthetic protected review evidence\n")
        card_before = (root / "CARD.yaml").read_bytes()
        review_before = review.read_bytes()
        index_before = (root / ".git" / "index").read_bytes()
        external = root / "privacy-deny.json"
        external_bytes = b'{"deny_regexes":[],"deny_filenames":[],"tokens_file":null,"team":"preserved"}\n'

        def edit_then_fail(_transaction):
            external.write_bytes(external_bytes)
            raise RuntimeError("injected documented-recovery case")

        bundle = load_bundle()
        with self.assertRaises(InstallError) as failed:
            run_asset_transaction(
                preflight_bundle(resolve_target(str(root), environ={}), bundle),
                after_publication=edit_then_fail,
            )
        self.assertEqual("recovery-required", failed.exception.reason)
        lock = root / ".omama" / "install.lock"
        journal_path = root / ".omama" / "install-journal.json"
        self.assertFalse(lock.exists())
        journal_bytes = journal_path.read_bytes()
        journal = json.loads(journal_bytes.decode("utf-8"))
        self.assertEqual(1, journal["schema"])
        self.assertEqual("recovery-required", journal["status"])
        self.assertTrue(journal["owner"])

        evidence = Path(tempfile.mkdtemp(prefix="manual-recovery-evidence-", dir=_test_root()))
        (evidence / "install-journal.json").write_bytes(journal_bytes)
        (evidence / "external-privacy-deny.json").write_bytes(external.read_bytes())
        divergent = []
        for record in reversed(journal["operations"]):
            if not record.get("applied"):
                continue
            path = safe_destination(root, record["relative"])
            current = path.read_bytes() if path.is_file() else None
            current_sha = hashlib.sha256(current).hexdigest() if current is not None else None
            before = record["before"]
            already_restored = (
                (before["kind"] == "missing" and current is None)
                or (
                    before["kind"] == "file"
                    and current_sha == before.get("sha256")
                    and len(current) == before.get("size")
                )
            )
            if already_restored:
                continue
            if current_sha != record["after_sha256"]:
                divergent.append(record["relative"])
                continue
            if before["kind"] == "missing":
                path.unlink()
            elif before["kind"] == "file":
                path.write_bytes(base64.b64decode(before["bytes_b64"]))
                path.chmod(before["mode"])
            else:
                self.fail("representative recovery encountered an unsupported before-image")
        self.assertEqual(["privacy-deny.json"], divergent)
        ownership = {
            entry["destination"]: entry["ownership"] for entry in bundle.manifest["files"]
        }
        self.assertEqual("editable-bootstrap", ownership["privacy-deny.json"])
        self.assertEqual(external_bytes, external.read_bytes())
        self.assertEqual(journal_bytes, (evidence / "install-journal.json").read_bytes())
        journal_path.unlink()

        tool_python = Path(os.environ["OMAMA_INSTALLED_TOOL_PYTHON"])
        cli = tool_python.parent / ("omama.exe" if os.name == "nt" else "omama")
        explicit = os.environ["OMAMA_EXPLICIT_PYTHON"]
        env = os.environ.copy()
        for key in list(env):
            if key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "PYTHONPATH", "VIRTUAL_ENV") \
                    or key.startswith("GIT_CONFIG_") or key.startswith("OMAMA_"):
                env.pop(key, None)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        retry = _run(str(cli), "init", str(root), "--python", explicit, cwd=root, env=env)
        self.assertEqual(0, retry.returncode, retry.stdout + retry.stderr)
        self.assertIn("INSTALLED", retry.stdout)
        self.assertEqual(external_bytes, external.read_bytes())
        self.assertEqual(card_before, (root / "CARD.yaml").read_bytes())
        self.assertEqual(review_before, review.read_bytes())
        self.assertEqual(index_before, (root / ".git" / "index").read_bytes())
        self.assertEqual(journal_bytes, (evidence / "install-journal.json").read_bytes())
        self.assertFalse(journal_path.exists())
        self.assertFalse(lock.exists())
        state = json.loads((root / ".omama" / "state.json").read_text(encoding="utf-8"))
        self.assertEqual("complete", state["status"])

    def test_failure_at_selftest_boundary_rolls_back_state_and_assets(self):
        from omama_cli.install import InstallError, preflight_bundle, run_asset_transaction
        from omama_cli.target import resolve_target

        root = self.make_repo()
        before = _tree_bytes(root)

        def selftest_failure(_transaction):
            self.assertTrue((root / ".omama" / "state.json").exists())
            raise RuntimeError("injected-selftest-stage")

        with self.assertRaisesRegex(InstallError, "injected-selftest-stage"):
            run_asset_transaction(
                preflight_bundle(resolve_target(str(root), environ={}), self.bundle()),
                before_finish=selftest_failure,
            )
        self.assertEqual(before, _tree_bytes(root))
        self.assertFalse((root / ".omama").exists())

    def test_tracked_local_state_and_unsafe_destination_refuse(self):
        from omama_cli.install import InstallError, preflight_bundle
        from omama_cli.target import TargetError, resolve_target

        root = self.make_repo()
        local = root / ".claude" / "settings.local.json"
        local.parent.mkdir()
        local.write_bytes(b"{}\n")
        self.assertEqual(0, _run("git", "-C", str(root), "add", "-f", ".claude/settings.local.json").returncode)
        with self.assertRaises(InstallError) as caught:
            preflight_bundle(resolve_target(str(root), environ={}), self.bundle())
        self.assertEqual("tracked-local-state", caught.exception.reason)
        self.assertEqual(0, _run("git", "-C", str(root), "reset", "--", ".claude/settings.local.json").returncode)
        with self.assertRaises(TargetError) as caught:
            preflight_bundle(resolve_target(str(root), environ={}), self.bundle(destination_override="../escape.py"))
        self.assertEqual("path-escape", caught.exception.reason)

    def test_read_only_destination_is_named_before_publication(self):
        from omama_cli.install import InstallError, preflight_bundle
        from omama_cli.target import resolve_target

        root = self.make_repo()
        path = root / "tools" / "omama" / "a.py"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"print('immutable')\n")
        path.chmod(0o444)
        try:
            with self.assertRaises(InstallError) as caught:
                preflight_bundle(resolve_target(str(root), environ={}), self.bundle())
            self.assertEqual("read-only-destination", caught.exception.reason)
            self.assertFalse((root / ".omama").exists())
        finally:
            path.chmod(0o644)

    def test_non_repository_bare_repository_and_unsafe_command_path_refuse(self):
        from omama_cli.target import TargetError, resolve_target

        plain = Path(tempfile.mkdtemp(prefix="plain-", dir=_test_root()))
        with self.assertRaises(TargetError) as caught:
            resolve_target(str(plain), environ={})
        self.assertEqual("unsupported-git-target", caught.exception.reason)
        bare = Path(tempfile.mkdtemp(prefix="bare-", dir=_test_root()))
        self.assertEqual(0, _run("git", "init", "--bare", str(bare)).returncode)
        with self.assertRaises(TargetError) as caught:
            resolve_target(str(bare), environ={})
        self.assertEqual("unsupported-git-target", caught.exception.reason)
        unsafe = Path(tempfile.mkdtemp(prefix="unsafe-$-", dir=_test_root()))
        self.assertEqual(0, _run("git", "init", str(unsafe)).returncode)
        with self.assertRaises(TargetError) as caught:
            resolve_target(str(unsafe), environ={})
        self.assertEqual("unsupported-command-path", caught.exception.reason)

    def test_symlink_destination_escape_is_refused_when_host_supports_symlinks(self):
        from omama_cli.install import preflight_bundle
        from omama_cli.target import TargetError, resolve_target

        root = self.make_repo()
        outside = Path(tempfile.mkdtemp(prefix="outside-", dir=_test_root()))
        try:
            os.symlink(str(outside), str(root / "tools"), target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("host cannot create fixture symlink: {0}".format(type(exc).__name__))
        with self.assertRaises(TargetError) as caught:
            preflight_bundle(resolve_target(str(root), environ={}), self.bundle())
        self.assertEqual("path-reparse", caught.exception.reason)
        self.assertEqual({}, _tree_bytes(outside))


if __name__ == "__main__":
    unittest.main()
