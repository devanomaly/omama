# CLAUDE.md — fixture: per-section bypass

A file with ONE valid governed section and ANOTHER governed section
containing only prose and numbered items. Global bullet counting used to
let the second one pass silently (5th external review, 2026-08-18):
"something to govern" existed globally, but zero rules from this section
were ever checked.

## Code conventions

- Files up to 500 lines; function names unique across the repo. [07]

## Bugfix requires a work order

Every bugfix needs a validated work order before any edit, and the
validator must be run before touching code, with the output attached.
Running prose instead of bullets: zero governable rules in this section.

## Hooks installed in this repo

- Privacy pre-commit runs on every commit. [01]
