#!/usr/bin/env python3
"""Fixture runner for ../check_pr_base.py.

Runs the checker against one clean base name, two planted violations, and the
not-runnable (no argument) case, asserts the exit code and message match, so a
future edit can't silently widen or narrow what counts as a valid base.

Exit code 0 -> all cases behaved as expected (checker is correct).
Exit code 1 -> at least one case behaved unexpectedly (checker is broken, or
               someone weakened it).

Usage:
    python3 run_fixture.py
"""
import subprocess
import sys
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
]


def run(argv):
    return subprocess.run([sys.executable, str(CHECKER), *argv],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=30)


def main():
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
    print()
    if failures:
        print(f"run_fixture: {len(failures)}/{len(CASES)} case(s) FAILED")
        return 1
    print(f"run_fixture: all {len(CASES)} cases behaved as expected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
