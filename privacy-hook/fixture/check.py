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

Before any of those, fixture-source-self-clean: the fixture's OWN source files must
commit through the hook AS SHIPPED. Every regular file in fixture/ is
copied into a throwaway repo built by lib.make_repo (shipped wrapper,
shipped privacy-deny.json + privacy-tokens.txt, scanner at the root),
staged, and committed for real; `git commit` must exit 0. This is what
lets an adopting repo (this one included) commit a fixture edit through
its own hook. Payloads a case plants at runtime are unchanged; only the
fixture's SOURCE spelling of anything the shipped config flags -- the
built-in credential shapes AND the example team rules (deny_regexes,
tokens_file) -- is required to be non-contiguous (built by
concatenation). Scanning the source in-process with builtins_only would
NOT prove this: the shipped config's team layers block too (red-green
proven, see EVIDENCE.md).

Exits 0 only if all of them hold, 1 otherwise.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lib  # noqa: E402


def run(script):
    r = subprocess.run([sys.executable, os.path.join(HERE, script)],
                        capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def check_fixture_source_self_clean():
    """Stage every regular file in fixture/ (the files this repo commits;
    .tmp/ and __pycache__/ are not source) inside a throwaway repo with
    the hook installed exactly as ADOPTION step 1/2 installs it -- the
    SHIPPED privacy-deny.json and privacy-tokens.txt included -- and make
    a real `git commit`. The verdict is git's own exit code, and the
    BLOCKED lines are the hook's own, so what fails here is exactly what
    would fail for a developer committing a fixture edit through the
    hook: built-in credential shapes AND the example team rules.

    This is a WORKTREE-source check: the bytes staged in the scratch
    repo are the bytes on disk here, not this repo's index. A partially
    staged edit is therefore judged by its working-tree content; the
    real hook in an adopting repo judges the staged blob. Both agree
    whenever the file on disk is what gets committed, which is the case
    CI and a plain `git add` produce.

    A payload a case PLANTS at runtime (inside a throwaway repo under
    fixture/.tmp/) is not fixture SOURCE and is correctly out of scope --
    only the files committed to this repo are staged."""
    repo = lib.make_repo()
    staged = []
    for name in sorted(os.listdir(HERE)):
        src = os.path.join(HERE, name)
        if not os.path.isfile(src):
            continue
        with open(src, "rb") as f:
            lib.write_file(repo, "fixture/" + name, f.read())
        staged.append(name)
    lib.git(repo, "add", "fixture")
    r = lib.git(repo, "commit", "-q", "-m", "fixture source through the shipped hook")
    output = r.stdout + r.stderr
    if r.returncode == 0:
        if not lib.rmtree(os.path.dirname(repo)):
            print("WARN: scratch tree not removed: fixture/.tmp/%s"
                  % os.path.basename(os.path.dirname(repo)), file=sys.stderr)
    return r.returncode, output, staged


def main():
    ok = True

    rc, out, staged = check_fixture_source_self_clean()
    print("--- fixture-source-self-clean: %d files committed through the "
          "shipped hook config (expect zero) -> rc=%d ---" % (len(staged), rc))
    print(out, end="")
    if rc != 0:
        print("FAIL: fixture source is not committable through its own hook "
              "as shipped -- split the flagged literal(s) by concatenation "
              "(built-in shapes and the example team rules alike)",
              file=sys.stderr)
        ok = False
    else:
        print("PASS: every fixture/ source file commits through the shipped "
              "hook (fixture is self-committable, red-green proven)")

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
