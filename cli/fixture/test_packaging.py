import copy
import hashlib
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


class CommandContractTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "omama_cli", *args],
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
        self.assertEqual(2, self.run_cli("init").returncode)
        self.assertIn("NOT-RUN", self.run_cli("init").stderr)
        self.assertEqual(2, self.run_cli("doctor").returncode)
        self.assertIn("NOT-RUN", self.run_cli("doctor").stderr)

    def test_unimplemented_commands_do_not_write_target(self):
        target = Path(tempfile.mkdtemp(prefix="command-", dir=_test_root()))
        sentinel = target / "sentinel.txt"
        sentinel.write_bytes(b"preserve me\n")
        before = {p.relative_to(target).as_posix(): p.read_bytes() for p in target.rglob("*") if p.is_file()}
        self.assertEqual(2, self.run_cli("init", str(target)).returncode)
        self.assertEqual(2, self.run_cli("doctor", str(target)).returncode)
        after = {p.relative_to(target).as_posix(): p.read_bytes() for p in target.rglob("*") if p.is_file()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
