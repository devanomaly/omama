#!/usr/bin/env python3
"""Versioned hooks dir + relocated scanner + `pre-merge-commit`, composed
(review of #15, 2026-09-02).

ADOPTION route (a) puts the hooks under a tracked `.githooks/` activated
with `core.hooksPath`; step 2c makes `pre-commit` a two-line launcher that
exports PRIVACY_HOOK_SCANNER and hands over to the shipped wrapper; step 3
installs a second hook under the name `pre-merge-commit`, because git
calls THAT one on an automatic merge. Each step was documented alone. Two
independent reviews found that they did not compose: step 3 said to copy
the SHIPPED wrapper, which looks for the scanner at the repo root -- and
for a 2c adopter nothing is there. Every automatic merge, clean or not,
was refused with `BLOCKED hook-error missing-scanner ... set
PRIVACY_HOOK_SCANNER`, a variable the adopter had set.

Three assertions, one throwaway repo built by lib.make_versioned_repo(),
hooks installed the way step 3 now says (the launcher under BOTH names):

  1. plain commit with a planted key -> refused by the scanner's verdict
     (`BLOCKED aws-access-key`), the notice on stderr naming
     `tools/scan_staged.py`. Route (a) + 2c work at all.
  2. a colleague's branch carrying the key -- committed with --no-verify,
     the colleague has no hook -- merged into master: the AUTOMATIC merge
     is refused, and by the scanner's verdict, not by a hook-error.
  3. a clean automatic merge goes through (rc=0) with the notice on
     stderr, which proves `pre-merge-commit` ran: a fast-forward runs no
     hook, so the notice is what separates "passed the scan" from "no
     scan happened".

Assertion 3 is the discriminating one. Under the old step 3 (bare wrapper
as `pre-merge-commit`) assertion 2 passes by accident -- refused is
refused, whatever the reason -- and assertion 3 fails: the clean merge is
blocked with `missing-scanner`. That red is reproducible with

    python3 case_hookspath_merge.py --merge-hook-as-shipped-wrapper

which installs `pre-merge-commit` the way step 3 used to say.

Exits 0 when all three hold, 1 otherwise, 2 if the fixture itself could
not be set up.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

# Fake AWS-style access key -- shape-valid, not a real credential. Split by
# concatenation so this fixture source carries no contiguous AWS-key-shape
# literal (fixture-source-self-clean in check.py commits every fixture
# file through the shipped hook).
VIOLATION = b"AWS_ACCESS_KEY_ID=AKIA" + b"ABCDEFGHIJKLMNOP\n"
VIOLATING_PATH = "config/deploy.env"
NOTICE = "notice privacy-hook: scanner = tools/scan_staged.py"


def leaks_path(repo, text):
    return repo in text or repo.replace("\\", "/") in text


def checkout(repo, *args):
    """A failed checkout is a broken FIXTURE, never a finding: report it
    as such (rc=2) instead of letting the merge below fail on a branch
    that does not exist and blame the hook. CI sets
    `init.defaultBranch main`, so the base branch is never assumed."""
    r = lib.git(repo, "checkout", "-q", *args)
    if r.returncode != 0:
        sys.stderr.write("FIXTURE BUG: git checkout %s failed:\n%s%s\n"
                         % (" ".join(args), r.stdout, r.stderr))
        sys.exit(2)


def main(argv):
    merge_hook = "launcher"
    if argv == ["--merge-hook-as-shipped-wrapper"]:
        merge_hook = "wrapper"
    elif argv:
        sys.stderr.write("usage: case_hookspath_merge.py "
                         "[--merge-hook-as-shipped-wrapper]\n")
        return 2

    repo = lib.make_versioned_repo(merge_hook=merge_hook)
    ok = True
    # Whatever `git init` named it -- `master` here, `main` under CI's
    # `init.defaultBranch main` -- the base branch is read, not assumed.
    base = lib.git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if not base or base == "HEAD":
        sys.stderr.write("FIXTURE BUG: could not name the base branch\n")
        return 2

    # --- 1. route (a) + 2c: a planted key on a plain commit is refused --
    lib.write_file(repo, VIOLATING_PATH, VIOLATION)
    lib.git(repo, "add", VIOLATING_PATH)
    r = lib.commit(repo, "plain commit: should be blocked")
    out = r.stdout + r.stderr
    if r.returncode == 0:
        sys.stderr.write("FIXTURE BUG: planted key was not blocked on a plain "
                         "commit under core.hooksPath (rc=0)\n%s\n" % out)
        return 2
    if "BLOCKED aws-access-key" not in out or NOTICE not in r.stderr:
        sys.stderr.write(
            "FIXTURE BUG: plain commit refused, but not by the relocated "
            "scanner through the launcher:\n%s\n" % out)
        return 2
    print("PASS: versioned .githooks/pre-commit launcher blocks the planted "
          "key through tools/scan_staged.py")
    lib.git(repo, "rm", "--cached", "-q", VIOLATING_PATH)
    os.remove(os.path.join(repo, VIOLATING_PATH))

    # The base branch must diverge from the branch point, or the merges
    # below would fast-forward and no merge commit -- hence no
    # pre-merge-commit -- would ever be created.
    lib.write_file(repo, "src/app.py", b"def main():\n    return 0\n")
    lib.git(repo, "add", "src/app.py")
    r = lib.commit(repo, "base branch moves on")
    if r.returncode != 0:
        sys.stderr.write("FIXTURE BUG: clean commit on the base branch was "
                         "refused:\n%s%s\n" % (r.stdout, r.stderr))
        return 2

    # --- 2. the colleague's leak arrives through an automatic merge -----
    checkout(repo, "-b", "colleague", base + "~1")
    lib.write_file(repo, VIOLATING_PATH, VIOLATION)
    lib.git(repo, "add", VIOLATING_PATH)
    r = lib.git(repo, "commit", "-q", "--no-verify", "-m",
                "colleague without the hook commits the key")
    if r.returncode != 0:
        sys.stderr.write("FIXTURE BUG: --no-verify commit failed:\n%s%s\n"
                         % (r.stdout, r.stderr))
        return 2
    checkout(repo, base)
    r = lib.git(repo, "merge", "--no-edit", "colleague")
    out = r.stdout + r.stderr
    if r.returncode == 0:
        sys.stderr.write(
            "FAIL: automatic merge carrying the planted key went through "
            "(rc=0) -- pre-merge-commit did not scan it\n%s\n" % out)
        ok = False
    elif "BLOCKED aws-access-key" not in out:
        sys.stderr.write(
            "FAIL: merge refused, but not by the scanner's verdict -- the "
            "pre-merge-commit hook did not reach tools/scan_staged.py:\n%s\n"
            % out)
        ok = False
    elif leaks_path(repo, out):
        sys.stderr.write("FAIL: merge refusal echoed an absolute path:\n%s\n"
                         % out)
        ok = False
    else:
        print("PASS: automatic merge carrying the key refused by "
              "pre-merge-commit with the scanner's verdict")
    r = lib.git(repo, "merge", "--abort")
    if r.returncode != 0 and ok:
        sys.stderr.write("FIXTURE BUG: could not abort the refused merge:\n"
                         "%s%s\n" % (r.stdout, r.stderr))
        return 2

    # --- 3. a clean automatic merge goes through, and the scan ran ------
    checkout(repo, "-b", "clean-branch", base + "~1")
    lib.write_file(repo, "docs/note.md", b"# notes\n\nnothing secret here\n")
    lib.git(repo, "add", "docs/note.md")
    r = lib.commit(repo, "clean branch commit")
    if r.returncode != 0:
        sys.stderr.write("FIXTURE BUG: clean branch commit was refused:\n"
                         "%s%s\n" % (r.stdout, r.stderr))
        return 2
    checkout(repo, base)
    r = lib.git(repo, "merge", "--no-edit", "clean-branch")
    out = r.stdout + r.stderr
    parents = lib.git(repo, "rev-list", "--parents", "-1", "HEAD").stdout.split()
    if r.returncode != 0 and "missing-scanner" in out:
        sys.stderr.write(
            "FAIL: a CLEAN automatic merge was refused (rc=%d) -- the "
            "pre-merge-commit hook does not reach the relocated scanner; "
            "this is the old ADOPTION step 3 (bare wrapper copied under "
            "the second name):\n%s\n" % (r.returncode, out))
        ok = False
    elif r.returncode != 0:
        sys.stderr.write(
            "FAIL: a CLEAN automatic merge was refused (rc=%d), and not by "
            "the missing-scanner path:\n%s\n" % (r.returncode, out))
        ok = False
    elif len(parents) != 3:
        sys.stderr.write(
            "FIXTURE BUG: clean merge did not create a merge commit (fast-"
            "forward?), so pre-merge-commit was never exercised: %s\n"
            % parents)
        return 2
    elif NOTICE not in r.stderr:
        sys.stderr.write(
            "FAIL: clean merge went through but pre-merge-commit left no "
            "notice on stderr -- nothing proves the scan ran:\n%s\n" % out)
        ok = False
    elif leaks_path(repo, out):
        sys.stderr.write("FAIL: merge output echoed an absolute path:\n%s\n"
                         % out)
        ok = False
    else:
        print("PASS: clean automatic merge goes through, pre-merge-commit "
              "launcher announced the relocated scanner")

    if ok:
        lib.rmtree(os.path.dirname(repo))
    else:
        sys.stderr.write("repo kept for post-mortem: %s\n" % repo)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
