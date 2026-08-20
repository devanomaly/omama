# CLAUDE.md — fixture: renamed governed heading

Renaming a governed heading used to drop it from TAGGED_SECTIONS_NORM
silently: with sibling sections present, neither missing- nor
empty-governed-section fired, and untagged rules inside it sailed through
(analysis audit, 2026-08-18 — the 3rd review's colon fix covered the
instance, not the class).

## Project rules

- Files up to 500 lines, no tag at all here
- Function names unique across the repo, also no tag

## Bugfix requires a work order

- Every bugfix needs a validated work order before editing code. [02]

## Hooks installed in this repo

- Privacy pre-commit runs on every commit. [01]
