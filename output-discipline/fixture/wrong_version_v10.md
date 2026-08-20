<!-- plan v10 · tier: M -->

# Plan: anything

Goal: prove v10 is NOT v1 -- the old grammar accepted `v10` because the
`[^a-zA-Z]*` after `v1` swallowed the `0` (5th external review, 2026-08-18).

Done when: the checker rejects this declaration as unknown.

Verify: py -3 scripts/check_artifact.py fixture/wrong_version_v10.md

Risks: none -- fixture.
