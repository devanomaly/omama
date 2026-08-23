#!/usr/bin/env python3
"""Runnable checker for the privacy-hook fixture.

Runs the two smoke cases as subprocesses and asserts the correct
polarity:
  - case_violation.py must exit NON-ZERO (commit was blocked)
  - case_clean.py must exit ZERO (commit went through)

Then case_gitlink.py, case_scanner_override.py and
case_hookspath_merge.py, each self-reporting its own polarities (gitlink
named `.env` blocked / innocent gitlink allowed; the scanner reached
through PRIVACY_HOOK_SCANNER giving the default location's verdict, an
override pointing at a missing file failing closed, an honoured override
announced on stderr; ADOPTION route (a) + step 2c + step 3 composed: the
launcher under both hook names blocks a key on commit AND on automatic
merge while a clean merge goes through).

Then runs case_corpus.py, the table-driven corpus: one red case per KEPT
pattern, the deny-filename / literal-token / deny-regex red cases, the
sixteen measured false positives as green cases, and the
no-regeneration tripwire (payloads the removed rule used to catch, now
asserted green so re-adding a broad value rule goes red here first).
case_corpus.py must exit ZERO -- it self-reports per-case polarity and
fails loudly on any case that behaves wrong.

Finally, fixture-source-self-clean asserts that every fixture/*.py file,
scanned as bytes the same way the real hook would scan a staged blob,
trips none of privacy-hook's built-in credential-shape rules -- so an
adopting repo (this one included) can commit a fixture edit through its
own hook. Payloads a case plants at runtime are unchanged; only the
fixture's SOURCE representation of a credential shape is required to be
non-contiguous (built by concatenation).

Exits 0 only if all of them hold, 1 otherwise.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PIECE_DIR = os.path.dirname(HERE)
sys.path.insert(0, PIECE_DIR)
import scan_staged  # noqa: E402


def run(script):
    r = subprocess.run([sys.executable, os.path.join(HERE, script)],
                        capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def check_fixture_source_self_clean():
    """The fixture's OWN source files must pass privacy-hook's built-in
    scanner, so an adopting repo (this one included) can commit a fixture
    edit through the hook. Reads each fixture/*.py as bytes -- the same
    bytes `git show :path` would hand the real hook -- and asserts
    scan_bytes(..., builtins_only=True) reports no rule. deny_regexes and
    the token list are irrelevant here (this fixture plants no team-owned
    literal), so only the built-in credential shapes are checked; team
    config is exercised by the corpus's deny-filename / deny-token /
    deny-regex cases instead.

    A payload a case PLANTS at runtime (inside a throwaway repo under
    fixture/.tmp/) is not fixture SOURCE and is correctly out of scope --
    only the *.py files committed to this repo are scanned."""
    failures = []
    for name in sorted(os.listdir(HERE)):
        if not name.endswith(".py"):
            continue
        path = os.path.join(HERE, name)
        with open(path, "rb") as f:
            data = f.read()
        hit = scan_staged.scan_bytes(data, deny_regexes=[], tokens=[],
                                     builtins_only=True)
        if hit:
            failures.append((name, hit))
    return failures


def main():
    ok = True

    failures = check_fixture_source_self_clean()
    print("--- fixture-source-self-clean (expect no built-in rule hits) ---")
    if failures:
        for name, hit in failures:
            print("FAIL: fixture/%s matches built-in rule %r" % (name, hit),
                  file=sys.stderr)
        print("FAIL: fixture source is not committable through its own "
              "hook -- split the flagged literal(s) by concatenation",
              file=sys.stderr)
        ok = False
    else:
        print("PASS: every fixture/*.py is clean against the built-in "
              "rules (fixture is self-committable, red-green proven)")

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

    rc, out, err = run("case_scanner_override.py")
    print("--- case_scanner_override.py (expect zero) -> rc=%d ---" % rc)
    print(out, end="")
    print(err, end="", file=sys.stderr)
    if rc != 0:
        print("FAIL: scanner-location override case reported wrong behaviour",
              file=sys.stderr)
        ok = False
    else:
        print("PASS: relocated scanner blocks identically, missing override "
              "fails closed, honoured override announced on stderr")

    rc, out, err = run("case_hookspath_merge.py")
    print("--- case_hookspath_merge.py (expect zero) -> rc=%d ---" % rc)
    print(out, end="")
    print(err, end="", file=sys.stderr)
    if rc != 0:
        print("FAIL: versioned .githooks + pre-merge-commit composition case "
              "reported wrong behaviour", file=sys.stderr)
        ok = False
    else:
        print("PASS: launcher under both hook names: key blocked on commit "
              "and on merge, clean merge passes")

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
