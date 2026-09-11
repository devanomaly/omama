import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


def _test_root():
    value = os.environ.get("OMAMA_PACKAGING_TEST_ROOT")
    if not value:
        raise RuntimeError("OMAMA_PACKAGING_TEST_ROOT must name the allocated disposable root")
    root = Path(value).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return str(root)


class PackagingContractTests(unittest.TestCase):
    def setUp(self):
        from omama_cli.bundle import load_bundle

        self.bundle = load_bundle()

    def materialize(self):
        root = Path(tempfile.mkdtemp(prefix="bundle-", dir=_test_root()))
        for relative, data in self.bundle.files.items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        (root / "manifest.json").write_text(
            json.dumps(self.bundle.manifest, sort_keys=True), encoding="utf-8"
        )
        return root

    def test_complete_expanded_inventory_and_exact_hashes(self):
        expected_destinations = {
            "tools/omama/receipt-gate/receipt_gate.py",
            "tools/omama/receipt-gate/adapt/check_wiring.py",
            "tools/omama/work-order/validate_work_order.py",
            "tools/omama/output-discipline/scripts/check_artifact.py",
            "tools/omama/privacy-hook/scan_staged.py",
            ".githooks/privacy-pre-commit",
            ".githooks/pre-commit",
            ".githooks/pre-merge-commit",
            "privacy-deny.json",
            "work-order.template.yaml",
            "docs/templates/omama/CLAUDE.starter.md",
            "docs/templates/omama/PLAN.md",
            "docs/templates/omama/REVIEW.md",
            "tools/omama/LICENSE",
            "tools/omama/PROVENANCE.md",
        }
        entries = self.bundle.manifest["files"]
        self.assertEqual(expected_destinations, {entry["destination"] for entry in entries})
        for entry in entries:
            data = self.bundle.files[entry["resource"]]
            self.assertEqual(entry["sha256"], hashlib.sha256(data).hexdigest())

    def test_missing_named_resource_is_rejected(self):
        from omama_cli.bundle import BundleError, validate_bundle_directory

        root = self.materialize()
        (root / "files/tools/omama/work-order/validate_work_order.py").unlink()
        with self.assertRaisesRegex(BundleError, "missing-resource.*validate_work_order.py"):
            validate_bundle_directory(root)

    def test_missing_license_is_rejected(self):
        from omama_cli.bundle import BundleError, validate_bundle_directory

        root = self.materialize()
        (root / "files/tools/omama/LICENSE").unlink()
        with self.assertRaisesRegex(BundleError, "missing-license"):
            validate_bundle_directory(root)

    def test_missing_source_identity_is_rejected(self):
        from omama_cli.bundle import BundleError, validate_bundle_directory

        root = self.materialize()
        manifest = copy.deepcopy(self.bundle.manifest)
        del manifest["source"]["revision"]
        (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(BundleError, "missing-source-identity"):
            validate_bundle_directory(root)

    def test_wrong_hash_is_rejected(self):
        from omama_cli.bundle import BundleError, validate_bundle_directory

        root = self.materialize()
        target = root / "files/tools/omama/receipt-gate/receipt_gate.py"
        target.write_bytes(target.read_bytes() + b"\n# drift\n")
        with self.assertRaisesRegex(BundleError, "wrong-hash.*receipt_gate.py"):
            validate_bundle_directory(root)

    def test_omitted_manifest_entry_is_rejected_even_if_source_bytes_exist(self):
        from omama_cli.bundle import BundleError, validate_bundle_directory

        root = self.materialize()
        manifest = copy.deepcopy(self.bundle.manifest)
        manifest["files"] = [
            entry for entry in manifest["files"]
            if entry["destination"] != "tools/omama/output-discipline/scripts/check_artifact.py"
        ]
        (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(BundleError, "incomplete-resource-inventory.*check_artifact.py"):
            validate_bundle_directory(root)

    def test_dirty_identity_never_claims_exact_revision(self):
        source = self.bundle.manifest["source"]
        if source["dirty"]:
            self.assertIsNone(source["exact_revision"])
            self.assertRegex(source["dirty_digest"], r"^[0-9a-f]{64}$")
            self.assertEqual(source["identity_inputs_digest"], source["dirty_digest"])
        self.assertIsInstance(source["modified_after_identity_capture"], bool)

    def test_ownership_primitives_are_conservative(self):
        from omama_cli.identity import ExistingState, classify_existing

        immutable = next(e for e in self.bundle.manifest["files"] if e["ownership"] == "immutable")
        editable = next(e for e in self.bundle.manifest["files"] if e["ownership"] == "editable-bootstrap")
        immutable_bytes = self.bundle.files[immutable["resource"]]
        editable_bytes = self.bundle.files[editable["resource"]]
        self.assertEqual(ExistingState.MISSING, classify_existing(self.bundle, immutable, None, None))
        self.assertEqual(ExistingState.ADOPTABLE_IDENTICAL, classify_existing(self.bundle, immutable, immutable_bytes, None))
        current = self.bundle.manifest["bundle_id"]
        self.assertEqual(ExistingState.IMMUTABLE_DRIFT, classify_existing(self.bundle, immutable, b"changed", current))
        self.assertEqual(ExistingState.EDITABLE_PRESERVE, classify_existing(self.bundle, editable, b"team edit", current))
        self.assertEqual(ExistingState.PACKAGE_UPDATE, classify_existing(self.bundle, immutable, immutable_bytes, "older"))
        self.assertEqual(ExistingState.SAME_BUNDLE, classify_existing(self.bundle, immutable, immutable_bytes, current))

    def test_manifest_identity_is_an_installable_resource_without_self_hash_claim(self):
        identity = self.bundle.manifest["installed_identity"]
        self.assertEqual("tools/omama/manifest.json", identity["destination"])
        self.assertEqual("manifest.json", identity["resource"])
        self.assertIn("local installation state", identity["hash_policy"])
        self.assertEqual(self.bundle.manifest, json.loads(self.bundle.manifest_bytes.decode("utf-8")))

    def test_bundle_id_rejects_semantic_manifest_tamper(self):
        from omama_cli.bundle import BundleError, validate_bundle_directory

        root = self.materialize()
        manifest = copy.deepcopy(self.bundle.manifest)
        manifest["package_version"] = "9.9.9"
        (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(BundleError, "wrong-bundle-identity"):
            validate_bundle_directory(root)

    def test_t4_inventory_classes_and_validated_entry_requirement(self):
        from omama_cli.identity import classify_existing

        by_ownership = {}
        for entry in self.bundle.manifest["files"]:
            by_ownership[entry["ownership"]] = by_ownership.get(entry["ownership"], 0) + 1
        self.assertEqual({"immutable": 8, "generated-wiring": 2, "editable-bootstrap": 5}, by_ownership)
        self.assertEqual(7, len(self.bundle.manifest["generated_local"]))
        fake = dict(self.bundle.manifest["files"][0])
        fake["destination"] = "unvalidated"
        with self.assertRaisesRegex(ValueError, "not from the validated bundle"):
            classify_existing(self.bundle, fake, b"", None)

    def test_all_cli_source_modules_are_identity_inputs(self):
        source_root = Path(__file__).resolve().parents[2]
        spec = importlib.util.spec_from_file_location(
            "omama_build_inventory", str(source_root / "build_backend" / "inventory.py")
        )
        inventory = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(inventory)
        package_sources = {
            path.relative_to(source_root).as_posix()
            for path in (source_root / "cli" / "omama_cli").glob("*.py")
        }
        self.assertTrue(package_sources)
        self.assertEqual(set(), package_sources - set(inventory.IDENTITY_INPUTS))


class CommandContractTests(unittest.TestCase):
    def run_cli(self, *args):
        from omama_cli.target import routing_names

        env = os.environ.copy()
        for key in routing_names(env):
            env.pop(key, None)
        return subprocess.run(
            [sys.executable, "-m", "omama_cli", *args],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

    def test_help_version_and_command_grammar(self):
        self.assertEqual(0, self.run_cli("--help").returncode)
        self.assertEqual(0, self.run_cli("--version").returncode)
        self.assertEqual(0, self.run_cli("init", "--help").returncode)
        self.assertEqual(0, self.run_cli("doctor", "--help").returncode)

    def test_commands_reject_explicit_non_git_target_without_writes(self):
        target = Path(tempfile.mkdtemp(prefix="command-", dir=_test_root()))
        sentinel = target / "sentinel.txt"
        sentinel.write_bytes(b"preserve me\n")
        before = {p.relative_to(target).as_posix(): p.read_bytes() for p in target.rglob("*") if p.is_file()}
        init = self.run_cli("init", str(target))
        doctor = self.run_cli("doctor", str(target))
        self.assertEqual(1, init.returncode)
        self.assertIn("unsupported-git-target", init.stderr)
        self.assertEqual(1, doctor.returncode)
        self.assertIn("unsupported-git-target", doctor.stderr)
        after = {p.relative_to(target).as_posix(): p.read_bytes() for p in target.rglob("*") if p.is_file()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()


class VersionAuthorityTests(unittest.TestCase):
    """Phase-B M4 (F27): one authoritative version across every surface."""

    def _pyproject_version(self):
        root = Path(__file__).resolve().parents[2]
        for line in (root / "pyproject.toml").read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("version ="):
                return stripped.split("=", 1)[1].strip().strip('"')
        raise AssertionError("pyproject.toml declares no version")

    def test_source_build_and_runtime_versions_agree(self):
        import omama_cli
        from build_backend import inventory

        declared = self._pyproject_version()
        self.assertEqual(declared, inventory.PACKAGE_VERSION,
                         "build inventory version disagrees with pyproject.toml")
        self.assertEqual(declared, omama_cli._SOURCE_VERSION,
                         "package source fallback version disagrees with pyproject.toml")
        # At runtime the installed distribution's metadata is the authority.
        self.assertEqual(declared, omama_cli.__version__)

    def test_built_wheel_metadata_and_manifest_agree_with_the_source_version(self):
        import json
        import zipfile

        wheel = os.environ.get("OMAMA_BUILT_WHEEL") or os.environ.get("OMAMA_T8_WHEEL")
        if not wheel:
            raise unittest.SkipTest("built-wheel version binding requires OMAMA_BUILT_WHEEL")
        declared = self._pyproject_version()
        with zipfile.ZipFile(wheel) as archive:
            manifest = json.loads(archive.read("omama_cli/_payload/manifest.json").decode("utf-8"))
            metadata_name = next(name for name in archive.namelist() if name.endswith(".dist-info/METADATA"))
            metadata = archive.read(metadata_name).decode("utf-8")
        self.assertEqual(declared, manifest["package_version"])
        self.assertIn("Version: " + declared, metadata)


class ManifestShapeTests(unittest.TestCase):
    """Phase-B M4 (F26): a malformed manifest is a named BundleError."""

    def _manifest(self):
        return {
            "schema": 1, "package_version": "0.1.0", "bundle_id": "0" * 64,
            "source": {"url": "u", "revision": "r", "dirty": True, "exact_revision": None,
                       "dirty_digest": "d", "identity_inputs_digest": "d",
                       "modified_after_identity_capture": False, "dirty_digest_policy": "p"},
            "license": {"destination": "tools/omama/LICENSE", "expression": "MIT"},
            "files": [{"resource": "files/0", "destination": "tools/omama/LICENSE",
                       "ownership": "immutable", "sha256": "a" * 64}],
            "required_destinations": ["tools/omama/LICENSE"],
            "installed_identity": {"destination": "tools/omama/manifest.json"},
        }

    def test_malformed_entries_raise_a_named_bundle_error(self):
        from omama_cli.bundle import BundleError, _validate_manifest

        for label, mutate in (
            ("non-object entry", lambda m: m.__setitem__("files", ["not-an-object"])),
            ("missing resource", lambda m: m["files"][0].pop("resource")),
            ("non-string destination", lambda m: m["files"][0].__setitem__("destination", 7)),
            ("bad hash", lambda m: m["files"][0].__setitem__("sha256", "nope")),
        ):
            manifest = self._manifest()
            mutate(manifest)
            with self.assertRaises(BundleError, msg=label):
                _validate_manifest(manifest, lambda name: b"", b"{}")


class BuildProvenanceTests(unittest.TestCase):
    """Phase-B M4 (F23/F24/C17): truthful identity, fresh staging, wheel-only."""

    def _root(self):
        value = os.environ.get("OMAMA_PACKAGING_TEST_ROOT") or os.environ.get("OMAMA_CLI_TEST_ROOT")
        if not value:
            raise unittest.SkipTest("a disposable root is required")
        path = Path(value)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def test_revision_is_claimed_only_when_git_describes_this_source_root(self):
        from build_backend import backend
        from unittest import mock

        own = "a" * 40
        absent_identity = Path(self._root()) / "absent-identity.json"

        def answers(toplevel, head):
            return lambda *args: {
                ("rev-parse", "--show-toplevel"): toplevel,
                ("rev-parse", "HEAD"): head,
                ("status", "--porcelain=v1", "--untracked-files=all"): "",
            }.get(args)

        # Git's top level is this source root: the revision is this project's,
        # and a clean tree earns an exact revision.
        with mock.patch.object(backend, "_git", side_effect=answers(str(backend.ROOT), own)), \
                mock.patch.object(backend, "IDENTITY_FILE", absent_identity):
            self.assertTrue(backend._git_owns_source_root())
            source = backend._identity()
        self.assertEqual(own, source["revision"])
        self.assertEqual(own, source["exact_revision"])
        self.assertFalse(source["dirty"])

        # Git resolves to some enclosing repository instead: nothing is claimed.
        with mock.patch.object(backend, "_git", side_effect=answers("/some/enclosing/repository", own)):
            self.assertFalse(backend._git_owns_source_root())

        # Not a Git checkout at all: still unavailable, never "clean".
        with mock.patch.object(backend, "_git", side_effect=answers(None, None)), \
                mock.patch.object(backend, "IDENTITY_FILE", absent_identity):
            self.assertFalse(backend._git_owns_source_root())
            source = backend._identity()
        self.assertEqual("unknown", source["revision"])
        self.assertIsNone(source["exact_revision"])
        self.assertTrue(source["dirty"])

    def test_enclosing_repository_revision_is_never_published_as_omama_identity(self):
        from build_backend import backend
        from unittest import mock

        foreign = "f" * 40
        with mock.patch.object(backend, "_git", side_effect=lambda *args: {
                ("rev-parse", "--show-toplevel"): "/enclosing/foreign/repo",
                ("rev-parse", "HEAD"): foreign,
                ("status", "--porcelain=v1", "--untracked-files=all"): "",
        }.get(args)), mock.patch.object(backend, "IDENTITY_FILE", Path(self._root()) / "absent-identity.json"):
            source = backend._identity()
        self.assertNotEqual(foreign, source["revision"])
        self.assertEqual("unknown", source["revision"])
        self.assertIsNone(source["exact_revision"])
        self.assertTrue(source["dirty"], "an unidentifiable source tree must not claim to be clean")

    def test_stale_setuptools_staging_is_discarded_before_generation(self):
        from build_backend import backend
        from unittest import mock

        staging = Path(self._root()) / "fake-source-root"
        build_root = staging / "build" / "lib" / "omama_cli" / "_payload" / "files"
        build_root.mkdir(parents=True, exist_ok=True)
        stale = build_root / "STALE-LEFTOVER.txt"
        stale.write_text("payload file from a previous build\n", encoding="utf-8")
        with mock.patch.object(backend, "ROOT", staging):
            backend._discard_stale_build_output()
        self.assertFalse(stale.exists(), "stale staging survived into the next build")
        self.assertFalse((staging / "build").exists())

    def test_phase_one_refuses_to_build_a_source_distribution(self):
        from build_backend import backend

        with self.assertRaises(RuntimeError) as caught:
            backend.build_sdist(str(self._root()))
        message = str(caught.exception)
        self.assertIn("wheel-only", message)
        # The refusal must not claim any equivalence it has not established.
        self.assertNotIn("equivalent", message.lower().replace("equivalence is claimed", ""))

    def test_build_lock_serializes_generation_and_is_released(self):
        from build_backend import backend
        from unittest import mock

        staging = Path(self._root()) / "lock-source-root"
        staging.mkdir(parents=True, exist_ok=True)
        lock = staging / ".omama-build.lock"
        with mock.patch.object(backend, "BUILD_LOCK", lock):
            with backend._build_lock():
                self.assertTrue(lock.exists(), "the build lock was not taken")
            self.assertFalse(lock.exists(), "the build lock was not released")
