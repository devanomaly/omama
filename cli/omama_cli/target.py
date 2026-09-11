"""Repository discovery and path safety for the phase-1 installer."""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


GIT_ROUTING = (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR", "GIT_NAMESPACE",
    "GIT_CEILING_DIRECTORIES", "GIT_DISCOVERY_ACROSS_FILESYSTEM",
    "GIT_CONFIG", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT",
    "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM",
)
GIT_CONFIG_PREFIXES = ("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")
UNSAFE_SHELL_CHARS = ("|", "&", ";", "<", ">", "`", "\r", "\n", "$")


class TargetError(ValueError):
    def __init__(self, reason, message):
        super().__init__(message)
        self.reason = reason
        self.message = message


@dataclass(frozen=True)
class Target:
    root: Path
    git_dir: Path
    common_dir: Path
    index_path: Path
    linked_worktree: bool


def _run_git(cwd, *args):
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd)] + list(args),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", check=False,
        )
    except OSError as exc:
        raise TargetError("git-unavailable", "git could not run: {0}".format(type(exc).__name__))
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        suffix = detail[-1][:300] if detail else "no diagnostic"
        raise TargetError("unsupported-git-target", "git {0} failed: {1}".format(args[0], suffix))
    return result.stdout.strip()


def routing_names(environ=None):
    environ = os.environ if environ is None else environ
    return sorted(
        key for key in environ
        if key in GIT_ROUTING or key.startswith(GIT_CONFIG_PREFIXES)
    )


# Per-command Git configuration for fixture-owned scratch repositories.  These
# are passed as ``git -c`` arguments, never as environment variables: the
# installed receipt gate refuses inherited ``GIT_CONFIG_*`` routing, and that
# accepted guard is not weakened to make isolation pass.  Only Git reads them,
# so the interpreter's HOME, XDG and user-site selection are untouched and the
# dependency the gate imports is unchanged.
GIT_SCRATCH_PINS = (
    "commit.gpgsign=false",
    "tag.gpgsign=false",
    "core.autocrlf=false",
    "core.safecrlf=false",
    "init.templateDir=",
)


def git_scratch_command(repository, *arguments):
    """``git`` argv for a scratch repository with adopter inputs neutralized."""
    pinned = []
    for pin in GIT_SCRATCH_PINS:
        pinned.extend(["-c", pin])
    return ["git", "-C", str(repository)] + pinned + list(arguments)


def validate_command_path(path):
    text = Path(path).as_posix()
    found = [char for char in UNSAFE_SHELL_CHARS if char in text]
    if found:
        raise TargetError(
            "unsupported-command-path",
            "path contains command syntax the certified hook grammar refuses ({0}); "
            "choose a repository path without shell operators, newlines, backticks, or dollar expansion"
            .format(", ".join(repr(value) for value in found)),
        )


def _is_reparse_or_symlink(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    except NotADirectoryError:
        # A regular file stands where one of this path's parent directories
        # must be.  That is a malformed destination, and the containment walk
        # is where it is first observed -- before any snapshot is taken -- so
        # it is named here rather than escaping as a traceback.
        raise TargetError(
            "unsafe-destination",
            "a path component is a regular file, not a directory: {0}".format(path),
        )
    except OSError as exc:
        raise TargetError(
            "unsafe-destination",
            "path component could not be inspected: {0}: {1}".format(type(exc).__name__, path),
        )
    if path.is_symlink():
        return True
    attributes = getattr(info, "st_file_attributes", 0)
    reparse = getattr(os.stat_result, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    if not reparse:
        reparse = getattr(__import__("stat"), "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(attributes & reparse)


def ensure_no_reparse(root, path, include_leaf=True):
    root = Path(root).resolve()
    path = Path(path)
    try:
        relative = path.absolute().relative_to(root)
    except ValueError:
        raise TargetError("path-escape", "destination escapes repository root: {0}".format(path))
    current = root
    parts = relative.parts if include_leaf else relative.parts[:-1]
    for part in parts:
        current = current / part
        if _is_reparse_or_symlink(current):
            raise TargetError(
                "path-reparse",
                "destination traverses a symlink or junction/reparse point: {0}".format(current),
            )


def safe_destination(root, relative):
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise TargetError("unsafe-destination", "bundle destination is not a forward-slash relative path")
    candidate = Path(relative)
    if candidate.is_absolute() or any(part in ("", ".", "..") for part in candidate.parts):
        raise TargetError("path-escape", "bundle destination escapes repository root: {0}".format(relative))
    result = Path(root) / candidate
    try:
        result.absolute().relative_to(Path(root).resolve())
    except ValueError:
        raise TargetError("path-escape", "bundle destination escapes repository root: {0}".format(relative))
    ensure_no_reparse(root, result, include_leaf=True)
    return result


def resolve_target(path, environ=None):
    names = routing_names(environ)
    if names:
        raise TargetError(
            "inherited-git-routing",
            "inherited Git routing is unsafe: {0}; unset these variables and retry"
            .format(", ".join(names)),
        )
    supplied = Path(path).absolute()
    if not supplied.is_dir():
        raise TargetError("unsupported-git-target", "target is not an existing directory: {0}".format(supplied))
    if _is_reparse_or_symlink(supplied) or supplied.resolve() != supplied:
        raise TargetError("path-reparse", "target path uses a symlink, junction, or reparse point: {0}".format(supplied))
    root = Path(_run_git(supplied, "rev-parse", "--show-toplevel")).resolve()
    if _run_git(root, "rev-parse", "--is-bare-repository").lower() != "false":
        raise TargetError("unsupported-git-target", "bare Git repositories are not install targets")
    try:
        supplied.resolve().relative_to(root)
    except ValueError:
        raise TargetError("path-escape", "resolved target is outside its worktree root")
    validate_command_path(root)
    ensure_no_reparse(root, root, include_leaf=True)

    def git_path(value):
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = root / candidate
        return candidate.resolve()

    git_dir = git_path(_run_git(root, "rev-parse", "--git-dir"))
    common_dir = git_path(_run_git(root, "rev-parse", "--git-common-dir"))
    index_path = git_path(_run_git(root, "rev-parse", "--git-path", "index"))
    return Target(
        root=root,
        git_dir=git_dir,
        common_dir=common_dir,
        index_path=index_path,
        linked_worktree=git_dir != common_dir,
    )
