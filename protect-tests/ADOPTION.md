# 04 — protect-tests · ADOPTION

Integration and human decisions. The mechanics and the limits are in the [README](README.md).

**Nothing in this piece is installed.** `vendor/` and `adapt/` are reference/example material.

## How to adopt (step by step)

1. Read `vendor/PROVENANCE.md` to confirm the script's origin (repo + commit) — and the
   current maintenance decision.
2. Read `adapt/README.md` and `adapt/settings.example.json` to see how a team's repository
   would actually plug this in: manual copy of the script + `hooks.PreToolUse` snippet in the
   repo's `.claude/settings.json`.
3. Before installing anywhere real, run the fixture to confirm the behavior in your environment.

## Sanctioned route for legitimate deactivation

When deactivating a test is legitimate (real deprecation, deliberate quarantine), the sanctioned
route is for the **human to run the command manually** — the deny message itself points this out.

## What only a human decides

- Installing the hook in a real repository — decision of the team that owns the repo.
- When deactivating a test is legitimate — and running the manual route above.
- The fork-vs-accept maintenance decision — **made 2026-08-18: ACCEPT** (upstream kept
  byte-identical; no fork for now), with the README's residual formally accepted. Owner: the
  maintainer; revisit after one dogfooding cycle (internal pilot). Full justification in
  `vendor/PROVENANCE.md` ("Maintenance decision: ACCEPT"). Reopening it is a human decision, not
  an effect of review.
