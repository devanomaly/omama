"""Durable receipt interpreter qualification and target-owned provisioning."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .install import InstallError
from .target import validate_command_path


PYTHON_FLOOR = (3, 8)
PYTHON_CEILING = (4, 0)
PYYAML_MIN = (6, 0, 2)
PYYAML_MAX = (7, 0, 0)
PYYAML_REQUIREMENT = "PyYAML>=6.0.2,<7"

# Inherited controls that can change which distributions uv installs, which
# Python it selects, or where it writes.  `--no-seed` is not enforcement: uv
# 0.9.10 reports that the flag has no effect while still honouring
# ``UV_VENV_SEED``.  Scrubbing the environment carries the guarantee, and the
# post-provision inventory proves it.
UV_SCRUB_PREFIXES = ("UV_", "PIP_")
UNSAFE_PYTHON_CONTROLS = (
    "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE",
    "PYTHONNOUSERSITE", "PYTHONEXECUTABLE", "PYTHONPLATLIBDIR",
    "VIRTUAL_ENV", "CONDA_PREFIX", "CONDA_DEFAULT_ENV",
    "SETUPTOOLS_USE_DISTUTILS", "PYTHONWARNINGS",
)
# Distribution names a freshly created, unseeded uv environment may legitimately
# carry in addition to the selected dependency.  Anything else is unapproved.
ALLOWED_RUNTIME_DISTRIBUTIONS = frozenset()
RUNTIME_OWNER_MARKER = ".omama-runtime-owner.json"


def _release_tuple(value):
    """Parse a release version without gluing separate fields together.

    ``6.0.2rc1`` is a pre-release of ``6.0.2`` and must never compare as
    ``(6, 0, 21)``; a non-numeric field ends the release and marks the value as
    a pre-release, which sorts below the corresponding final release.
    """
    release = []
    prerelease = False
    for part in str(value).split("."):
        if part.isdigit():
            release.append(int(part))
            continue
        digits = ""
        for char in part:
            if not char.isdigit():
                break
            digits += char
        if digits:
            release.append(int(digits))
        prerelease = True
        break
    return tuple(release), prerelease


def _version_at_least(value, floor):
    release, prerelease = _release_tuple(value)
    if release > floor:
        return True
    if release < floor:
        return False
    return not prerelease


def _version_below(value, ceiling):
    release, _prerelease = _release_tuple(value)
    return release < ceiling


def _clean_probe_env():
    """Environment for interpreter probes.

    Only unsafe *process* controls are removed.  HOME, XDG and user-site
    selection are deliberately preserved: rewriting them changes which
    dependency the interpreter actually imports, so a probe run under a
    replaced HOME would qualify a different package than the installed gate
    will later execute.
    """
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env.pop("VIRTUAL_ENV", None)
    return env


# Removes only the unsafe current-working-directory entry.  ``-I``/``-s`` are
# not equivalent substitutes: they also hide the user site the installed gate
# will import from.
_PROBE_PREAMBLE = (
    "import sys,os; "
    "_cwd=os.getcwd(); "
    "sys.path[:] = [p for i,p in enumerate(sys.path) "
    "if not (i == 0 and (p == '' or p == '.' or os.path.abspath(p) == _cwd))]; "
)


def _probe(interpreter, require_yaml, capability=False):
    """Observe an interpreter from a neutral directory.

    ``capability`` records what the installed gate actually needs (a working
    ``yaml.safe_load`` round trip) alongside the imported module's real path,
    instead of trusting a self-reported version string.
    """
    code = (
        _PROBE_PREAMBLE
        + "import json; "
        "d={'executable':sys.executable,'prefix':sys.prefix,'base_prefix':getattr(sys,'base_prefix',sys.prefix),"
        "'version':[sys.version_info[0],sys.version_info[1],sys.version_info[2]]}; "
    )
    if require_yaml:
        code += "import yaml; d['pyyaml']=yaml.__version__; d['pyyaml_path']=getattr(yaml,'__file__',None); "
        if capability:
            code += (
                "d['pyyaml_capability']=(yaml.safe_load('a: 1') == {'a': 1} "
                "and yaml.safe_load(yaml.safe_dump({'b': [1, 2]})) == {'b': [1, 2]}); "
            )
    code += "print(json.dumps(d,sort_keys=True))"
    try:
        # A neutral, process-owned directory: no repository content is on the
        # search path and no repository file can be executed by an import.
        with tempfile.TemporaryDirectory(prefix="omama-probe-") as neutral:
            result = subprocess.run(
                [str(interpreter), "-B", "-c", code], env=_clean_probe_env(), cwd=neutral,
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
    if require_yaml and capability:
        if value.get("pyyaml_capability") is not True:
            raise InstallError(
                "dependency-incapable",
                "PyYAML {0} at {1} did not complete the required safe_load/safe_dump round trip"
                .format(value.get("pyyaml"), value.get("pyyaml_path")),
            )
    elif require_yaml:
        reported = value.get("pyyaml")
        if not (_version_at_least(reported, PYYAML_MIN) and _version_below(reported, PYYAML_MAX)):
            raise InstallError("dependency-version", "PyYAML {0} is outside >=6.0.2,<7".format(reported))
    return value


def _normalized(path):
    """Absolute, lexically normalized path.

    ``Path.absolute()`` keeps ``..`` components, so a peer directory spelled
    ``<root>/../peer`` compares as if it were inside ``<root>``.
    """
    return Path(os.path.normpath(str(Path(path).absolute())))


def _is_within(path, parent):
    try:
        Path(path).resolve().relative_to(Path(parent).resolve())
        return True
    except ValueError:
        return False


def _is_lexically_within(path, parent):
    try:
        _normalized(path).relative_to(_normalized(parent))
        return True
    except ValueError:
        return False


def qualify_explicit(path, target=None):
    supplied = Path(path)
    if not supplied.is_absolute():
        raise InstallError("explicit-python-not-absolute", "--python requires an absolute interpreter path")
    validate_command_path(supplied)
    resolved = supplied.resolve()
    if not resolved.is_file():
        raise InstallError("interpreter-unrunnable", "explicit interpreter is not an existing regular file")
    if target is not None and (
            _is_lexically_within(supplied, target.root) or _is_within(resolved, target.root)):
        raise InstallError("interpreter-not-durable", "explicit interpreter is inside the target repository")
    # The read-only explicit route is qualified by the capability the installed
    # gate requires, not by a universal PyYAML version floor it never earned.
    # The Python floor, containment and durability requirements are unchanged.
    value = _probe(supplied, require_yaml=True, capability=True)
    return {
        "runtime_mode": "explicit",
        # The lexical executable selects the supplied environment on POSIX,
        # where venv and hosted-tool Python entrypoints are normally symlinks.
        # Keep the canonical executable as an independent durability identity.
        "receipt_interpreter": supplied.absolute().as_posix(),
        "base_interpreter": Path(value["executable"]).resolve().as_posix(),
        "python_base_prefix": Path(value["base_prefix"]).resolve().as_posix(),
        "python_version": ".".join(str(x) for x in value["version"]),
        "pyyaml_version": str(value["pyyaml"]),
        # The dependency that was actually imported, not merely a version claim.
        "pyyaml_path": str(value.get("pyyaml_path") or ""),
        "dependency_qualification": "capability",
    }


def _uv_env(target):
    """Program-owned uv environment.

    Every inherited ``UV_*``/``PIP_*`` control and unsafe Python control is
    removed before the program's own controls are applied, so a caller cannot
    add unapproved distributions, redirect the Python selection, or move the
    cache.
    """
    env = {
        key: value for key, value in os.environ.items()
        if not key.startswith(UV_SCRUB_PREFIXES) and key not in UNSAFE_PYTHON_CONTROLS
    }
    cache = target.root / ".omama" / "cache"
    temporary = cache / "tmp"
    env.update({
        "UV_CACHE_DIR": str(cache), "UV_NO_CONFIG": "1",
        "UV_PYTHON_DOWNLOADS": "never", "UV_LINK_MODE": "copy",
        "TMP": str(temporary), "TEMP": str(temporary), "TMPDIR": str(temporary),
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    return env


def scrubbed_environment_inventory(environ=None):
    """Names removed from, and controls imposed on, the uv environment."""
    environ = os.environ if environ is None else environ
    return {
        "removed": sorted(
            key for key in environ
            if key.startswith(UV_SCRUB_PREFIXES) or key in UNSAFE_PYTHON_CONTROLS
        ),
        "imposed": [
            "UV_CACHE_DIR", "UV_NO_CONFIG", "UV_PYTHON_DOWNLOADS", "UV_LINK_MODE",
            "TMP", "TEMP", "TMPDIR", "PYTHONDONTWRITEBYTECODE",
        ],
        "no_seed_credited": False,
    }


def _uv_diagnostic(result):
    """Preserve uv's actionable lines instead of whatever printed last.

    uv ends failures with usage boilerplate, so the final line alone hides the
    cause.
    """
    combined = ((result.stderr or "") + "\n" + (result.stdout or "")).strip().splitlines()
    lines = [line.strip() for line in combined if line.strip()]
    actionable = [line for line in lines if line.lower().startswith(("error:", "warning:", "fatal:", "caused by"))]
    selected = actionable or lines[-1:]
    return " | ".join(selected)[:600] or "no diagnostic"


def _run_uv(arguments, target, uv_executable):
    cache = target.root / ".omama" / "cache"
    temporary = cache / "tmp"
    cache.mkdir(parents=True, exist_ok=True)
    temporary.mkdir(parents=True, exist_ok=True)
    env = _uv_env(target)
    try:
        result = subprocess.run(
            [str(uv_executable)] + list(arguments), cwd=str(target.root), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", timeout=300, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise InstallError("uv-unavailable", "uv command could not run: {0}".format(type(exc).__name__))
    if result.returncode != 0:
        raise InstallError("runtime-provision-failed", "uv {0} exited {1}: {2}".format(arguments[0], result.returncode, _uv_diagnostic(result)))
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
    supplied = Path(path)
    candidate = supplied.resolve()
    if not candidate.is_file():
        raise InstallError("base-python-unavailable", "managed base interpreter is missing")
    if _is_lexically_within(supplied, target.root) or _is_within(candidate, target.root):
        raise InstallError("interpreter-not-durable", "managed base interpreter is inside the target repository")
    tool_prefix = Path(sys.prefix).resolve()
    base_prefix = Path(getattr(sys, "base_prefix", sys.prefix)).resolve()
    if tool_prefix != base_prefix and _is_within(candidate, tool_prefix):
        raise InstallError("interpreter-not-durable", "managed base resolves inside the disposable CLI/tool environment")
    # Probe the selected entrypoint before canonicalizing its durable identity:
    # a POSIX venv's bin/python normally resolves to its system base.
    value = _probe(supplied, require_yaml=False)
    if Path(value["prefix"]).resolve() != Path(value["base_prefix"]).resolve():
        raise InstallError("interpreter-not-durable", "managed base is itself a virtual environment, not an independent system Python")
    return candidate, value


def _runtime_python(runtime):
    # This function also plans the settings command before the runtime exists;
    # select by platform rather than by premature file existence.
    return runtime / "Scripts" / "python.exe" if os.name == "nt" else runtime / "bin" / "python"


def managed_runtime_interpreter(target):
    return _runtime_python(target.root / ".omama" / "runtime").absolute()


def runtime_distributions(interpreter):
    """Distribution names installed in an owned runtime, or ``None``."""
    code = (
        _PROBE_PREAMBLE
        + "import json\n"
        "try:\n"
        "    from importlib import metadata\n"
        "except ImportError:\n"
        "    import importlib_metadata as metadata\n"
        "names = sorted({(d.metadata['Name'] or '').lower() for d in metadata.distributions()} - {''})\n"
        "print(json.dumps(names))\n"
    )
    try:
        with tempfile.TemporaryDirectory(prefix="omama-inventory-") as neutral:
            result = subprocess.run(
                [str(interpreter), "-B", "-c", code], env=_clean_probe_env(), cwd=neutral,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace", timeout=60, check=False,
            )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    try:
        value = json.loads(result.stdout.strip())
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, list) else None


def _require_owned_inventory(interpreter):
    names = runtime_distributions(interpreter)
    if names is None:
        raise InstallError("runtime-inventory-unavailable", "owned runtime inventory could not be read")
    unexpected = sorted(set(names) - {"pyyaml"} - ALLOWED_RUNTIME_DISTRIBUTIONS)
    if unexpected:
        raise InstallError(
            "runtime-inventory-unapproved",
            "owned runtime contains unapproved distribution(s): {0}; the selected dependency is PyYAML only"
            .format(", ".join(unexpected)),
        )
    if "pyyaml" not in names:
        raise InstallError("runtime-inventory-incomplete", "owned runtime does not contain the selected PyYAML distribution")
    return names


def _owned_runtime_state(plan):
    """Classify an existing managed runtime as absent, owned, or not ours."""
    runtime = plan.target.root / ".omama" / "runtime"
    if not runtime.exists():
        return "absent", runtime
    if runtime.is_symlink() or not runtime.is_dir():
        return "unowned", runtime
    marker = runtime / RUNTIME_OWNER_MARKER
    if not marker.is_file():
        return "unowned", runtime
    try:
        value = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return "drifted", runtime
    if not isinstance(value, dict) or value.get("schema") != 1 or not value.get("owner"):
        return "drifted", runtime
    return "owned", runtime


def _reusable_managed(plan):
    state = plan.existing_state
    if not state or state.get("runtime_mode") != "managed":
        return None
    interpreter = Path(str(state.get("receipt_interpreter", "")))
    expected = plan.target.root / ".omama" / "runtime"
    if interpreter.absolute() != _runtime_python(expected).absolute():
        raise InstallError("incompatible-runtime", "recorded managed interpreter is outside .omama/runtime")
    ownership, _runtime = _owned_runtime_state(plan)
    if ownership == "absent":
        # Doctor's "rerun init in this clone/worktree" remedy depends on this:
        # a wholly absent owned runtime is re-provisioned rather than probed.
        return None
    if ownership != "owned":
        raise InstallError(
            "incompatible-runtime",
            "existing .omama/runtime is {0}; it is named and preserved rather than deleted or overwritten"
            .format("not owned by omama" if ownership == "unowned" else "owned-marker drifted"),
        )
    if not interpreter.is_file():
        raise InstallError(
            "incompatible-runtime",
            "owned .omama/runtime exists but its interpreter is missing; remove the runtime tree deliberately and rerun init",
        )
    value = _probe(interpreter, require_yaml=True)
    return {
        "runtime_mode": "managed",
        "receipt_interpreter": interpreter.absolute().as_posix(),
        "base_interpreter": str(state.get("base_interpreter")),
        "python_base_prefix": str(state.get("python_base_prefix", value["base_prefix"])),
        "python_version": ".".join(str(x) for x in value["version"]),
        "pyyaml_version": str(value["pyyaml"]),
        "pyyaml_path": str(value.get("pyyaml_path") or ""),
        "dependency_qualification": "pinned",
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
    candidate = Path(base_python) if base_python else discover_base(target, uv_executable)
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
        _probe(interpreter, require_yaml=True)
        # The scrubbed environment, not `--no-seed`, carries the guarantee;
        # this inventory is what proves it for this provisioning.
        inventory = _require_owned_inventory(interpreter)
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
    installed = _runtime_python(runtime).absolute()
    # Record the dependency identity of the *published* runtime, not of the
    # transaction-owned staging tree it was built in: the recorded path is what
    # doctor re-observes later.
    published = _probe(installed, require_yaml=True)
    return {
        "runtime_mode": "managed",
        "receipt_interpreter": installed.as_posix(),
        "base_interpreter": candidate.as_posix(),
        "python_base_prefix": Path(base_value["base_prefix"]).resolve().as_posix(),
        "python_version": ".".join(str(x) for x in base_value["version"]),
        "pyyaml_version": str(published["pyyaml"]),
        "pyyaml_path": str(published.get("pyyaml_path") or ""),
        "dependency_qualification": "pinned",
        "runtime_distributions": inventory,
    }
