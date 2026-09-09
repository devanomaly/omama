"""T9 exact-installed-command admission and init integration fixtures."""

import json
import io
import os
import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import test_install as install_fixture


class InstalledAdmissionContractTests(unittest.TestCase):
    def setUp(self):
        tool = os.environ.get("OMAMA_T9_CLI_PYTHON")
        explicit = os.environ.get("OMAMA_EXPLICIT_PYTHON")
        if not tool or not explicit:
            self.skipTest("installed T9 proof requires OMAMA_T9_CLI_PYTHON and OMAMA_EXPLICIT_PYTHON")
        self.tool = Path(tool)
        self.explicit = Path(explicit)

    def make_repo(self):
        return install_fixture.InstallerContractTests(
            "test_inherited_git_routing_refuses_before_target_writes"
        ).make_repo()

    def run_cli(self, root, *arguments):
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        env.pop("VIRTUAL_ENV", None)
        for key in ("OMAMA_CARD", "OMAMA_VALIDATOR", "OMAMA_CHECK_ARTIFACT", "OMAMA_VERIFY_TIMEOUT"):
            env.pop(key, None)
        return subprocess.run(
            [str(self.tool), "-B", "-m", "omama_cli"] + list(arguments),
            cwd=str(root), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", check=False,
        )

    def assert_admission_output(self, result):
        for name in (
            "receipt-s1", "receipt-s3", "missing-validator", "missing-checker",
            "missing-gate", "privacy-token-states", "privacy-pre-commit",
            "privacy-pre-merge-commit", "missing-scanner", "missing-wrapper",
            "complete-payload-commit",
        ):
            self.assertIn("ADMISSION-OK[{0}]".format(name), result.stdout)
        self.assertIn("ADMISSION-OK[privacy-token-null]", result.stdout)
        self.assertIn("ADMISSION-OK[privacy-token-omitted]", result.stdout)
        self.assertNotIn("OMAMA_ADMISSION_LITERAL_", result.stdout + result.stderr)

    def test_first_init_requires_complete_installed_admission(self):
        root = self.make_repo()
        card_before = (root / "CARD.yaml").read_bytes()
        index_before = (root / ".git" / "index").read_bytes()
        result = self.run_cli(root, "init", str(root), "--python", str(self.explicit))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("ADMISSION-OK", result.stdout)
        self.assertIn("INSTALLED", result.stdout)
        self.assertIn("ADOPT STARTER", result.stdout)
        self.assertIn("PER-OPERATOR OUTPUT-DISCIPLINE BLOCK", result.stdout)
        self.assert_admission_output(result)
        state = json.loads((root / ".omama" / "state.json").read_text(encoding="utf-8"))
        self.assertEqual("complete", state["status"])
        self.assertEqual([], state["managed_omama_overrides"])
        self.assertEqual(
            '"{0}" "$CLAUDE_PROJECT_DIR/tools/omama/receipt-gate/receipt_gate.py"'.format(
                self.explicit.as_posix()),
            state["settings_command"],
        )
        self.assertEqual(card_before, (root / "CARD.yaml").read_bytes())
        self.assertEqual(index_before, (root / ".git" / "index").read_bytes())
        self.assertFalse((root / ".omama" / "install.lock").exists())
        self.assertFalse((root / ".omama" / "install-journal.json").exists())
        self.assertEqual([], list((root / ".omama").glob(".admission-*")))

    def test_default_managed_first_init_uses_created_platform_runtime(self):
        root = self.make_repo()
        card_before = (root / "CARD.yaml").read_bytes()
        index_before = (root / ".git" / "index").read_bytes()
        result = self.run_cli(root, "init", str(root))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assert_admission_output(result)
        state = json.loads((root / ".omama" / "state.json").read_text(encoding="utf-8"))
        self.assertEqual("complete", state["status"])
        self.assertEqual("managed", state["runtime_mode"])
        interpreter = Path(state["receipt_interpreter"])
        self.assertTrue(interpreter.is_file())
        expected = root / ".omama" / "runtime" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        self.assertEqual(expected.resolve(), interpreter.resolve())
        doctor = self.run_cli(root, "doctor", str(root))
        self.assertEqual(0, doctor.returncode, doctor.stdout + doctor.stderr)
        self.assertIn("DOCTOR-OK", doctor.stdout)
        self.assertEqual(card_before, (root / "CARD.yaml").read_bytes())
        self.assertEqual(index_before, (root / ".git" / "index").read_bytes())

    def test_same_bundle_rerun_preserves_team_config_and_repeats_private_admission(self):
        root = self.make_repo()
        first = self.run_cli(root, "init", str(root), "--python", str(self.explicit))
        self.assertEqual(0, first.returncode, first.stdout + first.stderr)
        config_path = root / "privacy-deny.json"
        custom = json.loads(config_path.read_text(encoding="utf-8"))
        custom["team_annotation"] = "preserve-this-edit"
        custom_bytes = (json.dumps(custom, indent=2, sort_keys=True) + "\n").encode("utf-8")
        config_path.write_bytes(custom_bytes)
        card_before = (root / "CARD.yaml").read_bytes()
        index_before = (root / ".git" / "index").read_bytes()
        rerun = self.run_cli(root, "init", str(root), "--python", str(self.explicit))
        self.assertEqual(0, rerun.returncode, rerun.stdout + rerun.stderr)
        self.assert_admission_output(rerun)
        self.assertEqual(custom_bytes, config_path.read_bytes())
        self.assertEqual(card_before, (root / "CARD.yaml").read_bytes())
        self.assertEqual(index_before, (root / ".git" / "index").read_bytes())
        local = json.loads((root / ".claude" / "settings.local.json").read_text(encoding="utf-8"))
        self.assertEqual(1, json.dumps(local).count("receipt_gate.py"))
        ignore = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
        for line in (".claude/settings.local.json", ".omama/", "privacy-tokens.txt"):
            self.assertEqual(1, ignore.count(line))
        self.assertEqual("complete", json.loads((root / ".omama" / "state.json").read_text(encoding="utf-8"))["status"])

    def test_deleted_inert_editable_template_stays_deleted_and_rerun_admits_remaining_payload(self):
        root = self.make_repo()
        first = self.run_cli(root, "init", str(root), "--python", str(self.explicit))
        self.assertEqual(0, first.returncode, first.stdout + first.stderr)
        deleted = root / "docs" / "templates" / "omama" / "PLAN.md"
        deleted.unlink()
        card_before = (root / "CARD.yaml").read_bytes()
        index_before = (root / ".git" / "index").read_bytes()
        doctor = self.run_cli(root, "doctor", str(root))
        self.assertEqual(0, doctor.returncode, doctor.stdout + doctor.stderr)
        self.assertIn("editable bootstrap is absent/preserved", doctor.stdout)
        rerun = self.run_cli(root, "init", str(root), "--python", str(self.explicit))
        self.assertEqual(0, rerun.returncode, rerun.stdout + rerun.stderr)
        self.assert_admission_output(rerun)
        self.assertIn("ADMISSION-WARNING[editable-absent]", rerun.stdout)
        self.assertIn("all 14 currently installed manifest files committed", rerun.stdout)
        self.assertFalse(deleted.exists())
        self.assertEqual(card_before, (root / "CARD.yaml").read_bytes())
        self.assertEqual(index_before, (root / ".git" / "index").read_bytes())

    def test_no_git_config_prepared_then_same_bundle_activation_rerun_completes(self):
        root = self.make_repo()
        card_before = (root / "CARD.yaml").read_bytes()
        index_before = (root / ".git" / "index").read_bytes()
        prepared = self.run_cli(
            root, "init", str(root), "--python", str(self.explicit), "--no-git-config")
        self.assertEqual(2, prepared.returncode, prepared.stdout + prepared.stderr)
        self.assertIn("PREPARED", prepared.stdout)
        self.assertIn("mandatory admission was not attempted", prepared.stderr)
        self.assertNotIn("ADMISSION-OK", prepared.stdout)
        state = json.loads((root / ".omama" / "state.json").read_text(encoding="utf-8"))
        self.assertEqual("prepared", state["status"])
        self.assertEqual("manual-required", state["activation_status"])
        absent = subprocess.run(
            ["git", "-C", str(root), "config", "--local", "--get", "core.hooksPath"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        self.assertEqual(1, absent.returncode)
        subprocess.run(
            ["git", "-C", str(root), "config", "--local", "core.hooksPath", ".githooks"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
        )
        completed = self.run_cli(
            root, "init", str(root), "--python", str(self.explicit), "--no-git-config")
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assert_admission_output(completed)
        self.assertEqual("complete", json.loads((root / ".omama" / "state.json").read_text(encoding="utf-8"))["status"])
        self.assertEqual(card_before, (root / "CARD.yaml").read_bytes())
        self.assertEqual(index_before, (root / ".git" / "index").read_bytes())

    def test_selftest_not_run_is_init_failure_and_rolls_back(self):
        from omama_cli.bundle import validate_bundle_directory
        from omama_cli.command import main
        from omama_cli.selftest import AdmissionReport

        root = self.make_repo()
        before = install_fixture._tree_bytes(root)

        def not_run(_target, _state, _scratch):
            report = AdmissionReport()
            report.add("NOT-RUN", "synthetic-capability", "deliberate capability absence")
            return report

        stdout = io.StringIO()
        stderr = io.StringIO()
        payload = self.tool.parent.parent / "Lib" / "site-packages" / "omama_cli" / "_payload"
        bundle = validate_bundle_directory(payload)
        with patch("omama_cli.command.load_bundle", return_value=bundle), \
                patch("omama_cli.command.admission", not_run), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            result = main(["init", str(root), "--python", str(self.explicit)])
        self.assertEqual(1, result, stdout.getvalue() + stderr.getvalue())
        self.assertIn("ADMISSION-NOT-RUN", stderr.getvalue())
        self.assertIn("VIOLATION[admission-not-run]", stderr.getvalue())
        self.assertEqual(before, install_fixture._tree_bytes(root))
        self.assertFalse((root / ".omama").exists())


if __name__ == "__main__":
    unittest.main()
