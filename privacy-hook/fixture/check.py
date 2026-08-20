#!/usr/bin/env python3
"""Runnable checker for the privacy-hook fixture.

Runs the two smoke cases as subprocesses and asserts the correct
polarity:
  - case_violation.py must exit NON-ZERO (commit was blocked)
  - case_clean.py must exit ZERO (commit went through)

Then runs case_corpus.py, the table-driven corpus: one red case per KEPT
pattern, the deny-filename / literal-token / deny-regex red cases, the
sixteen measured false positives as green cases, and the
no-regeneration tripwire (payloads the removed rule used to catch, now
asserted green so re-adding a broad value rule goes red here first).
case_corpus.py must exit ZERO -- it self-reports per-case polarity and
fails loudly on any case that behaves wrong.

Exits 0 only if all three hold, 1 otherwise.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def run(script):
    r = subprocess.run([sys.executable, os.path.join(HERE, script)],
                        capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def main():
    ok = True

    rc, out, err = run("case_violation.py")
    print("--- case_violation.py (expect non-zero) -> rc=%d ---" % rc)
    print(out, end="")
    print(err, end="", file=sys.stderr)
    if rc == 0:
        print("FAIL: violating commit was not blocked", file=sys.stderr)
        ok = False
    else:
        print("PASS: violating commit was blocked (red proven)")

    rc, out, err = run("case_clean.py")
    print("--- case_clean.py (expect zero) -> rc=%d ---" % rc)
    print(out, end="")
    print(err, end="", file=sys.stderr)
    if rc != 0:
        print("FAIL: clean commit was blocked", file=sys.stderr)
        ok = False
    else:
        print("PASS: clean commit went through (green proven)")

    rc, out, err = run("case_gitlink.py")
    print("--- case_gitlink.py (expect zero) -> rc=%d ---" % rc)
    print(out, end="")
    print(err, end="", file=sys.stderr)
    if rc != 0:
        print("FAIL: gitlink case reported wrong polarity", file=sys.stderr)
        ok = False
    else:
        print("PASS: gitlink .env blocked, innocent gitlink allowed")

    rc, out, err = run("case_corpus.py")
    print("--- case_corpus.py (expect zero) -> rc=%d ---" % rc)
    print(out, end="")
    print(err, end="", file=sys.stderr)
    if rc != 0:
        print("FAIL: corpus reported at least one wrong-polarity case",
              file=sys.stderr)
        ok = False
    else:
        print("PASS: every corpus case behaved as declared")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
