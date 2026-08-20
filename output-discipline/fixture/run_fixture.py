#!/usr/bin/env python3
"""Red-green fixture runner for check_artifact.py.

Every case states its expected exit code and, for reds, the named violation
that must appear -- a guard is only worth its red, and the red must fail for
the right reason, not merely fail.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CHECKER = os.path.join(HERE, "..", "scripts", "check_artifact.py")

# (file, flags, expected exit, required substring in output or None)
# Default mode (no flag) is UNCHANGED. --budgets-advisory (CARD-03,
# 2026-08-19): structure violations still fail; budget violations only warn
# (exit 0 + WARNING line).
CASES = [
    ("plan_clean_xs.md", [], 0, None),
    ("plan_clean_m.md", [], 0, None),
    ("plan_missing_verify.md", [], 1, "missing-verify"),
    ("plan_over_budget.md", [], 1, "over-budget"),
    ("review_clean_s.md", [], 0, None),
    ("review_verdict_buried.md", [], 1, "verdict-not-first"),
    ("undeclared.md", [], 2, "no type/tier declaration"),
    ("buried_declaration.md", [], 2, "no type/tier declaration"),
    # 5th external review (2026-08-18): permissive grammar accepted all three.
    ("wrong_version_v10.md", [], 2, "no type/tier declaration"),
    ("split_declaration.md", [], 2, "no type/tier declaration"),
    ("verdict_theater_passing.md", [], 1, "missing-verdict"),
    # --budgets-advisory mode: the two behavior changes + structure locks.
    ("plan_over_budget.md", ["--budgets-advisory"], 0, "WARNING: over-budget"),
    ("plan_clean_xs.md", ["--budgets-advisory"], 0, None),
    ("review_clean_s.md", ["--budgets-advisory"], 0, None),
    ("review_verdict_buried.md", ["--budgets-advisory"], 1, "verdict-not-first"),
    ("plan_missing_verify.md", ["--budgets-advisory"], 1, "missing-verify"),
    ("verdict_theater_passing.md", ["--budgets-advisory"], 1, "missing-verdict"),
]


def main():
    failures = []
    for fname, flags, want_exit, want_text in CASES:
        proc = subprocess.run(
            [sys.executable, CHECKER] + flags + [os.path.join(HERE, fname)],
            capture_output=True, text=True,
        )
        out = proc.stdout + proc.stderr
        label = "%s%s -> exit=%d" % (fname, " " + " ".join(flags) if flags else "",
                                     proc.returncode)
        if proc.returncode != want_exit:
            failures.append("%s (expected exit %d)\n%s" % (label, want_exit, out))
            continue
        if want_text and want_text not in out:
            failures.append(
                "%s failed but NOT for the expected reason "
                "(wanted %r)\n%s" % (label, want_text, out)
            )
            continue
        print("OK  %s%s" % (label, "  [%s]" % want_text if want_text else ""))
    if failures:
        print("\nFIXTURE FAILED: %d case(s) misbehaved" % len(failures))
        for f in failures:
            print("--- " + f)
        return 1
    print("\nFIXTURE OK: clean cases green; missing-verify, over-budget and "
          "buried-verdict red for the right named reasons; undeclared "
          "artifact NOT-RUN instead of a false pass; --budgets-advisory "
          "keeps structure red and demotes over-budget to a warning.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
