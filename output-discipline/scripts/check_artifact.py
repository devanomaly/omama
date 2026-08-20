#!/usr/bin/env python3
"""check_artifact.py -- deterministic structure/budget checker for
output-discipline PLAN and REVIEW artifacts.

Exit codes (contract borrowed from the gating toolkit's validator skeleton):
  0  VERIFIED  - artifact declares its type/tier and satisfies every rule
  1  FAILED    - one or more named violations
  2  NOT-RUN   - could not evaluate (missing file, undecodable bytes, no
                 type/tier declaration). A coverage failure is NOT-RUN,
                 never a pass: a checker that could not look at the
                 artifact has no business reporting it clean.

Usage:  py -3 check_artifact.py [--budgets-advisory] <artifact.md>
Prints one JSON summary line plus a human-readable verdict line.

--budgets-advisory (CARD-03, 2026-08-19: structure mandatory, budgets
advisory -- panel 5/5 kept structure, 4/5 killed line budgets): STRUCTURE
violations (missing/buried verdict, missing sections, missing done-when/
verify) still FAIL exactly as without the flag; budget (line-count)
violations are demoted to a "WARNING: over-budget..." line, exit 0, and a
"warnings" list in the JSON summary. Without the flag, behavior is
byte-for-byte unchanged (budgets still fail).
"""
import json
import re
import sys

BUDGETS = {"XS": 5, "S": 15, "M": 40, "L": None}

# v1 must be EXACTLY v1 -- (?![0-9.]) rejects v10/v1.1, which the old
# separator class silently absorbed; and the separator excludes <> so the
# declaration cannot span two adjacent comments ("--> <!--" is all
# non-alphabetic) -- both confirmed bypasses, 5th external review,
# 2026-08-18.
DECL_RE = re.compile(
    r"<!--\s*(plan|review)\s+v1(?![0-9.])[^a-zA-Z0-9<>]*tier:\s*(XS|S|M|L)\s*-->",
    re.IGNORECASE,
)
ONELINER_RE = re.compile(r"^\s*(Plan|Review)\s*\(\s*(XS)\s*\)\s*:", re.IGNORECASE)
# Trailing \b: without it "PASS" matched inside "PASSING" (same review).
VERDICT_RE = re.compile(
    r"\bVerdict:\*{0,2}\s*(PASS-with-issues|PASS|BLOCK)\b", re.IGNORECASE
)


class NotRun(Exception):
    def __init__(self, reason):
        super(NotRun, self).__init__(reason)
        self.reason = reason


def content_lines(text):
    """Non-empty lines with pure HTML-comment lines removed (multi-line
    comments included) -- comments are template guidance, not output."""
    no_comments = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    return [ln for ln in no_comments.splitlines() if ln.strip()]


def detect(text):
    # The declaration must live NEAR THE TOP: within the first 5 non-empty
    # raw lines. Searching the whole file let an uncapped (L) artifact bury
    # the declaration under arbitrary preface (external review, 2026-08-18)
    # -- position is part of the contract, not decoration.
    head = "\n".join([ln for ln in text.splitlines() if ln.strip()][:5])
    m = DECL_RE.search(head)
    if m:
        return m.group(1).lower(), m.group(2).upper()
    for ln in text.splitlines():
        if not ln.strip():
            continue
        m = ONELINER_RE.match(ln)
        if m:
            return m.group(1).lower(), "XS"
        break
    raise NotRun(
        "no type/tier declaration found: expected '<!-- plan|review v1 · "
        "tier: XS|S|M|L -->' near the top, or an XS one-liner "
        "('Plan (XS): ...' / 'Review (XS): ...')"
    )


def check(text, kind, tier, budgets_advisory=False):
    lines = content_lines(text)
    joined = "\n".join(lines)
    violations = []
    warnings = []

    budget = BUDGETS[tier]
    if budget is not None and len(lines) > budget:
        msg = ("over-budget: %d non-empty lines, tier %s allows %d"
               % (len(lines), tier, budget))
        (warnings if budgets_advisory else violations).append(msg)

    if kind == "plan":
        if not re.search(r"done\s+when", joined, re.IGNORECASE):
            violations.append("missing-done-when: no 'Done when' clause")
        if not re.search(r"verify\s*:", joined, re.IGNORECASE):
            violations.append("missing-verify: no 'Verify:' clause")
        if tier in ("M", "L") and not re.search(
            r"risks|pillars", joined, re.IGNORECASE
        ):
            violations.append(
                "missing-risks: tier %s plan needs a Risks/pillars line "
                "(honest N/A counts, silence does not)" % tier
            )
    else:  # review
        first3 = lines[:3]
        if not any(VERDICT_RE.search(ln) for ln in first3):
            if VERDICT_RE.search(joined):
                violations.append(
                    "verdict-not-first: verdict exists but not within the "
                    "first 3 non-empty lines"
                )
            else:
                violations.append(
                    "missing-verdict: no 'Verdict: PASS|PASS-with-issues|"
                    "BLOCK' line"
                )
        if tier in ("S", "M", "L"):
            if not re.search(r"^#+\s*findings", joined, re.IGNORECASE | re.MULTILINE):
                violations.append("missing-findings: tier %s review needs a Findings section" % tier)
            if not re.search(r"non-findings", joined, re.IGNORECASE):
                violations.append(
                    "missing-non-findings: tier %s review needs a "
                    "Non-findings section (coverage is deliverable)" % tier
                )

    return {
        "status": "FAILED" if violations else "VERIFIED",
        "type": kind,
        "tier": tier,
        "lines": len(lines),
        "budget": budget,
        "violations": violations,
        "warnings": warnings,
    }


def main(argv):
    budgets_advisory = "--budgets-advisory" in argv[1:]
    args = [a for a in argv[1:] if a != "--budgets-advisory"]
    if len(args) != 1:
        print(json.dumps({"status": "NOT-RUN", "violations": [],
                          "reason": "usage: check_artifact.py "
                                    "[--budgets-advisory] <artifact.md>"}))
        print("NOT-RUN: could not evaluate - wrong arguments")
        return 2
    try:
        with open(args[0], "r", encoding="utf-8") as fh:
            text = fh.read()
    except (IOError, OSError, UnicodeDecodeError) as exc:
        print(json.dumps({"status": "NOT-RUN", "violations": [],
                          "reason": "unreadable artifact: %s" % exc}))
        print("NOT-RUN: could not evaluate - unreadable artifact")
        return 2
    try:
        kind, tier = detect(text)
    except NotRun as exc:
        print(json.dumps({"status": "NOT-RUN", "violations": [],
                          "reason": exc.reason}))
        print("NOT-RUN: could not evaluate - %s" % exc.reason)
        return 2

    summary = check(text, kind, tier, budgets_advisory=budgets_advisory)
    print(json.dumps(summary))
    for w in summary["warnings"]:
        print("WARNING: %s (advisory: does not fail the artifact)" % w)
    if summary["status"] == "VERIFIED":
        if summary["warnings"]:
            print("VERIFIED: %s (%s) structure ok; %d budget warning(s), "
                  "advisory" % (kind, tier, len(summary["warnings"])))
        else:
            print("VERIFIED: %s (%s) within budget, all required sections "
                  "present" % (kind, tier))
        return 0
    print("FAILED: %d violation(s): %s"
          % (len(summary["violations"]), "; ".join(summary["violations"])))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
