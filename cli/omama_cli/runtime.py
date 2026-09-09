"""Durable receipt interpreter qualification and target-owned provisioning."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .install import InstallError
from .target import validate_command_path


PYTHON_FLOOR = (3, 8)
PYTHON_CEILING = (4, 0)
PYYAML_MIN = (6, 0, 2)
PYYAML_MAX = (7, 0, 0)
PYYAML_REQUIREMENT = "PyYAML>=6.0.2,<7"


def _version_tuple(value):
    pieces = []
    for part in str(value).split("."):
        digits = "".join(char for char in part if char.isdigit())
        if not digits:
            break
        pieces.append(int(digits))
    return tuple(pieces)


def _clean_probe_env():
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env.pop("VIRTUAL_ENV", None)
    return env


def _probe(interpreter, require_yaml):
    code = (
        "import json,sys; "
        "d={'executable':sys.executable,'prefix':sys.prefix,'base_prefix':getattr(sys,'base_prefix',sys.prefix),"
        "'version':[sys.version_info[0],sys.version_info[1],sys.version_info[2]]}; "
        + ("import yaml; d['pyyaml']=yaml.__version__; " if require_yaml else "")
        + "print(json.dumps(d,sort_keys=True))"
    )
    try:
        result = subprocess.run(
            [str(interpreter), "-B", "-c", code], env=_clean_probe_env(),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", timeout=60, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise InstallError("interpreter-unrunnable", "interpreter probe could not run: {0}".format(type(exc).__name__))
    if result.returncode != 0:
        label = "PyYAML import" if require_yaml else "version"
        raise InstallError("dependency-unavailable" if require_yaml else "interpreter-unrunnable", "{0} probe failed with exit {1}".format(label, result.returncode))
    try:
        value = json.loads(result.stdout.strip())
    except (ValueError, TypeError):
        raise InstallError("interpreter-unrunnable", "interpreter probe returned malformed output")
    version = tuple(value.get("version") or ())
    if version < PYTHON_FLOOR or version >= PYTHON_CEILING:
        raise InstallError("unsupported-python", "Python {0} is outside the supported >=3.8,<4 range".format(".".join(str(x) for x in version)))
    if require_yaml:
        yaml_version = _version_tuple(value.get("pyyaml"))
        if yaml_version < PYYAML_MIN or yaml_version >= PYYAML_MAX:
            raise InstallError("dependency-version", "PyYAML {0} is outside >=6.0.2,<7".format(value.get("pyyaml")))
    return value


def _is_within(path, parent):
    try:
        Path(path).resolve().relative_to(Path(parent).resolve())
        return True
    except ValueError:
        return False


def qualify_explicit(path, target=None):
    supplied = Path(path)
    if not supplied.is_absolute():
        raise InstallError("explicit-python-not-absolute", "--python requires an absolute interpreter path")
    validate_command_path(supplied)
    resolved = supplied.resolve()
    if not resolved.is_file() or supplied.is_symlink():
        raise InstallError("interpreter-unrunnable", "explicit interpreter is not an existing regular file")
    if target is not None and _is_within(resolved, target.root):
        raise InstallError("interpreter-not-durable", "explicit interpreter is inside the target repository")
    value = _probe(resolved, require_yaml=True)
    return {
        "runtime_mode": "explicit",
        "receipt_interpreter": Path(value["executable"]).resolve().as_posix(),
        "base_interpreter": Path(value["executable"]).resolve().as_posix(),
        "python_base_prefix": Path(value["base_prefix"]).resolve().as_posix(),
        "python_version": ".".join(str(x) for x in value["version"]),
        "pyyaml_version": str(value["pyyaml"]),
    }


def _run_uv(arguments, target, uv_executable):
    cache = target.root / ".omama" / "cache"
    temporary = cache / "tmp"
    cache.mkdir(parents=True, exist_ok=True)
    temporary.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({
        "UV_CACHE_DIR": str(cache), "UV_NO_CONFIG": "1",
        "UV_PYTHON_DOWNLOADS": "never", "UV_LINK_MODE": "copy",
        "TMP": str(temporary), "TEMP": str(temporary), "TMPDIR": str(temporary),
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    env.pop("VIRTUAL_ENV", None)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    try:
        result = subprocess.run(
            [str(uv_executable)] + list(arguments), cwd=str(target.root), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", timeout=300, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise InstallError("uv-unavailable", "uv command could not run: {0}".format(type(exc).__name__))
    if result.returncode != 0:
        tail = ((result.stderr or "") + (result.stdout or "")).strip().splitlines()
        raise InstallError("runtime-provision-failed", "uv {0} exited {1}: {2}".format(arguments[0], result.returncode, tail[-1][:300] if tail else "no diagnostic"))
    return result.stdout.strip()


def discover_base(target, uv_executable=None):
    uv_executable = uv_executable or shutil.which("uv")
    if not uv_executable:
        raise InstallError("uv-unavailable", "uv is required at install time; install uv or supply --python ABSOLUTE_PATH")
    cache = target.root / ".omama" / "cache"
    output = _run_uv([
        "python", "find", ">=3.8", "--system", "--no-managed-python",
        "--no-python-downloads", "--no-config", "--no-project",
        "--cache-dir", str(cache),
    ], target, uv_executable)
    candidate = output.splitlines()[-1].strip() if output else ""
    if not candidate:
        raise InstallError("base-python-unavailable", "uv found no existing supported system Python")
    return Path(candidate).resolve()


def qualify_managed_base(path, target):
    candidate = Path(path).resolve()
    if not candidate.is_file():
        raise InstallError("base-python-unavailable", "managed base interpreter is missing")
    if _is_within(candidate, target.root):
        raise InstallError("interpreter-not-durable", "managed base interpreter is inside the target repository")
    tool_prefix = Path(sys.prefix).resolve()
    base_prefix = Path(getattr(sys, "base_prefix", sys.prefix)).resolve()
    if tool_prefix != base_prefix and _is_within(candidate, tool_prefix):
        raise InstallError("interpreter-not-durable", "managed base resolves inside the disposable CLI/tool environment")
    value = _probe(candidate, require_yaml=False)
    if Path(value["prefix"]).resolve() != Path(value["base_prefix"]).resolve():
        raise InstallError("interpreter-not-durable", "managed base is itself a virtual environment, not an independent system Python")
    return candidate, value


def _runtime_python(runtime):
    # This function also plans the settings command before the runtime exists;
    # select by platform rather than by premature file existence.
    return runtime / "Scripts" / "python.exe" if os.name == "nt" else runtime / "bin" / "python"


def managed_runtime_interpreter(target):
    return _runtime_python(target.root / ".omama" / "runtime").absolute()


def _reusable_managed(plan):
    state = plan.existing_state
    if not state or state.get("runtime_mode") != "managed":
        return None
    interpreter = Path(str(state.get("receipt_interpreter", "")))
    expected = plan.target.root / ".omama" / "runtime"
    if not _is_within(interpreter, expected):
        raise InstallError("incompatible-runtime", "recorded managed interpreter is outside .omama/runtime")
    value = _probe(interpreter, require_yaml=True)
    return {
        "runtime_mode": "managed",
        "receipt_interpreter": Path(value["executable"]).resolve().as_posix(),
        "base_interpreter": str(state.get("base_interpreter")),
        "python_base_prefix": str(state.get("python_base_prefix", value["base_prefix"])),
        "python_version": ".".join(str(x) for x in value["version"]),
        "pyyaml_version": str(value["pyyaml"]),
    }


def prepare_receipt_runtime(transaction, explicit_python=None, uv_executable=None, base_python=None):
    plan = transaction.plan
    target = plan.target
    if explicit_python:
        return qualify_explicit(explicit_python, target)
    reusable = _reusable_managed(plan)
    if reusable:
        return reusable
    runtime = target.root / ".omama" / "runtime"
    if runtime.exists():
        raise InstallError("incompatible-runtime", "existing .omama/runtime has no matching managed installation state")
    uv_executable = uv_executable or shutil.which("uv")
    if not uv_executable:
        raise InstallError("uv-unavailable", "uv is required at install time; install uv or supply --python ABSOLUTE_PATH")
    candidate = Path(base_python).resolve() if base_python else discover_base(target, uv_executable)
    candidate, base_value = qualify_managed_base(candidate, target)
    staging = transaction.reserve_owned_tree(".omama/runtime")
    try:
        _run_uv([
            "venv", str(staging), "--python", str(candidate), "--no-project",
            "--no-managed-python", "--no-python-downloads", "--no-config",
            "--cache-dir", str(target.root / ".omama" / "cache"), "--link-mode", "copy",
        ], target, uv_executable)
        interpreter = _runtime_python(staging)
        _run_uv([
            "pip", "install", "--python", str(interpreter), PYYAML_REQUIREMENT,
            "--no-python-downloads", "--no-config", "--no-sources",
            "--cache-dir", str(target.root / ".omama" / "cache"),
            "--link-mode", "copy", "--strict",
        ], target, uv_executable)
        value = _probe(interpreter, require_yaml=True)
        # A receipt environment contains its dependency, never the CLI.
        package_probe = subprocess.run(
            [str(interpreter), "-B", "-c", "import importlib.util,sys;sys.exit(1 if importlib.util.find_spec('omama_cli') else 0)"],
            env=_clean_probe_env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        if package_probe.returncode != 0:
            raise InstallError("runtime-contaminated", "receipt runtime unexpectedly contains the omama CLI")
        transaction.publish_owned_tree(staging, ".omama/runtime")
    except Exception:
        if staging.exists():
            try:
                staging.resolve().relative_to(target.root.resolve())
            except ValueError:
                pass
            else:
                shutil.rmtree(str(staging))
        raise
    installed = _runtime_python(runtime).resolve()
    return {
        "runtime_mode": "managed",
        "receipt_interpreter": installed.as_posix(),
        "base_interpreter": candidate.as_posix(),
        "python_base_prefix": Path(base_value["base_prefix"]).resolve().as_posix(),
        "python_version": ".".join(str(x) for x in base_value["version"]),
        "pyyaml_version": str(value["pyyaml"]),
    }
