#!/usr/bin/env python3
"""Fixture runner for check_starter.py.

Runs the checker against a clean (adopted) case, a planted-violation case,
and the raw shipped template, asserts the checker's exit code matches
expectation for each, and prints the violations named for each rejected
case.

The third case is not a bug fixture -- it documents intended behavior:
CLAUDE.starter.md itself still carries its header comment and its
<ADJUST: ...> placeholders (it has not been adopted by any repo), so the
checker is EXPECTED to reject it with leftover-placeholder findings. If
this case ever starts passing, the leftover-placeholder check regressed.

Exit code 0  -> all cases behaved as expected (checker is correct).
Exit code 1  -> at least one case behaved unexpectedly (checker is broken,
                or someone weakened it).

Usage:
    python3 run_fixture.py
"""
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHECKER = HERE.parent / "check_starter.py"

# (path, expected exit, label, extra_args, required output substring or None).
# The substring is the REGRESSION LOCK: without it, a case with several
# violations stays exit-1 even when the one check it exists to protect
# regresses and a different check fires instead (4th external review,
# 2026-08-18) -- a red is worth its reason, not merely its nonzero exit.
CASES = [
    ("clean/CLAUDE.md", 0, "clean case: adopted starter file", [], None),
    (
        "violating/CLAUDE.md",
        1,
        "planted violation: untagged rule + doctrine vocabulary",
        [],
        "[untagged-rule]",
    ),
    (
        "../CLAUDE.starter.md",
        1,
        "raw shipped template (not yet adopted by any repo): still carries "
        "the header comment and <ADJUST: ...> placeholders on purpose",
        [],
        "[leftover-placeholder]",
    ),
    # Regression cases for the 2026-08-18 3rd/4th-review bypasses:
    (
        "violating_colon/CLAUDE.md",
        1,
        "planted violation: governed heading with trailing ':' must still "
        "be governed (punctuation opt-out bypass)",
        [],
        "[untagged-rule]",
    ),
    (
        "violating_empty/CLAUDE.md",
        1,
        "planted violation: no governed section at all (near-empty file "
        "must not pass silently)",
        [],
        "[missing-governed-section]",
    ),
    (
        "violating_empty_governed/CLAUDE.md",
        1,
        "planted violation: governed heading present but zero rule bullets "
        "(prose is not governed)",
        [],
        "[empty-governed-section]",
    ),
    (
        "violating_persection/CLAUDE.md",
        1,
        "planted violation: one valid governed section must not satisfy "
        "governance for a sibling governed section with zero rule bullets "
        "(per-section accounting, 5th external review)",
        [],
        "[empty-governed-section]",
    ),
    (
        "violating_renamed/CLAUDE.md",
        1,
        "planted violation: renamed governed heading must surface as a "
        "missing governed section, never silently ungovern its rules "
        "(analysis audit, 2026-08-18)",
        [],
        "[missing-governed-section]",
    ),
    (
        "violating_numbered/CLAUDE.md",
        1,
        "planted violation: numbered/'*' rules inside a governed section "
        "must be visible to the tag check (analysis audit, 2026-08-18)",
        [],
        "[untagged-rule]",
    ),
    (
        "violating_vocab_mask/CLAUDE.md",
        1,
        "planted violation: allowlisted token must not mask a forbidden "
        "one on the same line (--allow-vocab=P2, line has 'manifesto'); "
        "also locks the EN doctrine lexicon ('doctrine'/'pillar') catching "
        "a planted English doctrine sentence, not just the PT terms",
        ["--allow-vocab=P2"],
        "matched 'doctrine'",
    ),
    (
        "clean/CLAUDE.md",
        2,
        "usage refusal: --allow-vocab=pilar is never exemptable and must "
        "be refused loudly, not honored",
        ["--allow-vocab=pilar"],
        "cannot exempt",
    ),
    (
        "violating_stale_schema/CLAUDE.md",
        1,
        "planted violation: stale piece-02 field names (this file is a "
        "BYTE COPY of the clean case as it stood before this change -- it "
        "was green then and is red now, and only for the new reason)",
        [],
        "[stale-schema]",
    ),
    (
        "violating_internal_tag/CLAUDE.md",
        1,
        "planted violation: [05] and [06] name internal pieces this "
        "toolkit does not ship and stay OUT of the closed set, even now "
        "that [10] is in it",
        [],
        "not in the closed set",
    ),
    (
        "pointer_only/CLAUDE.md",
        1,
        "PIN, not a bug: a CLAUDE.md whose whole body points at another "
        "apex file (AGENTS.md) answers FAIL with one finding per governed "
        "section -- what ADOPTION.md's 'apex file is not CLAUDE.md' "
        "section describes; measured, not asserted",
        [],
        "[missing-governed-section]",
    ),
]


def run_case(rel_path, expected_exit, label, extra_args=(), want_text=None):
    path = HERE / rel_path
    result = subprocess.run(
        [sys.executable, str(CHECKER), str(path), *extra_args],
        capture_output=True,
        text=True,
    )
    ok = result.returncode == expected_exit
    if ok and want_text and want_text not in (result.stdout + result.stderr):
        ok = False
        label += f" [red for the WRONG reason: missing {want_text!r}]"
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {label} (exit={result.returncode}, expected={expected_exit})")
    if result.stdout.strip():
        for line in result.stdout.strip().splitlines():
            print(f"    {line}")
    if result.stderr.strip():
        for line in result.stderr.strip().splitlines():
            print(f"    {line}")
    return ok


def check_clean_pairs_gate_with_antifabrication():
    """Content invariant of the CLEAN example (analysis audit, 2026-08-18,
    found independently by two audits): the [02] reproduction gate is only
    as strong as the anti-fabrication rule that forbids inventing its
    input -- a fabricated reproduction is indistinguishable in artifact
    and exit code, so nothing mechanical ever fires. If clean/CLAUDE.md
    keeps the [02] gate, it must also carry the 'Never fabricate'
    dictation rule."""
    text = (HERE / "clean" / "CLAUDE.md").read_text(encoding="utf-8")
    if "[02]" in text and not re.search(r"[Nn]ever fabricate", text):
        print("[FAIL] clean/CLAUDE.md keeps the [02] reproduction gate but "
              "drops the anti-fabrication rule ('Never fabricate ...') that "
              "protects it")
        return False
    print("[PASS] clean/CLAUDE.md pairs the [02] gate with the "
          "anti-fabrication rule")
    return True


def main():
    all_ok = True
    for rel_path, expected_exit, label, extra_args, want_text in CASES:
        if not run_case(rel_path, expected_exit, label, extra_args, want_text):
            all_ok = False
        print()
    if not check_clean_pairs_gate_with_antifabrication():
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
