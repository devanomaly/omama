# CLAUDE.md — fixture: numbered/star rules without a tag

BULLET_RE used to accept only "- ": a rule written as "1." or "*" inside a
governed section was invisible to the tag check (analysis audit,
2026-08-18).

## Code conventions

- Files up to 500 lines; function names unique across the repo. [07]
1. Numbered rule with no tag at all — used to be invisible to the checker
* Star rule with no tag — same issue

## Bugfix requires a work order

- Every bugfix needs a validated work order before editing code. [02]

## Hooks installed in this repo

- Privacy pre-commit runs on every commit. [01]
