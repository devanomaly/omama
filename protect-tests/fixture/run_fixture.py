#!/usr/bin/env python3
"""
Fixture runner for the vendored protect-tests.js hook.

Drives the hook script DIRECTLY (no Claude Code harness involved) by piping
a crafted PreToolUse hook-protocol JSON payload on stdin, exactly as the
real Claude Code harness does, then inspects the hook's JSON stdout.

Contract of protect-tests.js (verified by manual invocation, see README):
  - The process ALWAYS exits 0. It never uses a non-zero process exit code
    to signal a block.
  - Blocking is communicated purely through stdout JSON:
      {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                               "permissionDecision": "deny", ...}}
    A non-blocked call prints "{}".

Because the hook's OWN exit code is always 0, this runner does the
translation the task requires: it inspects hookSpecificOutput.permissionDecision
and turns that into the runner's own exit code, per the requested convention:
  - violation case correctly blocked  -> exit 1 (non-zero: the action did NOT
    proceed, matching how a blocked tool call behaves for the agent)
  - clean case correctly allowed      -> exit 0 (the action proceeded)
  - hook behaves OTHER than expected  -> exit 2 (fixture/hook is broken;
    still non-zero, distinguishable via stderr text)

Usage:
  py -3 run_fixture.py violation   # expects the delete-test case to be denied
  py -3 run_fixture.py skip        # expects the skip-marker case to be denied
  py -3 run_fixture.py clean       # expects the benign edit to be allowed
  py -3 run_fixture.py all         # runs all three, prints a summary,
                                    # exits 0 only if every case matched
                                    # expectations (else exits 2)
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENDOR_JS = HERE.parent / "vendor" / "protect-tests.js"

CASES = {
    "violation": (HERE / "case-violation.json", True),
    "skip": (HERE / "case-violation-skip.json", True),
    "clean": (HERE / "case-clean.json", False),
}


def run_case(name):
    path, expect_blocked = CASES[name]
    payload = path.read_text(encoding="utf-8")

    proc = subprocess.run(
        ["node", str(VENDOR_JS)],
        input=payload,
        capture_output=True,
        text=True,
    )

    if proc.returncode != 0:
        print(f"[{name}] UNEXPECTED: node process itself exited {proc.returncode}", file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        return None

    try:
        out = json.loads(proc.stdout.strip() or "{}")
    except json.JSONDecodeError:
        print(f"[{name}] UNEXPECTED: hook did not print valid JSON: {proc.stdout!r}", file=sys.stderr)
        return None

    decision = out.get("hookSpecificOutput", {}).get("permissionDecision")
    blocked = decision == "deny"

    ok = blocked == expect_blocked
    label = "BLOCKED" if blocked else "ALLOWED"
    expected_label = "BLOCKED" if expect_blocked else "ALLOWED"
    status = "OK" if ok else "MISMATCH"

    print(f"[{name}] hook decision = {label} (expected {expected_label}) -> {status}")
    if blocked:
        reason = out["hookSpecificOutput"].get("permissionDecisionReason", "")
        print(f"         reason: {reason}")

    return ok


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("violation", "skip", "clean", "all"):
        print(__doc__)
        sys.exit(2)

    mode = sys.argv[1]

    if mode == "all":
        results = {name: run_case(name) for name in CASES}
        if all(results.values()):
            print("\nALL CASES MATCHED EXPECTATIONS")
            sys.exit(0)
        print("\nAT LEAST ONE CASE DID NOT MATCH EXPECTATIONS", file=sys.stderr)
        sys.exit(2)

    ok = run_case(mode)
    if ok is None:
        sys.exit(2)  # fixture/hook infra broke

    if mode == "clean":
        sys.exit(0 if ok else 2)
    else:  # violation | skip
        # Correct behavior (blocked) is reported as non-zero, per spec.
        sys.exit(1 if ok else 2)


if __name__ == "__main__":
    main()
