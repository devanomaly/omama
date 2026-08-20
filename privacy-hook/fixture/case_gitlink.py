#!/usr/bin/env python3
"""Gitlink filename case (5th external review, 2026-08-18).

A staged SUBMODULE POINTER (gitlink, mode 160000) has no blob to scan, but
it does have a path -- and deny_filenames is a policy about paths. The
gitlink skip used to run BEFORE the deny-filename check, so a submodule
named `.env` sailed through the exact rule written to stop that name.

Two polarities in one case:
  red   -- gitlink staged at path `.env` must be BLOCKED (deny-filename);
  green -- gitlink staged at an innocent path (`vendor-lib`) must still be
           skipped without a bogus unreadable-staged-blob block (that skip
           is the entire reason GITLINK_MODE handling exists).

Exits 0 when both polarities hold, 1 otherwise.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

# An arbitrary commit id: a gitlink references a commit in the SUBMODULE's
# object db, so the parent repo never needs the object to exist.
FAKE_COMMIT = "a" * 40


def main():
    repo = lib.make_repo()
    ok = True

    r = lib.git(repo, "update-index", "--add", "--cacheinfo",
                "160000,%s,.env" % FAKE_COMMIT)
    if r.returncode != 0:
        sys.stderr.write("FIXTURE BUG: could not stage gitlink: %s\n" % r.stderr)
        return 2
    r = lib.commit(repo, "should be blocked: gitlink named .env")
    out = r.stdout + r.stderr
    if r.returncode == 0:
        sys.stderr.write("FAIL: gitlink named .env was NOT blocked\n")
        ok = False
    elif "deny-filename" not in out:
        sys.stderr.write("FAIL: gitlink .env blocked, but not by "
                         "deny-filename:\n%s\n" % out)
        ok = False
    else:
        print("PASS: gitlink named .env blocked by deny-filename (red proven)")

    lib.git(repo, "rm", "--cached", ".env")
    r = lib.git(repo, "update-index", "--add", "--cacheinfo",
                "160000,%s,vendor-lib" % FAKE_COMMIT)
    if r.returncode != 0:
        sys.stderr.write("FIXTURE BUG: could not stage gitlink: %s\n" % r.stderr)
        return 2
    r = lib.commit(repo, "innocent gitlink should pass")
    if r.returncode != 0:
        sys.stderr.write("FAIL: innocently-named gitlink was blocked "
                         "(gitlink skip regressed):\n%s%s\n"
                         % (r.stdout, r.stderr))
        ok = False
    else:
        print("PASS: innocently-named gitlink committed (green proven)")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
