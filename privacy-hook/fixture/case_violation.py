#!/usr/bin/env python3
"""Planted-violation case.

Builds a temp repo with the hook installed, stages a file containing a
fake AWS-shaped access key AND a file containing the deny-listed token
from privacy-tokens.txt, then attempts a commit.

Exit code mirrors `git commit`'s own exit code: this script exits
NON-ZERO when the commit is (correctly) blocked, so `python3
case_violation.py` failing IS the red proof the FIXTURE spec asks for.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402


def main():
    repo = lib.make_repo()

    # Fake AWS-style access key -- shape-valid, not a real credential. Split
    # by concatenation so this fixture source itself does not carry a
    # contiguous AWS-key-shape literal (privacy-hook scans its own fixture
    # source too; see fixture-source-self-clean in check.py).
    lib.write_file(repo, "config/deploy.env",
                    b"AWS_ACCESS_KEY_ID=AKIA" + b"ABCDEFGHIJKLMNOP\n")
    # Deny-listed literal token from privacy-tokens.txt -- the SHIPPED example
    # token, split for the same reason (check.py commits this file through
    # the hook with the shipped config, team layers included).
    lib.write_file(repo, "notes/internal.md",
                    b"reference: EXAMPLE-DENY-" + b"TOKEN in the ticket\n")

    r = lib.attempt_commit(repo, "should be blocked")
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)

    if r.returncode == 0:
        sys.stderr.write(
            "FIXTURE BUG: violating commit was NOT blocked (returncode 0)\n")

    # Propagate git commit's own exit code untouched. Masking it here
    # would hide a broken/neutered hook from check.py -- the whole point
    # of this script's exit code IS the signal.
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
