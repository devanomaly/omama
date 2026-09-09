import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import test_install as install_fixture


def _files(root):
    root = Path(root)
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*") if path.is_file()
    }


class DoctorContractTests(unittest.TestCase):
    def setUp(self):
        self.wheel = os.environ.get("OMAMA_T8_WHEEL")
        self.explicit = os.environ.get("OMAMA_EXPLICIT_PYTHON")
        if not self.wheel or not self.explicit:
            self.skipTest("OMAMA_T8_WHEEL and OMAMA_EXPLICIT_PYTHON are required")

    def make_repo(self):
        return install_fixture.InstallerContractTests(
            "test_inherited_git_routing_refuses_before_target_writes"
        ).make_repo()

    def run_cli(self, root, *arguments, extra_env=None):
        env = os.environ.copy()
        env["PYTHONPATH"] = self.wheel
        env["TMP"] = install_fixture._test_root()
        env["TEMP"] = install_fixture._test_root()
        env["TMPDIR"] = install_fixture._test_root()
        for key in ("OMAMA_VALIDATOR", "OMAMA_CHECK_ARTIFACT", "OMAMA_CARD", "OMAMA_VERIFY_TIMEOUT"):
            env.pop(key, None)
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [sys.executable, "-B", "-m", "omama_cli"] + list(arguments),
            cwd=str(root), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", check=False,
        )

    def run_cli_without_bytecode_flag(self, root, *arguments):
        env = os.environ.copy()
        env["PYTHONPATH"] = self.wheel
        env.pop("PYTHONDONTWRITEBYTECODE", None)
        for key in ("TMP", "TEMP", "TMPDIR"):
            env[key] = install_fixture._test_root()
        for key in ("OMAMA_VALIDATOR", "OMAMA_CHECK_ARTIFACT", "OMAMA_CARD", "OMAMA_VERIFY_TIMEOUT"):
            env.pop(key, None)
        return subprocess.run(
            [sys.executable, "-m", "omama_cli"] + list(arguments),
            cwd=str(root), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", check=False,
        )

    def prepare(self, complete=True, managed=False):
        root = self.make_repo()
        args = ["init", str(root)]
        if not managed:
            args.extend(["--python", self.explicit])
        result = self.run_cli(root, *args)
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        state_path = root / ".omama" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if complete:
            state["status"] = "complete"
            state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return root

    def rebind_installed_manifest(self, root, destination, data):
        manifest_path = root / "tools" / "omama" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entry = next(item for item in manifest["files"] if item["destination"] == destination)
        (root / destination).write_bytes(data)
        entry["sha256"] = hashlib.sha256(data).hexdigest()
        entry["size"] = len(data)
        basis = {
            "package_version": manifest["package_version"], "source": manifest["source"],
            "license": manifest["license"],
            "files": [{key: item[key] for key in ("destination", "ownership", "sha256")} for item in manifest["files"]],
            "generated_local": manifest["generated_local"],
            "ownership_policy": manifest["ownership_policy"],
        }
        manifest["bundle_id"] = hashlib.sha256(
            json.dumps(basis, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
        manifest_path.write_bytes(manifest_bytes)
        state_path = root / ".omama" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["bundle_id"] = manifest["bundle_id"]
        state["manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
        state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def test_full_doctor_executes_all_rows_and_preserves_target(self):
        root = self.prepare(complete=True)
        before = _files(root)
        result = self.run_cli(root, "doctor", str(root))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("DOCTOR-OK", result.stdout)
        for name in (
            "settings-command", "settings-execution", "interpreter",
            "validator-probe", "checker-probe", "vendor-identity",
            "privacy-components", "privacy-interpreter", "token-state",
            "clone-worktree", "partial-install", "relocation",
        ):
            self.assertIn("[{0}]".format(name), result.stdout + result.stderr)
        self.assertIn("valid synthetic card (0)", result.stdout)
        self.assertIn("missing-non-findings (1)", result.stdout)
        self.assertIn("zero literals", result.stdout)
        self.assertIn("user/managed/CLI-session settings are not claimed observable", result.stdout)
        self.assertEqual(before, _files(root))

    def test_static_only_is_incomplete_and_known_drift_dominates(self):
        root = self.prepare(complete=True)
        before = _files(root)
        result = self.run_cli(root, "doctor", str(root), "--static-only")
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        for name in ("settings-execution", "validator-probe", "checker-probe", "privacy-interpreter"):
            self.assertIn("NOT-RUN[{0}]".format(name), result.stderr)
        self.assertEqual(before, _files(root))
        gate = root / "tools" / "omama" / "receipt-gate" / "receipt_gate.py"
        gate.write_bytes(gate.read_bytes() + b"\n# synthetic drift\n")
        drifted = _files(root)
        result = self.run_cli(root, "doctor", str(root), "--static-only")
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("VIOLATION[immutable-drift]", result.stderr)
        self.assertIn("NOT-RUN[validator-probe]", result.stderr)
        self.assertEqual(drifted, _files(root))

    def test_prepared_state_is_incomplete_but_dynamic_probes_still_run(self):
        root = self.prepare(complete=False)
        result = self.run_cli(root, "doctor", str(root))
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("NOT-RUN[admission-state]", result.stderr)
        self.assertIn("OK[validator-probe]", result.stdout)
        self.assertIn("OK[checker-probe]", result.stdout)
        self.assertNotIn("DOCTOR-OK", result.stdout)

    def test_editable_drift_is_distinct_from_immutable_drift(self):
        root = self.prepare(complete=True)
        template = root / "docs" / "templates" / "omama" / "PLAN.md"
        template.write_bytes(b"team edited inert template\n")
        before = _files(root)
        result = self.run_cli(root, "doctor", str(root))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("OK[editable-drift]", result.stdout)
        self.assertNotIn("VIOLATION[immutable-drift]", result.stderr)
        self.assertEqual(before, _files(root))

    def test_process_and_project_environment_sources_and_ambiguity_are_visible(self):
        root = self.prepare(complete=True)
        source_validator = str(Path(__file__).resolve().parents[2] / "work-order" / "validate_work_order.py")
        result = self.run_cli(
            root, "doctor", str(root),
            extra_env={"OMAMA_VALIDATOR": source_validator},
        )
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("OMAMA_VALIDATOR source: process environment", result.stdout)
        self.assertIn("VIOLATION[dependency-resolution]", result.stderr)
        outside_card = str(Path(install_fixture._test_root()) / "outside-card.yaml")
        result = self.run_cli(root, "doctor", str(root), extra_env={"OMAMA_CARD": outside_card})
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("OMAMA_CARD source: process environment", result.stdout)
        self.assertIn("VIOLATION[card-resolution]", result.stderr)
        local = root / ".claude" / "settings.local.json"
        doc = json.loads(local.read_text(encoding="utf-8"))
        doc["env"] = {"OMAMA_VALIDATOR": "one", "OMAMA_CHECK_ARTIFACT": "project-checker"}
        local.write_text(json.dumps(doc), encoding="utf-8")
        tracked = root / ".claude" / "settings.json"
        tracked.parent.mkdir(exist_ok=True)
        tracked.write_text(json.dumps({"env": {"OMAMA_VALIDATOR": "two"}}), encoding="utf-8")
        result = self.run_cli(root, "doctor", str(root))
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("VIOLATION[environment-ambiguity]", result.stderr)
        self.assertIn("user/managed/CLI-session settings are not claimed observable", result.stdout)

    def test_presence_and_self_consistent_local_manifest_do_not_replace_actual_dependency_probes(self):
        cases = (
            ("tools/omama/work-order/validate_work_order.py", "validator-probe"),
            ("tools/omama/output-discipline/scripts/check_artifact.py", "checker-probe"),
        )
        for destination, expected in cases:
            with self.subTest(destination=destination):
                root = self.prepare(complete=True)
                self.rebind_installed_manifest(root, destination, b"raise SystemExit(0)\n")
                result = self.run_cli(root, "doctor", str(root))
                self.assertEqual(1, result.returncode, result.stdout + result.stderr)
                self.assertIn("VIOLATION[{0}]".format(expected), result.stderr)
                self.assertIn("WARNING[package-bundle]", result.stdout)
                self.assertIn("traceability, not cryptographic authenticity", result.stdout)
                static = self.run_cli(root, "doctor", str(root), "--static-only")
                self.assertEqual(2, static.returncode, static.stdout + static.stderr)
                self.assertIn("NOT-RUN[{0}]".format(expected), static.stderr)
                self.assertNotIn("DOCTOR-OK", static.stdout)

    def test_token_missing_zero_populated_and_null_states_never_print_values(self):
        root = self.prepare(complete=True)
        token = root / "privacy-tokens.txt"
        token.unlink()
        result = self.run_cli(root, "doctor", str(root))
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("configured token file is missing", result.stderr)
        self.assertIn("comment-only is allowed", result.stderr)
        token.write_bytes(b"synthetic-private-do-not-print\n")
        result = self.run_cli(root, "doctor", str(root))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("populated (1 literal line(s)); values not displayed", result.stdout)
        self.assertNotIn("synthetic-private-do-not-print", result.stdout + result.stderr)
        config = root / "privacy-deny.json"
        doc = json.loads(config.read_text(encoding="utf-8"))
        doc["tokens_file"] = None
        config.write_text(json.dumps(doc), encoding="utf-8")
        result = self.run_cli(root, "doctor", str(root))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("deliberately disabled", result.stdout)

    def test_wrong_hooks_path_and_relocation_are_named(self):
        root = self.prepare(complete=True)
        subprocess.run(["git", "-C", str(root), "config", "--local", "core.hooksPath", ".other-hooks"], check=True)
        result = self.run_cli(root, "doctor", str(root), "--static-only")
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("VIOLATION[privacy-hooks-path]", result.stderr)
        subprocess.run(["git", "-C", str(root), "config", "--local", "core.hooksPath", ".githooks"], check=True)
        state_path = root / ".omama" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["worktree_root"] = "C:/synthetic/old-location"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        result = self.run_cli(root, "doctor", str(root), "--static-only")
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("VIOLATION[relocation]", result.stderr)
        self.assertIn("rerun init", result.stderr)

    def test_standalone_partial_state_is_unhealthy_private_owner_is_allowed_and_foreign_is_not(self):
        root = self.prepare(complete=True)
        owner = "synthetic-owner"
        for name in ("install.lock", "install-journal.json"):
            (root / ".omama" / name).write_text(json.dumps({"schema": 1, "owner": owner}) + "\n", encoding="utf-8")
        result = self.run_cli(root, "doctor", str(root), "--static-only")
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("VIOLATION[partial-install]", result.stderr)
        state = json.loads((root / ".omama" / "state.json").read_text(encoding="utf-8"))
        fixture = Path(__file__).resolve().with_name("doctor_internal_probe.py")
        env = os.environ.copy()
        env["PYTHONPATH"] = self.wheel
        env["TMP"] = install_fixture._test_root()
        env["TEMP"] = install_fixture._test_root()
        internal = subprocess.run(
            [sys.executable, "-B", str(fixture), "--target", str(root), "--owner", owner, "--state", json.dumps(state)],
            cwd=str(root), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", check=False,
        )
        self.assertEqual(0, internal.returncode, internal.stdout + internal.stderr)
        self.assertIn("private admission recognized only expected owner state", internal.stdout)
        foreign = subprocess.run(
            [sys.executable, "-B", str(fixture), "--target", str(root), "--owner", "foreign", "--state", json.dumps(state), "--static-only"],
            cwd=str(root), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", check=False,
        )
        self.assertEqual(1, foreign.returncode, foreign.stdout + foreign.stderr)
        self.assertIn("VIOLATION[partial-install]", foreign.stderr)

    def test_sibling_command_is_statically_inspected_and_never_executed(self):
        root = self.prepare(complete=True)
        marker = root / "sibling-executed.txt"
        local = root / ".claude" / "settings.local.json"
        doc = json.loads(local.read_text(encoding="utf-8"))
        command = '"{0}" -c "open(r\'{1}\',\'w\').write(\'bad\')"'.format(
            Path(self.explicit).as_posix(), marker.as_posix()
        )
        doc["hooks"]["Stop"].append({"hooks": [{"type": "command", "command": command}]})
        local.write_text(json.dumps(doc), encoding="utf-8")
        result = self.run_cli(root, "doctor", str(root))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("statically inspected 1 sibling", result.stdout)
        self.assertIn("WARNING[settings-sibling]", result.stdout)
        self.assertFalse(marker.exists())

    def test_shadow_gate_is_not_executed_while_managed_gate_is_still_probed(self):
        root = self.prepare(complete=True)
        marker = root / "sibling-executed.txt"
        shadow = root / "shadow"
        shadow.mkdir()
        gate = shadow / "receipt_gate.py"
        gate.write_text(
            "from pathlib import Path\n"
            "Path('sibling-executed.txt').write_text('bad')\n"
            "raise SystemExit(2)\n",
            encoding="utf-8",
        )
        project = root / ".claude" / "settings.json"
        project.write_text(json.dumps({
            "hooks": {"Stop": [{"hooks": [{
                "type": "command",
                "command": '"{0}" "$CLAUDE_PROJECT_DIR/shadow/receipt_gate.py"'.format(Path(self.explicit).as_posix()),
            }]}]},
        }), encoding="utf-8")
        result = self.run_cli(root, "doctor", str(root))
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertFalse(marker.exists())
        self.assertIn("VIOLATION[settings-command]", result.stderr)
        self.assertIn("WARNING[settings-gate-sibling]", result.stdout)
        self.assertIn("OK[settings-execution]", result.stdout)

    def test_static_only_launches_no_interpreter_or_installed_artifact_probe(self):
        root = self.prepare(complete=True)
        fixture = Path(__file__).resolve().with_name("static_doctor_probe.py")
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        result = subprocess.run(
            [sys.executable, "-B", str(fixture), "--target", str(root), "--wheel", self.wheel],
            cwd=str(root), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(
            {"exit": 2, "interpreter_probe_calls": 0, "artifact_probe_calls": 0},
            json.loads(result.stdout.strip()),
        )

    def test_ordinary_doctor_without_python_B_preserves_target_and_writes_no_bytecode(self):
        root = self.prepare(complete=True)
        before = _files(root)
        result = self.run_cli_without_bytecode_flag(root, "doctor", str(root))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("DOCTOR-OK", result.stdout)
        self.assertEqual(before, _files(root))
        self.assertEqual([], list((root / "tools" / "omama").rglob("*.pyc")))
        self.assertEqual([], list((root / "tools" / "omama").rglob("__pycache__")))

    def test_fresh_clone_and_healthy_linked_worktree_have_concrete_outcomes(self):
        fresh = self.make_repo()
        result = self.run_cli(fresh, "doctor", str(fresh), "--static-only")
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("state is missing; run `omama init", result.stderr)
        main = self.make_repo()
        subprocess.run(["git", "-C", str(main), "commit", "-m", "base"], check=True)
        linked = Path(tempfile.mkdtemp(prefix="doctor-linked-parent-", dir=install_fixture._test_root())) / "linked"
        subprocess.run(["git", "-C", str(main), "worktree", "add", "--detach", str(linked)], check=True, stdout=subprocess.PIPE)
        subprocess.run(["git", "-C", str(main), "config", "--local", "core.hooksPath", ".githooks"], check=True)
        main_before = _files(main)
        result = self.run_cli(linked, "init", str(linked), "--python", self.explicit)
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        state_path = linked / ".omama" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["status"] = "complete"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        result = self.run_cli(linked, "doctor", str(linked))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("DOCTOR-OK", result.stdout)
        self.assertEqual(main_before, _files(main))

    def test_managed_missing_dependency_is_not_masked_by_cli_or_source(self):
        root = self.prepare(complete=True)
        base = Path(os.environ.get("OMAMA_MANAGED_BASE_PYTHON", "C:/Program Files/Python38/python.exe"))
        if not base.is_file():
            self.skipTest("no existing Python 3.8 base for missing-dependency venv")
        runtime = root / ".omama" / "runtime"
        created = subprocess.run(
            [str(base), "-B", "-m", "venv", "--without-pip", str(runtime)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", check=False,
        )
        self.assertEqual(0, created.returncode, created.stderr)
        interpreter = runtime / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        missing = subprocess.run(
            [str(interpreter), "-B", "-c", "import yaml"],
            env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        self.assertNotEqual(0, missing.returncode)
        state_path = root / ".omama" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state.update({
            "runtime_mode": "managed", "receipt_interpreter": interpreter.resolve().as_posix(),
            "base_interpreter": base.resolve().as_posix(), "pyyaml_version": "6.0.3",
        })
        state_path.write_text(json.dumps(state), encoding="utf-8")
        result = self.run_cli(root, "doctor", str(root))
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("dependency-unavailable", result.stderr)
        self.assertIn("dynamic gate check skipped", result.stderr)

    @unittest.skipUnless(os.environ.get("OMAMA_T7_WHEEL"), "different-package bundle proof requires retained T7 wheel")
    def test_newer_cli_bundle_is_reported_separately_not_as_corruption(self):
        current = self.wheel
        self.wheel = os.environ["OMAMA_T7_WHEEL"]
        root = self.prepare(complete=True)
        state_path = root / ".omama" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["base_interpreter"] = state["receipt_interpreter"]
        state_path.write_text(json.dumps(state), encoding="utf-8")
        self.wheel = current
        result = self.run_cli(root, "doctor", str(root))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("WARNING[package-bundle]", result.stdout)
        self.assertNotIn("VIOLATION[immutable-drift]", result.stderr)


if __name__ == "__main__":
    unittest.main()
