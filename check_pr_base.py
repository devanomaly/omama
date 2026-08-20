#!/usr/bin/env python3
"""check_pr_base.py -- a PR must branch off master's tip, not another PR branch.

Why this exists: a branch cut from an unmerged sibling branch (rather than from
master) silently drags that sibling's commits into the diff. If the sibling
merges first, no harm; if this PR merges first, the sibling's unreviewed commits
land on master as a side effect of an unrelated PR. Nothing in a normal review
surfaces this -- GitHub's diff view already resolves against the merge-base, so
the PR can look clean while the branch's ancestry is not what "branch off
master" promised.

This script answers exactly one question: does this PR's base ref name equal
`master`? It does not (cannot, from a single checkout) verify that the branch's
first commit was cut from master's tip at creation time -- that fact is not
recoverable after the fact if master has since moved. See "What it does NOT
catch" in the CONTRIBUTING.md section this backs.

Usage:  python3 check_pr_base.py <base-ref-name>
        (in CI: python3 check_pr_base.py "$GITHUB_BASE_REF")

Exit 0 -- OK: base is master.
Exit 1 -- VIOLATION: base is some other ref, named in the message.
Exit 2 -- not runnable: no argument given, or the argument is empty (a CI
          misconfiguration -- e.g. running this outside a pull_request event --
          is a coverage hole, not a silent pass).
"""
import sys

REQUIRED_BASE = "master"


def main(argv):
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


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
