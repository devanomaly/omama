#!/usr/bin/env python3
"""check_pr_base.py -- a PR must branch off master's tip, not another PR branch.

Why this exists: a branch cut from an unmerged sibling branch (rather than from
master) silently drags that sibling's commits into the diff. If the sibling
merges first, no harm; if this PR merges first, the sibling's unreviewed commits
land on master as a side effect of an unrelated PR. Nothing in a normal review
surfaces this -- GitHub's diff view already resolves against the merge-base, so
the PR can look clean while the branch's ancestry is not what "branch off
master" promised.

Two modes, two different questions:

  check_pr_base.py <base-ref-name>
      Does this PR's declared base ref name equal `master`? Cheap, no git
      needed, but only checks what the PR claims, not what actually happened.

  check_pr_base.py --ancestry <head-sha> <head-ref-name>
      Of the commits unique to this PR's head (origin/master..<head-sha>), is
      any of them also reachable from another unmerged remote branch? If so,
      this branch was cut from that sibling, not from master's tip, regardless
      of what the base ref claims. This DOES partially recover the cut-point
      fact the base-ref check cannot see -- but only while the sibling stays
      unmerged (once it merges, its commits are indistinguishable from
      legitimate master history) and only up to ancestry's own symmetry (two
      unmerged branches sharing commits look the same from either side; the
      check names the overlap, a human decides which one is the fork). See
      "What it does NOT catch" in the CONTRIBUTING.md section this backs.

Usage:  python3 check_pr_base.py <base-ref-name>
        python3 check_pr_base.py --ancestry <head-sha> <head-ref-name>
        (in CI: python3 check_pr_base.py "$GITHUB_BASE_REF"
                python3 check_pr_base.py --ancestry "<pr-head-sha>" "<pr-head-ref>")

Exit 0 -- OK: base is master (mode 1) / no unique commit is reachable from
          another remote branch (mode 2).
Exit 1 -- VIOLATION: base is some other ref (mode 1) / a unique commit is also
          reachable from a named sibling branch (mode 2). Named either way.
Exit 2 -- not runnable: missing/empty argument; and for --ancestry also a
          shallow repository, a missing origin/master, or not-a-git-repo at
          all -- a CI misconfiguration is a coverage hole, not a silent pass.
"""
import subprocess
import sys

REQUIRED_BASE = "master"


def _run_git(args):
    proc = subprocess.run(["git", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def check_base_ref(argv):
    if len(argv) != 1 or not argv[0].strip():
        print("usage: check_pr_base.py <base-ref-name>", file=sys.stderr)
        print("VIOLATION: no base ref name given -- not runnable here",
              file=sys.stderr)
        return 2
    base = argv[0].strip()
    if base != REQUIRED_BASE:
        print(f"VIOLATION: PR base is '{base}', must be '{REQUIRED_BASE}' "
              f"-- branch off {REQUIRED_BASE}'s tip, not another PR branch",
              file=sys.stderr)
        return 1
    print(f"OK: PR base is '{REQUIRED_BASE}'")
    return 0


def check_ancestry(argv):
    if len(argv) != 2 or not argv[0].strip() or not argv[1].strip():
        print("usage: check_pr_base.py --ancestry <head-sha> <head-ref-name>",
              file=sys.stderr)
        print("VIOLATION: no head SHA / head ref name given -- not runnable "
              "here", file=sys.stderr)
        return 2

    head_sha, head_ref = argv[0].strip(), argv[1].strip()

    rc, _out, err = _run_git(["rev-parse", "--is-inside-work-tree"])
    if rc != 0:
        print(f"VIOLATION: not a git repository here -- not runnable "
              f"({err or 'git rev-parse failed'})", file=sys.stderr)
        return 2

    rc, out, err = _run_git(["rev-parse", "--is-shallow-repository"])
    if rc != 0 or out != "false":
        print("VIOLATION: shallow repository -- ancestry needs full history "
              "to compute origin/master..<head>; a shallow checkout would "
              "silently hide the very commits this check reads (use "
              "fetch-depth: 0), not runnable here", file=sys.stderr)
        return 2

    rc, _out, err = _run_git(["rev-parse", "--verify", "origin/master"])
    if rc != 0:
        print(f"VIOLATION: 'origin/master' does not resolve -- not runnable "
              f"here ({err or 'ref not found'})", file=sys.stderr)
        return 2

    rc, out, err = _run_git(["rev-list", f"origin/master..{head_sha}"])
    if rc != 0:
        print(f"VIOLATION: could not compute origin/master..{head_sha} -- "
              f"not runnable here ({err or 'git rev-list failed'})",
              file=sys.stderr)
        return 2
    unique = set(out.splitlines()) if out else set()

    if not unique:
        print(f"OK: no commits unique to {head_sha} relative to "
              f"{REQUIRED_BASE} (already merged, or nothing added since "
              f"{REQUIRED_BASE}'s tip)")
        return 0

    rc, out, err = _run_git(
        ["for-each-ref", "--format=%(refname)", "refs/remotes/origin/"])
    if rc != 0:
        print(f"VIOLATION: could not list remote branches -- not runnable "
              f"here ({err or 'git for-each-ref failed'})", file=sys.stderr)
        return 2

    excluded = {"refs/remotes/origin/HEAD", "refs/remotes/origin/master",
                f"refs/remotes/origin/{head_ref}"}
    candidates = sorted(ref for ref in out.splitlines()
                        if ref and ref not in excluded)

    for ref in candidates:
        rc, branch_out, err = _run_git(["rev-list", f"origin/master..{ref}"])
        if rc != 0:
            print(f"VIOLATION: could not compute origin/master..{ref} -- "
                  f"not runnable here ({err or 'git rev-list failed'})",
                  file=sys.stderr)
            return 2
        branch_unique = set(branch_out.splitlines()) if branch_out else set()
        shared = sorted(unique & branch_unique)
        if shared:
            branch_name = ref[len("refs/remotes/origin/"):]
            shared_short = ", ".join(s[:7] for s in shared)
            print(f"VIOLATION: commit(s) {shared_short} unique to this PR's "
                  f"head are also reachable from '{branch_name}' -- this "
                  f"branch looks like it was cut from '{branch_name}', not "
                  f"{REQUIRED_BASE}'s tip (if '{branch_name}' is itself an "
                  f"open, unmerged PR, ancestry is symmetric here -- a human "
                  f"must decide which branch is the actual fork)",
                  file=sys.stderr)
            return 1

    print(f"OK: {len(unique)} commit(s) unique to {head_sha} are reachable "
          f"from no other remote branch")
    return 0


def main(argv):
    if argv and argv[0] == "--ancestry":
        return check_ancestry(argv[1:])
    return check_base_ref(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
