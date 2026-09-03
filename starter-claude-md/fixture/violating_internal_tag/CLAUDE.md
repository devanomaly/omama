# CLAUDE.md — fixture: tags for pieces this toolkit does not ship

05 and 06 are internal evaluations, cut before adoption and not included in
this toolkit (see the [NN] legend in the root README). A rule tagged to one
of them looks traced but points at nothing an adopter can install — the
closed set exists to make that visible. This case locks them OUT while 10
(receipt-gate) is IN.

## Code conventions

- Files up to 500 lines; function names unique across the repo. [07]
- Every plan or review declares a tier and follows the shipped structure. [05]

## Bugfix requires a work order

- Every task enters as a validated card before code is edited. [02]

## Hooks installed in this repo

- Privacy pre-commit runs on every commit. [01]
- The Stop hook re-runs the card's verify at close. [06]
