#!/usr/bin/env python3
"""Fixture runner for validate_work_order.py (slim card schema).

Runs the validator against eleven clean cases and thirty-six
planted-violation cases, asserts the validator's exit code matches
expectation for each, and prints the violation the validator named for each
rejected case. The case count itself is a lock (EXPECTED_CASE_COUNT): a
case that silently disappears is a weakened validator, so the runner goes
red on the count as well as on any case.

Twenty-four of the planted cases are the segment rule (issue #18): the
deny-list applies to the first word of EVERY segment -- after `||`, `;`,
`&&`, `|`, `|&`, a newline, a `&` glued to the next word, and inside quotes
-- and a backgrounded command (a bare `&` at a command boundary) is
rejected. Ten of the clean cases pin what that rule must NOT reject. The
rule reads `verify` as a POSIX/bash command line; the receipt gate runs it
with `Popen(shell=True)` (/bin/sh on POSIX, cmd.exe on Windows).

The legacy-schema fixtures live in archive/ (CARD-01, 2026-08-19).

Exit code 0  -> all cases behaved as expected (validator is correct),
                each red for EVERY named reason (regression locks).
Exit code 1  -> at least one case behaved unexpectedly (validator is broken,
                or someone weakened it).

Usage:
    python3 run_fixture.py
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
# The count is the anti-weakening lock: a case removed without touching this
# number is a red run, not a quieter green one.
EXPECTED_CASE_COUNT = 47

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

    # -- vacuity per SEGMENT, not per command (issue #18) ----------------
    # The deny-list is applied to the first word of EVERY operator-separated
    # segment, and a bare `&` at a command boundary is rejected. Each case
    # below is red for its own lock: a mutation that drops one element of
    # the rule turns at least one of them green.
    ("invalid_verify_or_true.yaml", 1,
     "planted violation: vacuous segment after `||` -- `pytest -q || true`",
     ["verify='pytest -q || true' is vacuous"]),
    ("invalid_verify_semi_true.yaml", 1,
     "planted violation: vacuous segment after `;` -- `pytest -q; true`",
     ["verify='pytest -q; true' is vacuous"]),
    ("invalid_verify_and_echo.yaml", 1,
     "planted violation: vacuous segment after `&&` -- `cd /tmp && echo ok`",
     ["verify='cd /tmp && echo ok' is vacuous"]),
    ("invalid_verify_pipe_true.yaml", 1,
     "planted violation: vacuous segment after `|` -- `pytest -q | true`",
     ["verify='pytest -q | true' is vacuous"]),
    ("invalid_verify_pipeamp_true.yaml", 1,
     "planted violation: vacuous segment after `|&` -- `pytest -q |& true`",
     ["verify='pytest -q |& true' is vacuous"]),
    ("invalid_verify_newline_true.yaml", 1,
     "planted violation: vacuous segment after a NEWLINE (block scalar)",
     ["verify='pytest -q\\ntrue' is vacuous"]),
    ("invalid_verify_group_parens.yaml", 1,
     "planted violation: vacuous segment inside `( ... )` -- `(pytest -q || true)`",
     ["verify='(pytest -q || true)' is vacuous"]),
    ("invalid_verify_leading_paren.yaml", 1,
     "planted violation: vacuous segment behind a leading `(` -- `|| (true)`",
     ["verify='pytest -q || (true)' is vacuous"]),
    ("invalid_verify_brace_group.yaml", 1,
     "planted violation: vacuous segment inside `{ ...; }` -- `|| { true; }`",
     ["verify='pytest -q || { true; }' is vacuous"]),
    ("invalid_verify_quoted_true.yaml", 1,
     "planted violation: vacuous segment spelled with quotes -- `'tr'\"ue\"`",
     ["verify='pytest -q || \\'tr\\'\"ue\"' is vacuous"]),
    ("invalid_verify_backslash_true.yaml", 1,
     "planted violation: vacuous segment spelled with a backslash -- `\\true`",
     ["verify='pytest -q || \\\\true' is vacuous"]),
    ("invalid_verify_line_continuation.yaml", 1,
     "planted violation: vacuous segment split by a backslash-newline",
     ["verify='pytest -q || tr\\\\\\nue' is vacuous"]),
    ("invalid_verify_background.yaml", 1,
     "planted violation: backgrounded verify -- trailing `&` discards the status",
     ["verify='pytest -q &' is vacuous"]),
    ("invalid_verify_background_paren.yaml", 1,
     "planted violation: backgrounded verify at a `&)` boundary",
     ["verify='(pytest -q &)' is vacuous"]),
    ("invalid_verify_glued_amp.yaml", 1,
     "planted violation: bare `&` glued to a no-op -- `pytest -q&echo ok` "
     "(a glued `&` is read as one more separator)",
     ["verify='pytest -q&echo ok' is vacuous"]),
    ("invalid_verify_redir_word_true.yaml", 1,
     "planted violation: vacuous segment behind a glued `>/dev/null`",
     ["verify='pytest -q || >/dev/null true' is vacuous"]),
    ("invalid_verify_bare_redir_ops.yaml", 1,
     "planted violation: vacuous segment behind all seven bare redirection "
     "operators (the segment is named too, so a bare-`&` misfire on the "
     "spaced `>& 2` / `<& 0` / `&> /dev/null` reads as red for the WRONG reason)",
     ["verify='pytest -q || > /dev/null >> /dev/null < /dev/null "
      "2> /dev/null >& 2 <& 0 &> /dev/null true' is vacuous",
      "segment '> /dev/null >> /dev/null < /dev/null 2> /dev/null "
      ">& 2 <& 0 &> /dev/null true'"]),
    ("invalid_verify_true_redirect.yaml", 1,
     "planted violation: vacuous segment glued to its redirection -- `true>/dev/null`",
     ["verify='pytest -q || true>/dev/null' is vacuous"]),
    ("invalid_verify_redir_word_shapes.yaml", 1,
     "planted violation: vacuous segment behind `2>&1 &>/dev/null </dev/null`",
     ["verify='pytest -q || 2>&1 &>/dev/null </dev/null true' is vacuous"]),
    ("invalid_verify_assignments.yaml", 1,
     "planted violation: vacuous segment behind `X=1 Y+=2` assignments",
     ["verify='pytest -q || X=1 Y+=2 true' is vacuous"]),
    ("invalid_verify_then_true.yaml", 1,
     "planted violation: vacuous segment behind `then`",
     ["verify='if pytest -q; then true; fi' is vacuous"]),
    ("invalid_verify_else_true.yaml", 1,
     "planted violation: vacuous segment behind `else`",
     ["verify='if pytest -q; then exit 0; else true; fi' is vacuous"]),
    ("invalid_verify_do_colon.yaml", 1,
     "planted violation: vacuous segment behind `do` -- `while false; do :; done`",
     ["verify='while false; do :; done' is vacuous"]),
    ("invalid_verify_time_true.yaml", 1,
     "planted violation: vacuous segment behind `time` -- `|| time true`",
     ["verify='pytest -q || time true' is vacuous"]),

    # -- clean cases the segment rule must NOT reject --------------------
    ("valid_and_chain.yaml", 0,
     "clean case: two real commands joined by `&&`", []),
    ("valid_quoted_semicolon_body.yaml", 0,
     "clean case: quoted one-liner body carrying `;` and an inner assignment",
     []),
    ("valid_block_scalar_chain.yaml", 0,
     "clean case: block scalar -- operator-then-newline and trailing newline",
     []),
    ("valid_trailing_semicolon.yaml", 0,
     "clean case: trailing `;` leaves an empty segment, not a violation", []),
    ("valid_or_real_command.yaml", 0,
     "clean case: a real command after `||`", []),
    ("valid_pipeamp_pipeline.yaml", 0,
     "clean case: real `|&` pipeline (`|&` is not a boundary `&`)", []),
    ("valid_amp_in_url.yaml", 0,
     "clean case: `&` inside a quoted URL is inside a word", []),
    ("valid_amp_in_pattern.yaml", 0,
     "clean case: `&` inside a quoted pattern is inside a word", []),
    ("valid_amp_entity.yaml", 0,
     "clean case: HTML entity `&#39;` is not a command boundary", []),
    ("valid_bang_true.yaml", 0,
     "clean case: `!` is not skipped -- `pytest -q || ! true` can fail", []),
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
    if len(CASES) != EXPECTED_CASE_COUNT:
        print(f"[FAIL] case count is {len(CASES)}, expected "
              f"{EXPECTED_CASE_COUNT} (a case vanished or the lock was not "
              "updated with the change that added one)")
        all_ok = False
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
