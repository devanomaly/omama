import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import test_install as install_fixture


def _helper():
    return install_fixture.InstallerContractTests("test_inherited_git_routing_refuses_before_target_writes")


def _surface_digest(interpreter):
    code = "import json,yaml;print(json.dumps({'yaml':yaml.__file__}))"
    result = subprocess.run(
        [str(interpreter), "-B", "-c", code],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace", check=True,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
    )
    package = Path(json.loads(result.stdout)["yaml"]).resolve().parent
    files = [Path(interpreter).resolve()] + sorted(path for path in package.rglob("*") if path.is_file())
    digest = hashlib.sha256()
    for path in files:
        info = path.stat()
        digest.update(str(path).encode("utf-8") + b"\0")
        digest.update(str(info.st_size).encode("ascii") + b"\0")
        digest.update(str(info.st_mtime_ns).encode("ascii") + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return len(files), digest.hexdigest()


class RuntimeContractTests(unittest.TestCase):
    def test_explicit_symlink_keeps_lexical_runtime_and_canonical_base_identity(self):
        from omama_cli import runtime

        supplied = Path(install_fixture._test_root()) / "synthetic-explicit-link" / "python"
        canonical = Path(sys.executable)
        probe = {
            "executable": str(canonical),
            "prefix": str(canonical.parent),
            "base_prefix": str(canonical.parent),
            "version": [sys.version_info[0], sys.version_info[1], sys.version_info[2]],
            "pyyaml": "6.0.3",
        }
        path_type = type(supplied)
        with mock.patch.object(path_type, "resolve", return_value=canonical), \
                mock.patch.object(path_type, "is_symlink", return_value=True), \
                mock.patch("omama_cli.runtime._probe", return_value=probe) as execute_probe:
            result = runtime.qualify_explicit(str(supplied))
        # The read-only explicit route is capability-qualified: it records what
        # the installed gate actually needs instead of a universal version floor.
        execute_probe.assert_called_once_with(supplied, require_yaml=True, capability=True)
        self.assertEqual(supplied.absolute().as_posix(), result["receipt_interpreter"])
        self.assertEqual(canonical.as_posix(), result["base_interpreter"])

    def test_explicit_python_is_absolute_qualified_read_only_and_never_installed_into(self):
        from omama_cli.install import InstallError, preflight_bundle, run_asset_transaction
        from omama_cli.runtime import prepare_receipt_runtime, qualify_explicit
        from omama_cli.target import resolve_target

        with self.assertRaises(InstallError) as caught:
            qualify_explicit("python")
        self.assertEqual("explicit-python-not-absolute", caught.exception.reason)
        explicit = os.environ.get("OMAMA_EXPLICIT_PYTHON")
        if not explicit:
            self.skipTest("OMAMA_EXPLICIT_PYTHON must name the host-qualified explicit interpreter")
        before = _surface_digest(explicit)
        with mock.patch("omama_cli.runtime._run_uv", side_effect=AssertionError("explicit route called uv")):
            result = qualify_explicit(explicit)
        after = _surface_digest(explicit)
        self.assertEqual("explicit", result["runtime_mode"])
        self.assertEqual(Path(explicit).absolute().as_posix(), result["receipt_interpreter"])
        self.assertEqual(Path(explicit).resolve().as_posix(), result["base_interpreter"])
        self.assertGreaterEqual(tuple(int(x) for x in result["python_version"].split("."))[:2], (3, 8))
        self.assertEqual(before, after)
        helper = _helper()
        root = helper.make_repo()
        plan = preflight_bundle(resolve_target(str(root), environ={}), helper.bundle())
        with mock.patch("omama_cli.runtime._run_uv", side_effect=AssertionError("explicit route called uv")):
            run_asset_transaction(
                plan,
                prepare=lambda transaction: prepare_receipt_runtime(transaction, explicit_python=explicit),
                status="prepared",
            )
        state = json.loads((root / ".omama" / "state.json").read_text(encoding="utf-8"))
        self.assertEqual("explicit", state["runtime_mode"])
        self.assertFalse((root / ".omama" / "runtime").exists())
        self.assertEqual(before, _surface_digest(explicit))

    def test_explicit_python_without_pyyaml_is_rejected_without_mutation(self):
        from omama_cli.install import InstallError
        from omama_cli.runtime import qualify_explicit

        candidate = Path(tempfile.mkdtemp(prefix="explicit-empty-parent-", dir=install_fixture._test_root())) / "explicit-empty"
        result = subprocess.run([sys.executable, "-B", "-m", "venv", str(candidate)], check=False)
        self.assertEqual(0, result.returncode)
        interpreter = candidate / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        before = {path.relative_to(candidate).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in candidate.rglob("*") if path.is_file()}
        with self.assertRaises(InstallError) as caught:
            qualify_explicit(str(interpreter))
        self.assertEqual("dependency-unavailable", caught.exception.reason)
        after = {path.relative_to(candidate).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in candidate.rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_managed_base_rejects_a_virtual_environment(self):
        from omama_cli.install import InstallError
        from omama_cli.runtime import qualify_managed_base
        from omama_cli.target import resolve_target

        helper = _helper()
        root = helper.make_repo()
        candidate = Path(tempfile.mkdtemp(prefix="candidate-parent-", dir=install_fixture._test_root())) / "candidate"
        result = subprocess.run([sys.executable, "-B", "-m", "venv", str(candidate)], check=False)
        self.assertEqual(0, result.returncode)
        interpreter = candidate / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        with self.assertRaises(InstallError) as caught:
            qualify_managed_base(interpreter, resolve_target(str(root), environ={}))
        self.assertEqual("interpreter-not-durable", caught.exception.reason)

    def test_failed_managed_provision_is_incomplete_and_rolls_back_owned_runtime(self):
        from omama_cli.install import InstallError, preflight_bundle, run_asset_transaction
        from omama_cli.runtime import prepare_receipt_runtime
        from omama_cli.target import resolve_target

        helper = _helper()
        root = helper.make_repo()
        target = resolve_target(str(root), environ={})
        plan = preflight_bundle(target, helper.bundle())

        def prepare(transaction):
            return prepare_receipt_runtime(
                transaction, uv_executable=str(root / "missing-uv.exe"),
                base_python=sys.executable,
            )

        with self.assertRaises(InstallError) as caught:
            run_asset_transaction(plan, prepare=prepare)
        self.assertEqual("uv-unavailable", caught.exception.reason)
        self.assertFalse((root / ".omama" / "runtime").exists())
        self.assertFalse((root / ".omama" / "state.json").exists())
        self.assertFalse((root / ".omama" / "install-journal.json").exists())
        self.assertFalse((root / ".omama" / "install.lock").exists())
        self.assertFalse((root / "tools").exists())

    def test_dependency_install_failure_after_venv_creation_removes_owned_runtime(self):
        from omama_cli import runtime
        from omama_cli.install import InstallError, preflight_bundle, run_asset_transaction
        from omama_cli.target import resolve_target

        helper = _helper()
        root = helper.make_repo()
        target = resolve_target(str(root), environ={})
        original = runtime._run_uv

        def fail_dependency(arguments, target_value, uv_executable):
            if arguments[:2] == ["pip", "install"]:
                raise InstallError("runtime-provision-failed", "injected dependency resolution failure")
            return original(arguments, target_value, uv_executable)

        def prepare(transaction):
            with mock.patch("omama_cli.runtime._run_uv", side_effect=fail_dependency):
                return runtime.prepare_receipt_runtime(transaction, base_python=sys.executable)

        with self.assertRaisesRegex(InstallError, "injected dependency") as caught:
            run_asset_transaction(preflight_bundle(target, helper.bundle()), prepare=prepare)
        self.assertEqual("runtime-provision-failed", caught.exception.reason)
        self.assertFalse((root / ".omama" / "runtime").exists())
        self.assertFalse((root / ".omama" / "state.json").exists())
        self.assertFalse((root / ".omama" / "install-journal.json").exists())
        self.assertFalse((root / ".omama" / "install.lock").exists())

    def test_external_change_inside_published_runtime_is_preserved_on_later_failure(self):
        from omama_cli.install import InstallError, preflight_bundle, run_asset_transaction
        from omama_cli.target import resolve_target

        helper = _helper()
        root = helper.make_repo()
        external = root / ".omama" / "runtime" / "external-edit.txt"

        def prepare(transaction):
            staging = transaction.reserve_owned_tree(".omama/runtime")
            staging.mkdir()
            (staging / "owned.txt").write_bytes(b"owned runtime fixture\n")
            transaction.publish_owned_tree(staging, ".omama/runtime")

        def later_failure(_transaction):
            external.write_bytes(b"external bytes after publication\n")
            raise RuntimeError("injected-later-failure")

        with self.assertRaises(InstallError) as caught:
            run_asset_transaction(
                preflight_bundle(resolve_target(str(root), environ={}), helper.bundle()),
                prepare=prepare, after_publication=later_failure,
            )
        self.assertEqual("recovery-required", caught.exception.reason)
        self.assertTrue(external.is_file())
        self.assertEqual(b"external bytes after publication\n", external.read_bytes())
        self.assertTrue((root / ".omama" / "install-journal.json").is_file())
        self.assertFalse((root / ".omama" / "install.lock").exists())

    @unittest.skipUnless(os.environ.get("OMAMA_RUN_MANAGED_RUNTIME") == "1", "set OMAMA_RUN_MANAGED_RUNTIME=1 for the installation-time uv integration")
    def test_managed_runtime_actual_uv_route_and_runtime_probe(self):
        from omama_cli import runtime
        from omama_cli.install import preflight_bundle, run_asset_transaction
        from omama_cli.target import resolve_target

        helper = _helper()
        root = helper.make_repo()
        target = resolve_target(str(root), environ={})
        base = os.environ.get("OMAMA_MANAGED_BASE_PYTHON")

        calls = []
        original = runtime._run_uv

        def recording(arguments, target_value, uv_executable):
            calls.append(list(arguments))
            return original(arguments, target_value, uv_executable)

        def prepare(transaction):
            with mock.patch("omama_cli.runtime._run_uv", side_effect=recording):
                return runtime.prepare_receipt_runtime(transaction, base_python=base)

        run_asset_transaction(preflight_bundle(target, helper.bundle()), prepare=prepare, status="prepared")
        state = json.loads((root / ".omama" / "state.json").read_text(encoding="utf-8"))
        interpreter = Path(state["receipt_interpreter"])
        self.assertTrue(interpreter.is_file())
        self.assertEqual("managed", state["runtime_mode"])
        self.assertGreaterEqual(tuple(int(x) for x in state["pyyaml_version"].split(".")), (6, 0, 2))
        probe = subprocess.run(
            [str(interpreter), "-B", "-c", "import yaml;print(yaml.__version__)"],
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", check=False,
        )
        self.assertEqual(0, probe.returncode, probe.stderr)
        self.assertEqual(state["pyyaml_version"], probe.stdout.strip())
        absent_cli = subprocess.run(
            [str(interpreter), "-B", "-c", "import importlib.util,sys;sys.exit(1 if importlib.util.find_spec('omama_cli') else 0)"],
            env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        self.assertEqual(0, absent_cli.returncode)
        venv_call = next(call for call in calls if call[:1] == ["venv"])
        pip_call = next(call for call in calls if call[:2] == ["pip", "install"])
        if base is None:
            find_call = next(call for call in calls if call[:2] == ["python", "find"])
            for flag in ("--system", "--no-managed-python", "--no-python-downloads", "--no-config", "--no-project", "--cache-dir"):
                self.assertIn(flag, find_call)
        for call in (venv_call, pip_call):
            self.assertIn("--python", call)
            self.assertIn("--no-python-downloads", call)
            self.assertIn("--no-config", call)
            self.assertIn("--cache-dir", call)
            self.assertIn("--link-mode", call)
            self.assertEqual("copy", call[call.index("--link-mode") + 1])
        self.assertEqual(str(Path(state["base_interpreter"]).resolve()), venv_call[venv_call.index("--python") + 1])
        self.assertIn(runtime.PYYAML_REQUIREMENT, pip_call)
        self.assertIn("--no-sources", pip_call)
        with mock.patch("omama_cli.runtime._run_uv", side_effect=AssertionError("same-bundle runtime called uv")):
            run_asset_transaction(
                preflight_bundle(target, helper.bundle()),
                prepare=lambda transaction: runtime.prepare_receipt_runtime(transaction),
                status="prepared",
            )

    @unittest.skipUnless(os.environ.get("OMAMA_INSTALLED_TOOL_PYTHON"), "set OMAMA_INSTALLED_TOOL_PYTHON for installed-tool deletion proof")
    def test_installed_cli_tool_environment_deletion_leaves_receipt_runtime_working(self):
        helper = _helper()
        root = helper.make_repo()
        tool_python = Path(os.environ["OMAMA_INSTALLED_TOOL_PYTHON"]).absolute()
        tool_root = tool_python.parents[1]
        allocated = Path(install_fixture._test_root()).resolve()
        marker = tool_root / ".omama-test-owner.json"
        self.assertEqual({"test_owned": True}, json.loads(marker.read_text(encoding="utf-8")))
        self.assertEqual(allocated, tool_root.parent)
        fixture = Path(__file__).resolve().with_name("provision_installed_runtime.py")
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        result = subprocess.run(
            [str(tool_python), "-B", str(fixture), "--target", str(root),
             "--base-python", os.environ.get("OMAMA_MANAGED_BASE_PYTHON", sys.executable)],
            cwd=str(allocated), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        state = json.loads((root / ".omama" / "state.json").read_text(encoding="utf-8"))
        receipt_python = Path(state["receipt_interpreter"]).absolute()
        self.assertFalse(receipt_python == tool_python or tool_root in receipt_python.parents)
        shutil.rmtree(str(tool_root))
        self.assertFalse(tool_root.exists())
        gate = root / "tools" / "omama" / "receipt-gate" / "receipt_gate.py"
        gate_probe = subprocess.run(
            [str(receipt_python), "-B", str(gate)], input="",
            cwd=str(root), env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", check=False,
        )
        self.assertEqual(2, gate_probe.returncode, gate_probe.stderr)
        self.assertIn("RECEIPT-GATE BLOCK[BAD-INPUT]", gate_probe.stderr)
        yaml_probe = subprocess.run(
            [str(receipt_python), "-B", "-c", "import yaml;print(yaml.__version__)"],
            env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", check=False,
        )
        self.assertEqual(0, yaml_probe.returncode, yaml_probe.stderr)
        self.assertEqual(state["pyyaml_version"], yaml_probe.stdout.strip())


if __name__ == "__main__":
    unittest.main()


class RuntimeBoundaryTests(unittest.TestCase):
    """Phase-B M1: the runtime and environment boundary.

    Each case reproduces the mechanism the repair addresses, not merely the
    illustrative example that first exposed it.
    """

    def test_repository_shadow_neither_executes_nor_masquerades_as_the_dependency(self):
        from omama_cli import runtime

        root = Path(tempfile.mkdtemp(prefix="cwd-shadow-", dir=install_fixture._test_root()))
        marker = root / "SHADOW-EXECUTED.txt"
        (root / "yaml.py").write_text(
            "import pathlib\n"
            "pathlib.Path(__file__).with_name('SHADOW-EXECUTED.txt').write_text('shadow ran\\n')\n"
            "__version__ = '6.0.2'\n",
            encoding="utf-8",
        )
        previous = os.getcwd()
        os.chdir(str(root))
        try:
            genuine = subprocess.run(
                [sys.executable, "-B", "-c", "import yaml;print(yaml.__file__)"],
                cwd=tempfile.gettempdir(), stdout=subprocess.PIPE, text=True, check=False,
            )
            try:
                value = runtime._probe(sys.executable, require_yaml=True, capability=True)
            except Exception:
                value = None
            self.assertFalse(marker.exists(), "repository-local yaml.py executed during qualification")
            if value is not None and genuine.returncode == 0:
                self.assertEqual(
                    Path(genuine.stdout.strip()).resolve(),
                    Path(value["pyyaml_path"]).resolve(),
                    "qualification recorded a dependency other than the one actually importable",
                )
                self.assertNotEqual("6.0.2", value["pyyaml"]) if genuine.stdout.strip().startswith(str(root)) else None
        finally:
            os.chdir(previous)

    def test_inherited_uv_and_pip_controls_never_reach_uv_and_no_seed_is_not_credited(self):
        from omama_cli import runtime

        root = Path(tempfile.mkdtemp(prefix="uv-scrub-", dir=install_fixture._test_root()))

        class _Target:
            pass

        _Target.root = root
        poisoned = {
            "UV_VENV_SEED": "1", "UV_MANAGED_PYTHON": "1", "UV_INDEX_URL": "https://example.invalid",
            "PIP_INDEX_URL": "https://example.invalid", "PIP_TARGET": str(root),
            "PYTHONPATH": str(root), "VIRTUAL_ENV": str(root),
        }
        with mock.patch.dict(os.environ, poisoned):
            inventory = runtime.scrubbed_environment_inventory()
            env = runtime._uv_env(_Target)
        for name in poisoned:
            self.assertIn(name, inventory["removed"])
            if name not in inventory["imposed"]:
                self.assertNotIn(name, env, "inherited control reached uv: " + name)
        self.assertFalse(inventory["no_seed_credited"])
        # HOME and user-site selection are deliberately preserved: rewriting
        # them would change which dependency the installed gate imports.
        self.assertEqual("HOME" in os.environ, "HOME" in env)

    def test_uv_failure_preserves_the_actionable_line_under_usage_boilerplate(self):
        from omama_cli import runtime

        class _Result:
            stdout = ""
            stderr = (
                "error: the argument '--no-managed-python' cannot be used with '--managed-python'\n"
                "Usage: uv venv --python <PYTHON>\n"
                "For more information, try '--help'.\n"
            )

        diagnostic = runtime._uv_diagnostic(_Result)
        self.assertIn("cannot be used with", diagnostic)
        self.assertNotEqual("For more information, try '--help'.", diagnostic)

    def test_prerelease_versions_are_not_glued_into_a_higher_release(self):
        from omama_cli import runtime

        self.assertEqual(((6, 0, 2), True), runtime._release_tuple("6.0.2rc1"))
        self.assertEqual(((6, 0, 2), True), runtime._release_tuple("6.0.2.dev0"))
        self.assertEqual(((6, 0, 2), False), runtime._release_tuple("6.0.2"))
        for rejected in ("6.0.2rc1", "6.0.2.dev0", "5.4.1", "7.0.0"):
            self.assertFalse(
                runtime._version_at_least(rejected, runtime.PYYAML_MIN)
                and runtime._version_below(rejected, runtime.PYYAML_MAX),
                "managed bound accepted " + rejected,
            )
        for accepted in ("6.0.2", "6.0.3"):
            self.assertTrue(
                runtime._version_at_least(accepted, runtime.PYYAML_MIN)
                and runtime._version_below(accepted, runtime.PYYAML_MAX))

    def test_lexically_equivalent_peer_path_is_not_inside_the_target(self):
        from omama_cli import runtime

        base = Path(tempfile.mkdtemp(prefix="lexical-", dir=install_fixture._test_root()))
        repository = base / "repo"
        peer = base / "peer"
        repository.mkdir()
        peer.mkdir()
        self.assertFalse(runtime._is_lexically_within(repository / ".." / "peer" / "python", repository))
        self.assertTrue(runtime._is_lexically_within(repository / "inside" / "python", repository))

    def test_absent_owned_runtime_reprovisions_while_unowned_or_drifted_is_refused(self):
        from omama_cli.install import InstallError
        from omama_cli import runtime

        base = Path(tempfile.mkdtemp(prefix="owned-runtime-", dir=install_fixture._test_root()))

        class _Plan:
            pass

        class _Target:
            pass

        _Target.root = base
        _Plan.target = _Target
        interpreter = runtime._runtime_python(base / ".omama" / "runtime").absolute()
        _Plan.existing_state = {
            "runtime_mode": "managed",
            "receipt_interpreter": interpreter.as_posix(),
            "base_interpreter": sys.executable,
        }
        # Absent: doctor's "rerun init in this clone/worktree" remedy must work.
        self.assertIsNone(runtime._reusable_managed(_Plan))
        # Present but not owned by omama: named and preserved, never deleted.
        runtime_tree = base / ".omama" / "runtime"
        runtime_tree.mkdir(parents=True)
        (runtime_tree / "foreign.txt").write_text("adopter content\n", encoding="utf-8")
        with self.assertRaises(InstallError) as caught:
            runtime._reusable_managed(_Plan)
        self.assertEqual("incompatible-runtime", caught.exception.reason)
        self.assertTrue((runtime_tree / "foreign.txt").is_file(), "refusal deleted an unowned runtime tree")
        # Present, marked, but drifted marker: still refused without deletion.
        (runtime_tree / runtime.RUNTIME_OWNER_MARKER).write_text("not json\n", encoding="utf-8")
        with self.assertRaises(InstallError) as caught:
            runtime._reusable_managed(_Plan)
        self.assertEqual("incompatible-runtime", caught.exception.reason)
        self.assertTrue((runtime_tree / "foreign.txt").is_file())

    def test_owned_runtime_inventory_refuses_unapproved_distributions(self):
        from omama_cli.install import InstallError
        from omama_cli import runtime

        with mock.patch.object(runtime, "runtime_distributions", return_value=["pyyaml", "pip", "setuptools"]):
            with self.assertRaises(InstallError) as caught:
                runtime._require_owned_inventory("ignored")
        self.assertEqual("runtime-inventory-unapproved", caught.exception.reason)
        self.assertIn("pip", caught.exception.message)
        with mock.patch.object(runtime, "runtime_distributions", return_value=["pyyaml"]):
            self.assertEqual(["pyyaml"], runtime._require_owned_inventory("ignored"))
        with mock.patch.object(runtime, "runtime_distributions", return_value=[]):
            with self.assertRaises(InstallError) as caught:
                runtime._require_owned_inventory("ignored")
        self.assertEqual("runtime-inventory-incomplete", caught.exception.reason)

    def test_empty_explicit_python_is_a_named_invalid_value_not_the_managed_route(self):
        from omama_cli.command import _parser
        from omama_cli.install import InstallError
        from omama_cli.runtime import qualify_explicit

        arguments = _parser().parse_args(["init", ".", "--python", ""])
        self.assertIsNotNone(arguments.python, "empty --python must remain distinguishable from an omitted flag")
        with self.assertRaises(InstallError) as caught:
            qualify_explicit(arguments.python)
        self.assertEqual("explicit-python-not-absolute", caught.exception.reason)
