import hashlib
import os
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import test_install as install_fixture


class WiringContractTests(unittest.TestCase):
    def make_repo(self):
        return install_fixture.InstallerContractTests(
            "test_inherited_git_routing_refuses_before_target_writes"
        ).make_repo()

    def test_malformed_project_settings_refuses_before_publication(self):
        wheel = os.environ.get("OMAMA_BUILT_WHEEL")
        explicit = os.environ.get("OMAMA_EXPLICIT_PYTHON")
        if not wheel or not explicit:
            self.skipTest("built CLI proof requires OMAMA_BUILT_WHEEL and OMAMA_EXPLICIT_PYTHON")
        root = self.make_repo()
        settings = root / ".claude" / "settings.json"
        settings.parent.mkdir()
        settings.write_bytes(b"{ malformed\n")
        before = install_fixture._tree_bytes(root)
        env = os.environ.copy()
        env["PYTHONPATH"] = wheel
        result = subprocess.run(
            [sys.executable, "-B", "-m", "omama_cli", "init", str(root),
             "--python", explicit],
            cwd=str(root), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", check=False,
        )
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertIn("settings-not-json", result.stderr)
        self.assertEqual(before, install_fixture._tree_bytes(root))
        self.assertFalse((root / ".omama").exists())

    @unittest.skipUnless(os.environ.get("OMAMA_BUILT_WHEEL") and os.environ.get("OMAMA_EXPLICIT_PYTHON"), "installed public CLI proof requires wheel and host interpreter")
    def test_public_installed_init_completes_and_no_git_config_is_exact(self):
        wheel = os.environ["OMAMA_BUILT_WHEEL"]
        explicit = os.environ["OMAMA_EXPLICIT_PYTHON"]
        for no_config in (False, True):
            with self.subTest(no_git_config=no_config):
                root = self.make_repo()
                before_card = (root / "CARD.yaml").read_bytes()
                before_index = (root / ".git" / "index").read_bytes()
                env = os.environ.copy()
                env["PYTHONPATH"] = wheel
                command = [sys.executable, "-B", "-m", "omama_cli", "init", str(root), "--python", explicit]
                if no_config:
                    command.append("--no-git-config")
                result = subprocess.run(
                    command, cwd=str(root), env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    encoding="utf-8", errors="replace", check=False,
                )
                self.assertEqual(2 if no_config else 0, result.returncode, result.stdout + result.stderr)
                self.assertEqual(before_card, (root / "CARD.yaml").read_bytes())
                self.assertEqual(before_index, (root / ".git" / "index").read_bytes())
                self.assertFalse((root / ".omama" / "install.lock").exists())
                self.assertFalse((root / ".omama" / "install-journal.json").exists())
                state = json.loads((root / ".omama" / "state.json").read_text(encoding="utf-8"))
                if no_config:
                    self.assertIn("PREPARED", result.stdout)
                    self.assertIn("mandatory admission was not attempted", result.stderr)
                    exact = 'git -C "{0}" config --local core.hooksPath .githooks'.format(root.as_posix())
                    self.assertIn(exact, result.stdout)
                    self.assertEqual("manual-required", state["activation_status"])
                    absent = subprocess.run(
                        ["git", "-C", str(root), "config", "--local", "--get", "core.hooksPath"],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
                    )
                    self.assertEqual(1, absent.returncode)
                else:
                    self.assertIn("ADMISSION-OK", result.stdout)
                    self.assertIn("INSTALLED", result.stdout)
                    self.assertEqual("active", state["activation_status"])
                    self.assertEqual("complete", state["status"])
                    checker = root / "tools" / "omama" / "receipt-gate" / "adapt" / "check_wiring.py"
                    checked = subprocess.run(
                        [explicit, "-B", str(checker), str(root)], cwd=str(root),
                        env={key: value for key, value in env.items() if key != "PYTHONPATH"},
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                        encoding="utf-8", errors="replace", check=False,
                    )
                    self.assertEqual(0, checked.returncode, checked.stdout + checked.stderr)
                    self.assertIn("WIRING-OK", checked.stdout)

    def plan(self, root, no_git_config=False):
        from omama_cli.install import preflight_bundle
        from omama_cli.target import resolve_target
        from omama_cli.wiring import attach_wiring, preflight_wiring

        helper = install_fixture.InstallerContractTests(
            "test_inherited_git_routing_refuses_before_target_writes"
        )
        plan = preflight_bundle(resolve_target(str(root), environ={}), helper.bundle())
        wiring = preflight_wiring(plan, Path(sys.executable).resolve(), no_git_config)
        attach_wiring(plan, wiring)
        return plan, wiring

    def install(self, root, no_git_config=False, before_finish=None):
        from omama_cli.install import run_asset_transaction
        from omama_cli.wiring import finish_wiring

        plan, wiring = self.plan(root, no_git_config)
        run_asset_transaction(
            plan, status="prepared",
            after_publication=lambda transaction: finish_wiring(transaction, wiring),
            before_finish=before_finish, state_extra=wiring.state_extra,
        )
        return wiring

    def test_settings_ignore_tokens_chainers_and_activation_preserve_unrelated_state(self):
        root = self.make_repo()
        tracked = root / ".claude" / "settings.json"
        tracked.parent.mkdir()
        tracked_doc = {
            "env": {"UNRELATED": "preserve"},
            "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo sibling"}]}]},
            "permissions": {"allow": ["Read"]},
        }
        tracked.write_text(json.dumps(tracked_doc), encoding="utf-8")
        local = root / ".claude" / "settings.local.json"
        local_doc = {"permissions": {"deny": ["WebFetch"]}, "custom": [1, 2]}
        local.write_text(json.dumps(local_doc), encoding="utf-8")
        before_tracked = tracked.read_bytes()
        before_config = subprocess.run(
            ["git", "-C", str(root), "config", "--local", "--list"],
            stdout=subprocess.PIPE, text=True, encoding="utf-8", check=True,
        ).stdout.splitlines()
        wiring = self.install(root)
        self.assertEqual(before_tracked, tracked.read_bytes())
        merged = json.loads(local.read_text(encoding="utf-8"))
        self.assertEqual(local_doc["permissions"], merged["permissions"])
        self.assertEqual(local_doc["custom"], merged["custom"])
        serialized = json.dumps(merged)
        self.assertEqual(1, serialized.count("receipt_gate.py"))
        commands = [
            handler.get("command")
            for matcher in merged["hooks"]["Stop"]
            for handler in matcher["hooks"]
            if isinstance(handler, dict)
        ]
        self.assertIn(wiring.command, commands)
        self.assertNotIn("OMAMA_", serialized)
        self.assertNotIn("\\", wiring.command)
        ignore_lines = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
        for line in (".claude/settings.local.json", ".omama/", "privacy-tokens.txt", "CARD.review.md", "*.receipt.json"):
            self.assertEqual(1, ignore_lines.count(line))
        self.assertEqual(b"# Add one private literal per line; keep this file gitignored.\n", (root / "privacy-tokens.txt").read_bytes())
        for relative in (".githooks/pre-commit", ".githooks/pre-merge-commit", ".githooks/privacy-pre-commit"):
            data = (root / relative).read_bytes()
            self.assertNotIn(b"\r\n", data)
            self.assertTrue(data.endswith(b"\n"))
        self.assertEqual(".githooks", subprocess.run(
            ["git", "-C", str(root), "config", "--local", "--get", "core.hooksPath"],
            stdout=subprocess.PIPE, text=True, encoding="utf-8", check=True,
        ).stdout.strip())
        after_config = subprocess.run(
            ["git", "-C", str(root), "config", "--local", "--list"],
            stdout=subprocess.PIPE, text=True, encoding="utf-8", check=True,
        ).stdout.splitlines()
        self.assertEqual(sorted(before_config + ["core.hookspath=.githooks"]), sorted(after_config))
        state = json.loads((root / ".omama" / "state.json").read_text(encoding="utf-8"))
        self.assertEqual("active", state["activation_status"])
        self.assertEqual([], state["managed_omama_overrides"])
        self.assertFalse((root / ".omama" / "install-journal.json").exists())
        self.assertFalse((root / ".omama" / "install.lock").exists())

    def test_same_bundle_rerun_preserves_populated_tokens_team_config_and_no_duplicates(self):
        root = self.make_repo()
        self.install(root)
        config = b'{"tokens_file":"privacy-tokens.txt","deny_regexes":[{"id":"team","pattern":"team-pattern"}]}\n'
        tokens = b"synthetic-team-literal\n"
        (root / "privacy-deny.json").write_bytes(config)
        (root / "privacy-tokens.txt").write_bytes(tokens)
        local = json.loads((root / ".claude" / "settings.local.json").read_text(encoding="utf-8"))
        local["unrelated"] = {"kept": True}
        (root / ".claude" / "settings.local.json").write_text(json.dumps(local), encoding="utf-8")
        self.install(root)
        self.assertEqual(config, (root / "privacy-deny.json").read_bytes())
        self.assertEqual(tokens, (root / "privacy-tokens.txt").read_bytes())
        merged = json.loads((root / ".claude" / "settings.local.json").read_text(encoding="utf-8"))
        self.assertEqual({"kept": True}, merged["unrelated"])
        self.assertEqual(1, json.dumps(merged).count("receipt_gate.py"))
        lines = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
        for line in (".claude/settings.local.json", ".omama/", "privacy-tokens.txt"):
            self.assertEqual(1, lines.count(line))

    def test_settings_gate_conflict_disabled_async_duplicate_and_tracked_local_refuse(self):
        from omama_cli.install import InstallError

        scenarios = {
            "tracked-gate": ("settings.json", {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": '"{0}" "$CLAUDE_PROJECT_DIR/tools/omama/receipt-gate/receipt_gate.py"'.format(Path(sys.executable).resolve().as_posix())}]}]}}),
            "disabled": ("settings.local.json", {"disableAllHooks": True}),
            "async": ("settings.local.json", {"hooks": {"Stop": [{"hooks": [{"type": "command", "async": True, "command": 'python receipt_gate.py'}]}]}}),
            "different": ("settings.local.json", {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": '"C:/different/python.exe" "$CLAUDE_PROJECT_DIR/tools/omama/receipt-gate/receipt_gate.py"'}]}]}}),
        }
        for name, (filename, doc) in scenarios.items():
            with self.subTest(name=name):
                root = self.make_repo()
                path = root / ".claude" / filename
                path.parent.mkdir()
                path.write_text(json.dumps(doc), encoding="utf-8")
                before = install_fixture._tree_bytes(root)
                with self.assertRaises(InstallError):
                    self.plan(root)
                self.assertEqual(before, install_fixture._tree_bytes(root))
                self.assertFalse((root / ".omama").exists())
        root = self.make_repo()
        local = root / ".claude" / "settings.local.json"
        local.parent.mkdir()
        command = '"{0}" "$CLAUDE_PROJECT_DIR/tools/omama/receipt-gate/receipt_gate.py"'.format(Path(sys.executable).resolve().as_posix())
        handler = {"type": "command", "command": command}
        local.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [handler]}, {"hooks": [handler]}]}}), encoding="utf-8")
        with self.assertRaisesRegex(InstallError, "more than one"):
            self.plan(root)
        subprocess.run(["git", "-C", str(root), "add", "-f", ".claude/settings.local.json"], check=True)
        with self.assertRaises(InstallError) as caught:
            self.plan(root)
        self.assertEqual("tracked-local-state", caught.exception.reason)

    def test_malformed_local_settings_and_disabled_tokens_are_handled(self):
        from omama_cli.install import InstallError

        root = self.make_repo()
        local = root / ".claude" / "settings.local.json"
        local.parent.mkdir()
        local.write_bytes(b"[ malformed\n")
        with self.assertRaises(InstallError) as caught:
            self.plan(root)
        self.assertEqual("settings-not-json", caught.exception.reason)
        root = self.make_repo()
        (root / "privacy-deny.json").write_text('{"tokens_file":null}\n', encoding="utf-8")
        self.install(root)
        self.assertFalse((root / "privacy-tokens.txt").exists())
        state = json.loads((root / ".omama" / "state.json").read_text(encoding="utf-8"))
        self.assertIsNone(state["tokens_file"])
        self.assertEqual("disabled", state["token_state_at_init"])

    def test_custom_or_displaced_hooks_refuse_but_already_matching_is_accepted(self):
        from omama_cli.install import InstallError

        root = self.make_repo()
        subprocess.run(["git", "-C", str(root), "config", "--local", "core.hooksPath", "custom-hooks"], check=True)
        with self.assertRaises(InstallError) as caught:
            self.plan(root)
        self.assertEqual("hooks-path-conflict", caught.exception.reason)
        for name in ("pre-push", "post-checkout"):
            with self.subTest(displaced=name):
                root = self.make_repo()
                active = root / ".git" / "hooks" / name
                active.write_bytes(b"#!/bin/sh\nexit 0\n")
                active.chmod(0o755)
                before = active.read_bytes()
                with self.assertRaises(InstallError) as caught:
                    self.plan(root)
                self.assertEqual("hooks-displacement", caught.exception.reason)
                self.assertEqual(before, active.read_bytes())
        root = self.make_repo()
        subprocess.run(["git", "-C", str(root), "config", "--local", "core.hooksPath", ".githooks"], check=True)
        config_before = (root / ".git" / "config").read_bytes()
        self.install(root)
        self.assertEqual(config_before, (root / ".git" / "config").read_bytes())

    def test_effective_included_hooks_path_and_active_hook_refuse_without_config_change(self):
        from omama_cli.install import InstallError

        root = self.make_repo()
        extra = root / ".git" / "extra-config"
        extra.write_text("[core]\n    hooksPath = .custom-hooks\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "config", "--local", "include.path", "extra-config"], check=True)
        hooks = root / ".custom-hooks"
        hooks.mkdir()
        active = hooks / "pre-push"
        active.write_bytes(b"#!/bin/sh\nexit 1\n")
        active.chmod(0o755)
        config_before = (root / ".git" / "config").read_bytes()
        extra_before = extra.read_bytes()
        with self.assertRaises(InstallError) as caught:
            self.plan(root)
        self.assertEqual("hooks-path-conflict", caught.exception.reason)
        self.assertIn("pre-push", caught.exception.message)
        self.assertEqual(config_before, (root / ".git" / "config").read_bytes())
        self.assertEqual(extra_before, extra.read_bytes())
        effective = subprocess.run(
            ["git", "-C", str(root), "config", "--includes", "--get", "core.hooksPath"],
            stdout=subprocess.PIPE, text=True, encoding="utf-8", check=True,
        ).stdout.strip()
        self.assertEqual(".custom-hooks", effective)
        self.assertFalse((root / ".omama").exists())

    def test_no_git_config_prepares_with_exact_remedy_and_no_activation(self):
        root = self.make_repo()
        wiring = self.install(root, no_git_config=True)
        result = subprocess.run(
            ["git", "-C", str(root), "config", "--local", "--get", "core.hooksPath"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        self.assertEqual(1, result.returncode)
        self.assertEqual('git -C "{0}" config --local core.hooksPath .githooks'.format(root.as_posix()), wiring.activation_remedy)
        state = json.loads((root / ".omama" / "state.json").read_text(encoding="utf-8"))
        self.assertEqual("manual-required", state["activation_status"])
        self.assertTrue((root / ".githooks" / "pre-commit").is_file())

    def test_tracked_or_escaping_tokens_and_nested_ignore_negation_refuse(self):
        from omama_cli.install import InstallError

        root = self.make_repo()
        (root / "privacy-deny.json").write_text('{"tokens_file":"../outside"}\n', encoding="utf-8")
        with self.assertRaises(InstallError) as caught:
            self.plan(root)
        self.assertEqual("unsafe-tokens-path", caught.exception.reason)
        root = self.make_repo()
        (root / "privacy-tokens.txt").write_text("synthetic\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "-f", "privacy-tokens.txt"], check=True)
        with self.assertRaises(InstallError) as caught:
            self.plan(root)
        self.assertEqual("tracked-local-state", caught.exception.reason)
        root = self.make_repo()
        nested = root / ".claude" / ".gitignore"
        nested.parent.mkdir()
        nested.write_text("!settings.local.json\n", encoding="utf-8")
        with self.assertRaises(InstallError) as caught:
            self.plan(root)
        self.assertEqual("ignore-negation-conflict", caught.exception.reason)

    def test_intervening_git_config_edit_is_preserved_as_incomplete_recovery(self):
        from omama_cli.install import InstallError
        from omama_cli.wiring import finish_wiring

        root = self.make_repo()
        plan, wiring = self.plan(root)

        def activate_then_external(transaction):
            finish_wiring(transaction, wiring)
            subprocess.run(["git", "-C", str(root), "config", "--local", "fixture.external", "preserve"], check=True)
            raise RuntimeError("injected-after-activation")

        from omama_cli.install import run_asset_transaction
        with self.assertRaises(InstallError) as caught:
            run_asset_transaction(
                plan, after_publication=activate_then_external,
                state_extra=wiring.state_extra,
            )
        self.assertEqual("recovery-required", caught.exception.reason)
        self.assertEqual("preserve", subprocess.run(
            ["git", "-C", str(root), "config", "--local", "--get", "fixture.external"],
            stdout=subprocess.PIPE, text=True, encoding="utf-8", check=True,
        ).stdout.strip())
        self.assertEqual(".githooks", subprocess.run(
            ["git", "-C", str(root), "config", "--local", "--get", "core.hooksPath"],
            stdout=subprocess.PIPE, text=True, encoding="utf-8", check=True,
        ).stdout.strip())
        self.assertTrue((root / ".omama" / "install-journal.json").is_file())

    def test_linked_worktree_requires_main_checkout_activation_then_accepts_matching_config(self):
        from omama_cli.install import InstallError

        main = self.make_repo()
        subprocess.run(["git", "-C", str(main), "commit", "-m", "fixture base"], check=True)
        linked = Path(tempfile.mkdtemp(prefix="linked-parent-", dir=install_fixture._test_root())) / "linked"
        subprocess.run(["git", "-C", str(main), "worktree", "add", "--detach", str(linked)], check=True, stdout=subprocess.PIPE)
        main_local = main / ".claude" / "settings.local.json"
        main_local.parent.mkdir()
        main_local.write_bytes(b'{"sibling":"preserve"}\n')
        main_card = (main / "CARD.yaml").read_bytes()
        main_index = (main / ".git" / "index").read_bytes()
        main_settings = main_local.read_bytes()
        main_config = (main / ".git" / "config").read_bytes()
        with self.assertRaises(InstallError) as caught:
            self.plan(linked)
        self.assertEqual("linked-worktree-config", caught.exception.reason)
        self.assertIn(main.as_posix(), caught.exception.message)
        self.assertEqual(main_config, (main / ".git" / "config").read_bytes())
        subprocess.run(["git", "-C", str(main), "config", "--local", "core.hooksPath", ".githooks"], check=True)
        configured = (main / ".git" / "config").read_bytes()
        self.install(linked)
        self.assertEqual(configured, (main / ".git" / "config").read_bytes())
        self.assertEqual(main_card, (main / "CARD.yaml").read_bytes())
        self.assertEqual(main_index, (main / ".git" / "index").read_bytes())
        self.assertEqual(main_settings, main_local.read_bytes())

    @unittest.skipUnless(
        os.environ.get("OMAMA_INSTALLED_TOOL_PYTHON") and os.environ.get("OMAMA_EXPLICIT_PYTHON"),
        "installed public separate-Git proof requires the installed tool and explicit interpreter",
    )
    def test_public_separate_git_dir_refuses_before_external_config_or_target_writes(self):
        tool_python = Path(os.environ["OMAMA_INSTALLED_TOOL_PYTHON"])
        cli = tool_python.parent / ("omama.exe" if os.name == "nt" else "omama")
        explicit = os.environ["OMAMA_EXPLICIT_PYTHON"]
        clean = os.environ.copy()
        for key in list(clean):
            if key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "PYTHONPATH", "VIRTUAL_ENV") \
                    or key.startswith("GIT_CONFIG_") or key.startswith("OMAMA_"):
                clean.pop(key, None)
        clean["PYTHONDONTWRITEBYTECODE"] = "1"

        def snapshot_worktree(root):
            marker = root / ".git"
            values = {}
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                relative = path.relative_to(root)
                if marker.is_dir() and relative.parts[0] == ".git":
                    continue
                values[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
            return values

        rows = []
        for separate in (False, True):
            with self.subTest(separate=separate):
                root = Path(tempfile.mkdtemp(
                    prefix="separate-git-worktree-" if separate else "internal-git-worktree-",
                    dir=install_fixture._test_root(),
                ))
                database = Path(tempfile.mkdtemp(prefix="separate-git-database-", dir=install_fixture._test_root())) if separate else root / ".git"
                if separate:
                    database.rmdir()
                    initialized = subprocess.run(
                        ["git", "init", "-q", "--separate-git-dir", str(database), str(root)],
                        env=clean, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
                    )
                else:
                    initialized = subprocess.run(
                        ["git", "init", "-q", str(root)], env=clean,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
                    )
                self.assertEqual(0, initialized.returncode, initialized.stderr)
                subprocess.run(["git", "-C", str(root), "config", "user.email", "fixture@example.invalid"], env=clean, check=True)
                subprocess.run(["git", "-C", str(root), "config", "user.name", "Fixture"], env=clean, check=True)
                (root / "tracked.txt").write_bytes(b"protected tracked bytes\n")
                subprocess.run(["git", "-C", str(root), "add", "tracked.txt"], env=clean, check=True)
                subprocess.run(
                    ["git", "-C", str(root), "-c", "core.hooksPath=.no-hooks", "commit", "-qm", "base"],
                    env=clean, check=True,
                )
                (root / "CARD.yaml").write_bytes(b"synthetic protected card\n")
                (root / "CARD.review.md").write_bytes(b"synthetic protected review evidence\n")
                (root / "fixture.receipt.json").write_bytes(b'{"synthetic":"preserve"}\n')
                (root / "privacy-deny.json").write_text(
                    json.dumps({"deny_regexes": [{"id": "broken", "pattern": "("}], "tokens_file": None}),
                    encoding="utf-8",
                )
                worktree_before = snapshot_worktree(root)
                config_before = (database / "config").read_bytes()
                index_before = (database / "index").read_bytes()
                result = subprocess.run(
                    [str(cli), "init", str(root), "--python", explicit], cwd=str(root), env=clean,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    encoding="utf-8", errors="replace", check=False,
                )
                rows.append((separate, result.returncode, result.stdout + result.stderr))
                self.assertEqual(1, result.returncode, result.stdout + result.stderr)
                self.assertEqual(worktree_before, snapshot_worktree(root))
                self.assertEqual(config_before, (database / "config").read_bytes())
                self.assertEqual(index_before, (database / "index").read_bytes())
                if separate:
                    self.assertIn("unsupported-git-config", result.stderr)
                    self.assertFalse((root / ".omama").exists())
                else:
                    self.assertIn("privacy-config", result.stderr)
                    self.assertNotIn("path-escape", result.stderr)
                    self.assertFalse((root / ".omama").exists())
        self.assertEqual([False, True], [row[0] for row in rows])


if __name__ == "__main__":
    unittest.main()
