#!/usr/bin/env python3
"""Fixture runner for ../check_pr_base.py.

Runs the checker against one clean base name, two planted violations, and the
not-runnable (no argument) case, asserts the exit code and message match, so a
future edit can't silently widen or narrow what counts as a valid base. Then
does the same for the ancestry mode (`--ancestry <head-sha> <head-ref>`),
building throwaway git repos under a tempdir so the fork-from-unmerged-sibling
case actually exists on disk rather than being asserted from prose.

Exit code 0 -> all cases behaved as expected (checker is correct).
Exit code 1 -> at least one case behaved unexpectedly (checker is broken, or
               someone weakened it).

Usage:
    python3 run_check_pr_base_fixture.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHECKER = HERE.parent / "check_pr_base.py"

# (argv-after-script, expected exit, label, required stderr/stdout substrings)
CASES = [
    (["master"], 0, "clean case: base is master", ["OK: PR base is 'master'"]),
    (["contributing"], 1,
     "planted violation: base is a non-master branch",
     ["VIOLATION: PR base is 'contributing'", "must be 'master'"]),
    (["MASTER"], 1,
     "planted violation: case-sensitive mismatch is still a violation",
     ["VIOLATION: PR base is 'MASTER'"]),
    ([], 2, "not runnable: no base ref name given",
     ["VIOLATION: no base ref name given"]),
    ([""], 2, "not runnable: empty base ref name",
     ["VIOLATION: no base ref name given"]),
    # --- ancestry mode: not-runnable argument cases (no repo needed) ---
    (["--ancestry"], 2, "ancestry not runnable: no head sha/ref given",
     ["VIOLATION: no head SHA / head ref name given"]),
    (["--ancestry", "", ""], 2, "ancestry not runnable: empty head sha/ref",
     ["VIOLATION: no head SHA / head ref name given"]),
    (["--ancestry", "deadbeef", ""], 2,
     "ancestry not runnable: empty head ref with a sha given",
     ["VIOLATION: no head SHA / head ref name given"]),
]


def run(argv, cwd=None):
    return subprocess.run([sys.executable, str(CHECKER), *argv],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=30,
                          cwd=str(cwd) if cwd else None)


def _git(cwd, *args):
    proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(
            f"fixture setup: git {' '.join(args)} failed in {cwd}\n"
            f"{proc.stdout}{proc.stderr}")
    return proc.stdout.strip()


def _init_bare_and_clone(root):
    """A bare 'origin' plus a push-capable clone named 'work'."""
    origin = root / "origin.git"
    _git(root, "init", "-q", "--bare", "-b", "master", str(origin))
    work = root / "work"
    _git(root, "clone", "-q", str(origin), str(work))
    _git(work, "config", "user.email", "fixture@example.invalid")
    _git(work, "config", "user.name", "fixture")
    return origin, work


def _commit(work, filename, content, message):
    (work / filename).write_text(content, encoding="utf-8")
    _git(work, "add", filename)
    _git(work, "commit", "-q", "-m", message)
    return _git(work, "rev-parse", "HEAD")


def _fresh_checkout(root, origin, name="checkout"):
    """A separate clone standing in for CI's checkout -- proves the checker
    works off refs/remotes/origin/*, not off `work`'s local branches."""
    dest = root / name
    _git(root, "clone", "-q", str(origin), str(dest))
    return dest


def build_clean(root):
    """Branch cut from master's tip; an unrelated sibling exists but shares
    no unique commits -> exit 0."""
    origin, work = _init_bare_and_clone(root)
    _commit(work, "a.txt", "base\n", "master: initial")
    _git(work, "push", "-q", "origin", "master")

    _git(work, "checkout", "-q", "-b", "sibling")
    _commit(work, "s.txt", "sibling\n", "sibling: unrelated work")
    _git(work, "push", "-q", "origin", "sibling")

    _git(work, "checkout", "-q", "master")
    _git(work, "checkout", "-q", "-b", "feature-clean")
    head_sha = _commit(work, "f.txt", "feature\n", "feature-clean: add feature")
    _git(work, "push", "-q", "origin", "feature-clean")

    checkout = _fresh_checkout(root, origin)
    return checkout, head_sha, "feature-clean", None


def build_fork(root):
    """feature-B is cut from sibling-A's tip, not master's -> exit 1, naming
    sibling-A and the shared commit."""
    origin, work = _init_bare_and_clone(root)
    _commit(work, "a.txt", "base\n", "master: initial")
    _git(work, "push", "-q", "origin", "master")

    _git(work, "checkout", "-q", "-b", "sibling-A")
    sib_sha = _commit(work, "a.txt", "sibling-A change\n", "sibling-A: unmerged work")
    _git(work, "push", "-q", "origin", "sibling-A")

    _git(work, "checkout", "-q", "-b", "feature-B")
    head_sha = _commit(work, "b.txt", "feature-B\n", "feature-B: cut from sibling-A")
    _git(work, "push", "-q", "origin", "feature-B")

    checkout = _fresh_checkout(root, origin)
    return checkout, head_sha, "feature-B", sib_sha


def build_merged(root):
    """Same shape as build_fork, but sibling-A merges into master before the
    check runs -> its commit is now legitimate master history -> exit 0."""
    origin, work = _init_bare_and_clone(root)
    _commit(work, "a.txt", "base\n", "master: initial")
    _git(work, "push", "-q", "origin", "master")

    _git(work, "checkout", "-q", "-b", "sibling-A")
    _commit(work, "a.txt", "sibling-A change\n", "sibling-A: work")
    _git(work, "push", "-q", "origin", "sibling-A")

    _git(work, "checkout", "-q", "-b", "feature-B")
    head_sha = _commit(work, "b.txt", "feature-B\n", "feature-B: cut from sibling-A")
    _git(work, "push", "-q", "origin", "feature-B")

    _git(work, "checkout", "-q", "master")
    _git(work, "merge", "-q", "--ff-only", "sibling-A")
    _git(work, "push", "-q", "origin", "master")

    checkout = _fresh_checkout(root, origin)
    return checkout, head_sha, "feature-B", None


def build_shallow(root):
    """A --depth 1 clone of an otherwise-normal repo -> exit 2, never a
    silent pass just because the history a real check needs isn't there."""
    origin, work = _init_bare_and_clone(root)
    head_sha = _commit(work, "a.txt", "base\n", "master: initial")
    _git(work, "push", "-q", "origin", "master")

    dest = root / "shallow"
    origin_uri = origin.resolve().as_uri()
    _git(root, "clone", "-q", "--depth", "1", origin_uri, str(dest))
    return dest, head_sha, "master", None


ANCESTRY_REPO_CASES = [
    (build_clean, 0, "ancestry clean: cut from master's tip",
     ["OK"], None),
    (build_fork, 1, "ancestry violation: forked from unmerged sibling-A",
     ["VIOLATION", "sibling-A"], "sib_sha"),
    (build_merged, 0, "ancestry clean: sibling-A merged before the check ran",
     ["OK"], None),
    (build_shallow, 2, "ancestry not runnable: shallow clone",
     ["VIOLATION: shallow repository"], None),
]


def run_static_cases():
    failures = []
    for argv, expected_rc, label, substrings in CASES:
        proc = run(argv)
        combined = (proc.stdout or "") + (proc.stderr or "")
        ok = proc.returncode == expected_rc
        missing = [s for s in substrings if s not in combined]
        if missing:
            ok = False
        status = "OK" if ok else "FAIL"
        print(f"{status}  {label} (exit={proc.returncode}, expected={expected_rc})")
        if not ok:
            failures.append(label)
            if missing:
                print(f"      missing substrings: {missing}")
            print("      --- output ---")
            print("      " + combined.strip().replace("\n", "\n      "))
    return failures


def run_ancestry_repo_cases():
    failures = []
    for builder, expected_rc, label, substrings, shared_sha_marker in ANCESTRY_REPO_CASES:
        with tempfile.TemporaryDirectory(prefix="check_pr_base_fixture_") as tmp:
            root = Path(tmp)
            cwd, head_sha, head_ref, sib_sha = builder(root)
            wanted = list(substrings)
            if shared_sha_marker == "sib_sha":
                wanted.append(sib_sha[:7])
            proc = run(["--ancestry", head_sha, head_ref], cwd=cwd)
            combined = (proc.stdout or "") + (proc.stderr or "")
            ok = proc.returncode == expected_rc
            missing = [s for s in wanted if s not in combined]
            if missing:
                ok = False
            status = "OK" if ok else "FAIL"
            print(f"{status}  {label} (exit={proc.returncode}, expected={expected_rc})")
            if not ok:
                failures.append(label)
                if missing:
                    print(f"      missing substrings: {missing}")
                print("      --- output ---")
                print("      " + combined.strip().replace("\n", "\n      "))
    return failures


def main():
    failures = run_static_cases()
    failures += run_ancestry_repo_cases()
    total = len(CASES) + len(ANCESTRY_REPO_CASES)
    print()
    if failures:
        print(f"run_check_pr_base_fixture: {len(failures)}/{total} case(s) FAILED")
        return 1
    print(f"run_check_pr_base_fixture: all {total} cases behaved as expected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
