#!/usr/bin/env python3
"""
check_starter.py

Deterministic checker for a CLAUDE.md-style starter file (see
CLAUDE.starter.md in this piece). Checks four things:

  1. untagged-rule: every top-level "- " bullet block (a bullet plus any
     indented continuation/sub-bullet lines that follow it, joined) inside
     a tagged section ("Code conventions", "Bugfix requires a work order",
     "Hooks installed in this repo") must end with a [NN] tag naming the
     toolkit piece it traces back to, NN in {01,02,03,04,07,08,09,10} --
     the pieces this toolkit actually ships (05 and 06 are internal pieces
     not included here, so they are not valid tags; 10 is receipt-gate,
     which owns the close). A bullet without a tag from that closed set is
     a finding -- it means the rule was invented instead of traced to
     something the toolkit actually ships. The tag may be followed by a
     trailing "." (end of sentence) and still count.

  2. forbidden-vocab: the file must not contain doctrine vocabulary, in
     Portuguese or English. This starter is operational instructions for an
     agent, not a restatement of house doctrine -- so terms like
     "pilar(es)"/"pillar(s)", "doutrina"/"doctrine", "manifesto",
     "swe-pillars", or codes matching P[1-9] / CC[0-9]+ are flagged
     wherever they appear in the file (not only inside tagged sections).
     Ordinary business codes that collide with the pattern
     (a squad called "P2", a priority label "P1") can be exempted per run
     with --allow-vocab (see Usage) -- there is no permanent allowlist
     baked into this script, because an allowlist that silently grows is
     how doctrine vocabulary sneaks back in unnoticed.

  3. leftover-placeholder: the file must not still carry copy-paste debris
     from the template -- an unresolved "<ADJUST:" marker, or the raw
     "<!--" / "-->" header-comment markers from CLAUDE.starter.md's header
     comment. Either means the file was copied but never actually adjusted
     for the adopting repo (see fixture/clean/CLAUDE.md for what "adjusted"
     looks like, versus CLAUDE.starter.md itself, which -- being the
     unadopted template -- is EXPECTED to fail this check; see
     fixture/run_fixture.py).

  4. stale-schema: the file must not name a field from the SUPERSEDED
     piece-02 schema. The card shipped today (CARD-01) has goal,
     non_goals, tier, task_type, done_when, verify and repro -- it has no
     `allowed.files`, no `allowed.commands`, no `reproduction.required`,
     and it is not called `work-order.yaml`. A starter file still naming
     one of those instructs the agent to obey a contract the validator
     will never enforce, which is the drift class this piece exists to
     surface. The list is CLOSED and LEXICAL (four literals, matched
     case-insensitively wherever they appear in the file, not only inside
     the governed sections): this check does not read a rule and decide
     whether it matches its piece -- that stays human review.

Usage:
    python3 check_starter.py <path-to-claude-md-file> [--allow-vocab TOK1,TOK2,...]

    --allow-vocab is a comma-separated, case-insensitive list of exact
    forbidden-vocab matches to exempt for this run only (e.g.
    --allow-vocab=P2,P1 for a repo where "P2"/"P1" name squads or ticket
    priorities, not doctrine pillars). It does not exempt "pilar",
    "doutrina", "manifesto", "swe-pillars", "pillar", "doctrine", or
    CC-codes.

Exit code:
    0  -> no violations found
    1  -> at least one violation found (each printed with its line number)
    2  -> usage error (missing argument) or path does not exist
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

TAGGED_SECTIONS = {
    "Code conventions",
    "Bugfix requires a work order",
    "Hooks installed in this repo",
}


def _norm_heading(text: str) -> str:
    """Normalize a section heading for comparison: strip trailing
    punctuation and whitespace, casefold, and STRIP DIACRITICS.
    '## Code conventions:' silently escaped section governance via the
    appended colon (3rd external review, 2026-08-18); a de-accented
    variant of a heading escaped it via de-accenting (analysis audit,
    2026-08-18) -- comparison happens on the normalized form so neither
    punctuation nor accents can opt a section out. Arbitrary RENAMES are
    handled one level up: every governed section must be PRESENT (see
    check_untagged_rules), so a renamed heading surfaces as a missing
    governed section instead of silently ungoverning its rules."""
    text = re.sub(r"[\s:.;!…]+$", "", text).strip().casefold()
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


TAGGED_SECTIONS_NORM = {_norm_heading(s) for s in TAGGED_SECTIONS}

VALID_TAGS = {"01", "02", "03", "04", "07", "08", "09", "10"}

# Top-level bullets only (column 0). An indented "  - sub-item" is a
# continuation of the enclosing bullet's block, not a new rule that needs
# its own [NN] tag. Every Markdown list form counts as a rule: '-', '*',
# '+', and numbered items ('1.', '1)') -- a rule written as '1. ...' used
# to be invisible to the tag check (analysis audit, 2026-08-18).
BULLET_RE = re.compile(r"^(?:[-*+]|\d+[.)])\s+")
# Tag may be the literal end of the block, or followed by a trailing "."
# closing the sentence -- both count as "tagged".
TAG_RE = re.compile(r"\[(\d{2})\]\.?\s*$")

FORBIDDEN_VOCAB_RE = re.compile(
    r"pilar(es)?|doutrina|manifesto|swe.?pillars|pillar(s)?|doctrine"
    r"|\bP[1-9]\b|\bCC[0-9]+\b",
    re.IGNORECASE,
)

# Field names from the SUPERSEDED piece-02 schema. CARD-01 (2026-08-19)
# replaced them: the card is `CARD.yaml`, its scope fence is `non_goals`,
# and a bugfix's reproduction is `repro` (the evidence itself, not a
# `reproduction.required` boolean). A starter file that still names one of
# these tells the agent to obey a contract no validator enforces. Closed
# list, lexical on purpose -- see the docstring.
STALE_SCHEMA_NAMES = (
    "allowed.files",
    "allowed.commands",
    "reproduction.required",
    "work-order.yaml",
)
STALE_SCHEMA_RE = re.compile(
    "|".join(re.escape(n) for n in STALE_SCHEMA_NAMES), re.IGNORECASE
)

LEFTOVER_ADJUST_RE = re.compile(r"<ADJUST:")
LEFTOVER_HEADER_COMMENT_RE = re.compile(r"<!--|-->")

SECTION_HEADER_RE = re.compile(r"^##\s+(.+?)\s*$")


def check_untagged_rules(lines: list[str]):
    """Bullets ("- ...") may wrap onto following indented continuation
    lines, and may be followed by indented sub-bullets that elaborate on
    the rule (e.g. "  - ideal: 200-300 lines") -- those don't need a tag
    of their own. The [NN] tag is expected at the end of *some* physical
    line within the block (its own wrapped line, or an earlier line the
    sub-bullets hang off of), not necessarily the last line of the block."""
    violations = []
    current_section = None
    block_start = None
    block_text_lines: list[str] = []

    def flush():
        if block_start is None:
            return
        joined = " ".join(t.strip() for t in block_text_lines)
        found_tag = None
        for t in block_text_lines:
            m = TAG_RE.search(t.strip())
            if m:
                found_tag = m.group(1)
        if found_tag is None:
            violations.append(
                f"line {block_start}: [untagged-rule] bullet in section "
                f"'{current_section}' has no [NN] tag: {joined!r}"
            )
        elif found_tag not in VALID_TAGS:
            violations.append(
                f"line {block_start}: [untagged-rule] tag [{found_tag}] is "
                f"not in the closed set {sorted(VALID_TAGS)}: {joined!r}"
            )

    # Governance is accounted PER SECTION, not globally: one valid bullet
    # in one governed section used to satisfy a global count while a
    # sibling governed section full of prose or numbered items was checked
    # against zero rules (5th external review, 2026-08-18).
    closed_sections = []  # (name, header_line_no, rule_count)
    section_line = None
    section_rules = 0

    def close_section():
        nonlocal section_line, section_rules
        if current_section is not None:
            closed_sections.append((current_section, section_line,
                                    section_rules))
        section_line, section_rules = None, 0

    for i, line in enumerate(lines, start=1):
        header_match = SECTION_HEADER_RE.match(line)
        if header_match:
            if current_section is not None:
                flush()
            close_section()
            block_start, block_text_lines = None, []
            raw = header_match.group(1)
            if _norm_heading(raw) in TAGGED_SECTIONS_NORM:
                current_section = raw
                section_line = i
            else:
                current_section = None
            continue

        if current_section is None:
            continue

        if BULLET_RE.match(line):
            flush()
            block_start, block_text_lines = i, [line]
            section_rules += 1
        elif line.strip() == "":
            flush()
            block_start, block_text_lines = None, []
        elif block_start is not None:
            block_text_lines.append(line)

    if current_section is not None:
        flush()
    close_section()

    # EVERY governed section must be PRESENT, each absence named
    # individually. A near-empty file passing silently was a confirmed
    # bypass (3rd external review, 2026-08-18); a RENAMED heading silently
    # ungoverning its rules while siblings kept the file green was the
    # same bypass one level up -- presence-by-canonical-name closes the
    # rename CLASS, not just the de-accent instance (analysis audit,
    # 2026-08-18).
    seen_norms = {_norm_heading(name) for name, _, _ in closed_sections}
    for canonical in sorted(TAGGED_SECTIONS):
        if _norm_heading(canonical) not in seen_norms:
            violations.append(
                f"[missing-governed-section] governed section "
                f"'{canonical}' is absent -- a renamed or dropped heading "
                "silently ungoverns its rules; if this repo deliberately "
                "dropped it, that is a template departure to make "
                "explicit, not a silent pass"
            )

    # A governed HEADING with zero governed rule blocks is the same
    # bypass one level inward: syntactically "something to govern",
    # zero rules actually checked (4th external review, 2026-08-18) --
    # and it is a per-section fact, so every empty governed section is
    # named individually (5th external review, 2026-08-18).
    for name, line_no, count in closed_sections:
        if count == 0:
            violations.append(
                f"line {line_no}: [empty-governed-section] governed "
                f"section '{name}' contains no rule bullets -- "
                "the tag-traceability check ran on zero rules here; "
                "prose is not governed"
            )

    return violations


def check_forbidden_vocab(lines: list[str], allowlist: set[str] | None = None):
    allowlist = allowlist or set()
    violations = []
    for i, line in enumerate(lines, start=1):
        # EVERY match on the line is inspected. Checking only the first match
        # let an allowlisted token mask a forbidden one on the same line
        # ("P2 manifesto ..." with --allow-vocab=P2 sailed through) --
        # external review finding, 2026-08-18.
        for match in FORBIDDEN_VOCAB_RE.finditer(line):
            if match.group(0).upper() not in allowlist:
                violations.append(
                    f"line {i}: [forbidden-vocab] matched {match.group(0)!r}: "
                    f"{line.strip()!r}"
                )
                break  # one finding per line is enough; the line is quoted
    return violations


def check_leftover_placeholders(lines: list[str]):
    violations = []
    for i, line in enumerate(lines, start=1):
        if LEFTOVER_ADJUST_RE.search(line):
            violations.append(
                f"line {i}: [leftover-placeholder] unresolved '<ADJUST:' "
                f"marker -- this section was copied but never adjusted: "
                f"{line.strip()!r}"
            )
        elif LEFTOVER_HEADER_COMMENT_RE.search(line):
            violations.append(
                f"line {i}: [leftover-placeholder] template header-comment "
                f"marker ('<!--' or '-->') still present -- remove the "
                f"header comment block when copying the template: "
                f"{line.strip()!r}"
            )
    return violations


def check_stale_schema(lines: list[str]):
    """One finding per line (the line is quoted, so a second literal on the
    same line adds no information) -- same shape as forbidden-vocab."""
    violations = []
    for i, line in enumerate(lines, start=1):
        match = STALE_SCHEMA_RE.search(line)
        if match:
            violations.append(
                f"line {i}: [stale-schema] matched {match.group(0)!r} -- a "
                f"field name from the superseded piece-02 schema; the card "
                f"shipped today is CARD.yaml with goal/non_goals/tier/"
                f"task_type/done_when/verify/repro: {line.strip()!r}"
            )
    return violations


# Tokens the docs promise can NEVER be exempted. Enforced here, not just
# documented (doc said it; code didn't -- external review finding, 2026-08-18).
NEVER_EXEMPT_RE = re.compile(
    r"^(pilar(es)?|doutrina|manifesto|swe.?pillars|pillar(s)?|doctrine"
    r"|CC[0-9]+)$",
    re.IGNORECASE,
)


def _parse_allow_vocab(argv: list[str]):
    """Returns (path_arg, allowlist_set) or (None, None) on usage error.

    Raises SystemExit(2) with a message if a never-exemptable token is
    passed -- refusing loudly beats silently honoring a forbidden exemption.
    """
    allowlist: set[str] = set()
    positional = []
    for arg in argv:
        if arg.startswith("--allow-vocab="):
            tokens = arg.split("=", 1)[1]
            for t in tokens.split(","):
                t = t.strip()
                if not t:
                    continue
                if NEVER_EXEMPT_RE.match(t):
                    print(
                        f"ERROR: --allow-vocab cannot exempt {t!r} -- "
                        "'pilar', 'doutrina', 'manifesto', 'swe-pillars', "
                        "'pillar', 'doctrine' and CC-codes are never "
                        "exemptable (see docstring).",
                        file=sys.stderr,
                    )
                    raise SystemExit(2)
                allowlist.add(t.upper())
        else:
            positional.append(arg)
    if len(positional) != 1:
        return None, None
    return positional[0], allowlist


def main():
    path_arg, allowlist = _parse_allow_vocab(sys.argv[1:])
    if path_arg is None:
        print(
            "Usage: python3 check_starter.py <path-to-claude-md-file> "
            "[--allow-vocab=TOK1,TOK2,...]",
            file=sys.stderr,
        )
        return 2

    path = Path(path_arg)
    if not path.exists():
        print(f"ERROR: path does not exist: {path}", file=sys.stderr)
        return 2

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="latin-1")
    lines = text.splitlines()

    violations = (
        check_untagged_rules(lines)
        + check_forbidden_vocab(lines, allowlist)
        + check_leftover_placeholders(lines)
        + check_stale_schema(lines)
    )
    def _line_no(v):
        # File-level findings (no "line N:" prefix) sort first.
        m = re.match(r"line (\d+):", v)
        return int(m.group(1)) if m else 0

    violations.sort(key=_line_no)

    if violations:
        print(f"FAIL: {len(violations)} violation(s) found in {path}\n")
        for v in violations:
            print(f"  - {v}")
        return 1

    print(f"PASS: no violations found in {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
