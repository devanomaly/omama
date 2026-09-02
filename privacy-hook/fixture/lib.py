"""Shared setup for the privacy-hook fixture cases.

Creates a throwaway git repo under a temp dir, installs the hook + a
sample config into it, and exposes a helper to attempt a commit and
report what happened. No writes outside the temp dir.
"""
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PIECE_DIR = os.path.dirname(HERE)


def _tmp_base():
    """Keep fixture scratch space inside this piece's own fixture/ dir
    (not the OS temp dir) so a run never writes outside the toolkit
    deliverable tree. Caller is responsible for cleanup; case_*.py leave
    the tree for post-mortem, `check.py` runs are meant to be wiped by
    the invoker (see README)."""
    base = os.path.join(HERE, ".tmp")
    os.makedirs(base, exist_ok=True)
    return base


def rmtree(path, attempts=12, delay=0.15):
    """Delete a scratch repo tree, on Windows too. Returns True if the
    tree is gone.

    The old call was `shutil.rmtree(tmp, ignore_errors=True)`, and it
    failed on essentially every scratch repo -- silently, because
    `ignore_errors` is exactly the flag that hides the failure. A fully
    GREEN corpus run still left one directory per case behind (74 of
    them, measured on a clean start). Two distinct causes, both real and
    both Windows-specific:

      1. git writes its loose objects READ-ONLY, and Windows refuses to
         unlink a read-only file. Fixed by clearing the bit and retrying
         the same operation.
      2. right after `git commit` returns, the repo DIRECTORY is still
         held by an exiting child (the hook's shell and the git
         subprocesses it spawned): `PermissionError(13, 'the file is in
         use by another process')` on `rmdir`. Nothing to chmod here --
         it just needs a moment. Measured: 1-2 retries at 150 ms.

    The bounded retry loop covers both, and the return value means the
    caller can REPORT a tree it could not remove instead of pretending."""
    def _clear_readonly(func, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError:
            pass

    for i in range(attempts):
        if not os.path.exists(path):
            return True
        if sys.version_info >= (3, 12):
            shutil.rmtree(path, onexc=_clear_readonly)
        else:
            shutil.rmtree(path, onerror=_clear_readonly)
        if not os.path.exists(path):
            return True
        time.sleep(delay)
    return not os.path.exists(path)


def hook_env():
    """The environment the fixture hands to git, and git hands to the hook.

    The wrapper reads PRIVACY_HOOK_SCANNER from the AMBIENT environment --
    the exact leak case_scanner_override.py documents -- so a value the
    developer's shell happens to export would reach every fixture repo:
    a path absent here blocks every case with `missing-scanner` (the
    smoke cases then die at setup, rc=2), a path present but pointing at
    the wrong script turns the hook into a no-op (`FIXTURE BUG: violating
    commit was NOT blocked`). Every case charges the DEFAULT location
    unless it sets the knob on purpose, so the knob is dropped here and
    re-added only by the one case that means it (case_scanner_override's
    own commit helper)."""
    env = os.environ.copy()
    env.pop("PRIVACY_HOOK_SCANNER", None)
    return env


def make_repo():
    tmp = tempfile.mkdtemp(prefix="privacy-hook-fixture-", dir=_tmp_base())
    repo = os.path.join(tmp, "repo")
    os.makedirs(repo)

    def run(*args, **kw):
        r = subprocess.run(args, cwd=repo, capture_output=True, text=True,
                           env=hook_env(), **kw)
        return r

    run("git", "init", "-q")
    run("git", "config", "user.email", "fixture@example.test")
    run("git", "config", "user.name", "Fixture Runner")

    # Install hook + config exactly as README "Como adotar" step 1/2
    # instruct an adopting team to: scan_staged.py at the repo root,
    # the shipped pre-commit file copied byte-for-byte into
    # .git/hooks/pre-commit. No rewriting -- this must exercise the
    # artifact a colleague actually installs, not a stand-in for it.
    hooks_dir = os.path.join(repo, ".git", "hooks")
    shutil.copy(os.path.join(PIECE_DIR, "scan_staged.py"),
                os.path.join(repo, "scan_staged.py"))
    shutil.copy(os.path.join(PIECE_DIR, "pre-commit"),
                os.path.join(hooks_dir, "pre-commit"))
    os.chmod(os.path.join(hooks_dir, "pre-commit"), 0o755)

    shutil.copy(os.path.join(PIECE_DIR, "privacy-deny.json"),
                os.path.join(repo, "privacy-deny.json"))
    shutil.copy(os.path.join(PIECE_DIR, "privacy-tokens.txt"),
                os.path.join(repo, "privacy-tokens.txt"))

    run("git", "add", "scan_staged.py", "privacy-deny.json", "privacy-tokens.txt")
    r = run("git", "commit", "-q", "-m", "chore: install privacy-hook")
    if r.returncode != 0:
        sys.stderr.write("fixture setup failed: %s\n%s\n" % (r.stdout, r.stderr))
        sys.exit(2)

    return repo


# ADOPTION step 2c, verbatim shape: the hook git calls is a two-line
# launcher that sets the knob and hands over to the SHIPPED wrapper, kept
# as its own file so it stays byte-identical with upstream.
LAUNCHER = (b"#!/bin/sh\n"
            b"# .githooks/<hook-name> -- ADOPTION step 2c launcher\n"
            b"PRIVACY_HOOK_SCANNER=tools/scan_staged.py\n"
            b"export PRIVACY_HOOK_SCANNER\n"
            b"exec sh .githooks/privacy-pre-commit\n")


def make_versioned_repo(merge_hook="launcher"):
    """ADOPTION route (a) + step 2c + step 3 COMPOSED, the way an adopter
    who vendors the scanner under tools/ ends up installed:

      - `git config core.hooksPath .githooks` (route a), the hooks dir
        tracked in the repo;
      - scan_staged.py at tools/scan_staged.py, config + tokens at the
        root (those two are not movable -- step 5);
      - the shipped wrapper, byte-for-byte, at .githooks/privacy-pre-commit;
      - .githooks/pre-commit = LAUNCHER (step 2c);
      - .githooks/pre-merge-commit (step 3) = the same LAUNCHER when
        merge_hook == "launcher" -- what step 3 says now -- or a bare
        copy of the shipped wrapper when merge_hook == "wrapper", which
        is what step 3 USED to say and is the red of
        case_hookspath_merge.py: that wrapper looks for the scanner at
        the root, finds nothing, and refuses every merge, clean or not.

    Everything a colleague would `git pull` is committed in the initial
    commit, which itself goes through the pre-commit launcher."""
    if merge_hook not in ("launcher", "wrapper"):
        raise ValueError("merge_hook must be 'launcher' or 'wrapper'")
    tmp = tempfile.mkdtemp(prefix="privacy-hook-fixture-", dir=_tmp_base())
    repo = os.path.join(tmp, "repo")
    os.makedirs(repo)

    def run(*args):
        return subprocess.run(args, cwd=repo, capture_output=True, text=True,
                              env=hook_env())

    run("git", "init", "-q")
    run("git", "config", "user.email", "fixture@example.test")
    run("git", "config", "user.name", "Fixture Runner")
    run("git", "config", "core.hooksPath", ".githooks")

    os.makedirs(os.path.join(repo, "tools"))
    os.makedirs(os.path.join(repo, ".githooks"))
    shutil.copy(os.path.join(PIECE_DIR, "scan_staged.py"),
                os.path.join(repo, "tools", "scan_staged.py"))
    shutil.copy(os.path.join(PIECE_DIR, "privacy-deny.json"),
                os.path.join(repo, "privacy-deny.json"))
    shutil.copy(os.path.join(PIECE_DIR, "privacy-tokens.txt"),
                os.path.join(repo, "privacy-tokens.txt"))
    shutil.copy(os.path.join(PIECE_DIR, "pre-commit"),
                os.path.join(repo, ".githooks", "privacy-pre-commit"))

    write_file(repo, ".githooks/pre-commit", LAUNCHER)
    if merge_hook == "launcher":
        write_file(repo, ".githooks/pre-merge-commit", LAUNCHER)
    else:
        shutil.copy(os.path.join(PIECE_DIR, "pre-commit"),
                    os.path.join(repo, ".githooks", "pre-merge-commit"))
    for name in ("pre-commit", "pre-merge-commit"):
        os.chmod(os.path.join(repo, ".githooks", name), 0o755)

    run("git", "add", "tools/scan_staged.py", "privacy-deny.json",
        "privacy-tokens.txt", ".githooks")
    r = run("git", "commit", "-q", "-m", "chore: install privacy-hook (versioned)")
    if r.returncode != 0:
        sys.stderr.write("fixture setup failed: %s\n%s\n" % (r.stdout, r.stderr))
        sys.exit(2)

    return repo


def write_file(repo, relpath, content_bytes):
    full = os.path.join(repo, relpath)
    os.makedirs(os.path.dirname(full), exist_ok=True) if os.path.dirname(full) else None
    with open(full, "wb") as f:
        f.write(content_bytes)


def git(repo, *args):
    return subprocess.run(["git"] + list(args), cwd=repo,
                          capture_output=True, text=True, env=hook_env())


def attempt_commit(repo, message):
    git(repo, "add", "-A")
    return git(repo, "commit", "-q", "-m", message)


def commit(repo, message):
    """Attempt a commit WITHOUT staging anything first.

    The corpus runner stages each case explicitly (`git add <path>`,
    `git mv`, `git rm`) because some cases -- renames, deletions of the
    config -- are defined by HOW they are staged, and `git add -A` would
    flatten that distinction away."""
    return git(repo, "commit", "-m", message)
