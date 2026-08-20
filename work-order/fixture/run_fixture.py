#!/usr/bin/env python3
"""Fixture runner for validate_work_order.py (slim card schema).

Runs the validator against one clean case and twelve planted-violation
cases, asserts the validator's exit code matches expectation for each, and
prints the violation the validator named for each rejected case. The
legacy-schema fixtures live in archive/ (CARD-01, 2026-08-19).

Exit code 0  -> all cases behaved as expected (validator is correct),
                each red for EVERY named reason (regression locks).
Exit code 1  -> at least one case behaved unexpectedly (validator is broken,
                or someone weakened it).

Usage:
    py -3 run_fixture.py
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VALIDATOR = HERE.parent / "validate_work_order.py"

# (file, expected exit, label, required output substrings).
# The substrings are the REGRESSION LOCKS: a multi-violation file stays
# exit-1 even when one specific check regresses, so exit code alone proves
# polarity, not the promised reasons (4th external review, 2026-08-18).
# EVERY planted violation gets its own lock -- a single-substring lock let
# two of shape_theater's three planted guards vanish while the fixture
# stayed green (5th external review, 2026-08-18).
CASES = [
    ("valid_slim.yaml", 0, "clean case: valid slim card", []),
    ("invalid_verify_true.yaml", 1,
     "planted violation: vacuous verify -- `true`",
     ["verify='true' is vacuous"]),
    ("invalid_verify_colon.yaml", 1,
     "planted violation: vacuous verify -- `:` (shell no-op)",
     ["verify=':' is vacuous"]),
    ("invalid_verify_empty.yaml", 1,
     "planted violation: vacuous verify -- whitespace-only",
     ["empty value for required key: verify"]),
    ("invalid_verify_echo.yaml", 1,
     "planted violation: vacuous verify -- `echo done`",
     ["verify='echo done' is vacuous"]),
    ("invalid_bugfix_no_repro.yaml", 1,
     "planted violation: bugfix without repro attached",
     ["task_type=bugfix requires repro"]),
    ("invalid_repro_checkbox.yaml", 1,
     "planted violation: repro is a checkbox (true), not an attached reproduction",
     ["repro=True is not a non-empty string"]),
    ("invalid_unknown_keys.yaml", 1,
     "planted violation: unknown top-level keys ('goals' typo, 'notes' extra)",
     ["unknown top-level keys ['goals', 'notes']"]),
    ("invalid_duplicate_keys.yaml", 1,
     "planted violation: duplicate YAML key (silent last-wins override)",
     ["duplicate"]),
    ("invalid_bad_tier.yaml", 1,
     "planted violation: tier outside the closed enum S1|S2|S3",
     ["tier='S4' is not one of"]),
    ("invalid_missing_keys.yaml", 1,
     "planted violation: required keys absent (goal, done_when, verify)",
     ["missing required key: goal",
      "missing required key: done_when",
      "missing required key: verify"]),
    ("invalid_null_values.yaml", 1,
     "planted violation: all keys present, all values null (containment theater)",
     ["empty value for required key: goal",
      "empty value for required key: verify"]),
    ("invalid_list_task_type.yaml", 1,
     "planted violation: task_type is a list (must be VIOLATION, never a traceback)",
     ["task_type"]),
]


def run_case(filename, expected_exit, label, want_texts):
    path = HERE / filename
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(path)],
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    ok = result.returncode == expected_exit
    # A traceback is never an acceptable red: fail-closed means a NAMED
    # violation, not a crash that happens to be nonzero.
    if ok and expected_exit != 0 and "Traceback (most recent call last)" in output:
        ok = False
        label += " [red via TRACEBACK, not a named violation]"
    if ok:
        missing = [t for t in want_texts if t not in output]
        if missing:
            ok = False
            label += f" [red for the WRONG reason(s): missing {missing!r}]"
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {label} (exit={result.returncode}, expected={expected_exit})")
    if result.stdout.strip():
        print(f"    stdout: {result.stdout.strip()}")
    if result.stderr.strip():
        for line in result.stderr.strip().splitlines():
            print(f"    {line}")
    return ok


def main():
    all_ok = True
    for filename, expected_exit, label, want_texts in CASES:
        if not run_case(filename, expected_exit, label, want_texts):
            all_ok = False
    print()
    if all_ok:
        print("FIXTURE RESULT: all cases behaved as expected")
        return 0
    else:
        print("FIXTURE RESULT: at least one case did NOT behave as expected")
        return 1


if __name__ == "__main__":
    sys.exit(main())
