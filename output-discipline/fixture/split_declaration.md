<!-- plan v1 -->
<!-- tier: M -->

# Plan: split declaration

Goal: prove the declaration has to live in a SINGLE comment -- the old
regex crossed `--> <!--` because the separator allowed anything
non-alphabetic (5th external review, 2026-08-18).

Done when: the checker treats this file as NOT declared.

Verify: python3 scripts/check_artifact.py fixture/split_declaration.md

Risks: none -- fixture.
