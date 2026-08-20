# 08 — starter CLAUDE.md · ADOPTION

The mechanics and the limits are in the [README](README.md); the receipts are the
fixture cases under `fixture/`, run by `fixture/run_fixture.py`.

## How to adopt (step by step)

1. Copy `CLAUDE.starter.md` to `CLAUDE.md` at the root of the adopting
   repository (removing the header comment).
2. Adjust every `<ADJUST: ...>` — in particular "Hooks installed in this
   repo": remove hooks the repo did not actually install; the file must not
   claim protection that doesn't exist.
3. Run the checker against the adjusted copy before committing.
   `check_starter.py` lives in this folder of the toolkit — run it from the
   root of the adopting repo, pointing at the script's path:
   ```
   python3 <path-to-the-toolkit>/starter-claude-md/check_starter.py CLAUDE.md
   ```
   (A wrong path in either argument gives `ERROR: path does not exist` —
   check both before reporting a bug.) Exit `0` = form ok; `1` = fix what's
   named; `2` = incorrect usage or nonexistent path.
4. A dev can carry the "Code conventions" section into their global
   `~/.claude/CLAUDE.md` — never the hooks section, specific to this repo
   (see "Where to put it" in the template).

## The `--allow-vocab` escape hatch

`--allow-vocab=TOK1,TOK2,...` exempts, **only for this run**, exact matches
(case-insensitive) of the forbidden pattern — for legitimate business codes
that collide with the pattern (squad "P2", priority "P1"). There is no
permanent allowlist in the script: an allowlist that grows silently is how
doctrine vocabulary comes back unnoticed.

Tokens that are **never exemptable**: "pilar"/"pilares", "doutrina",
"manifesto", "swe-pillars", "pillar"/"pillars", "doctrine", and `CC<n>`
codes. Trying to exempt them is
refused loudly with exit 2, never honored. An exempted token does not mask a
forbidden term on the same line (every match on the line is inspected).

## The dictation rule

The template installs the flow (the `[09]` bullet under "Code conventions"):
the human dictates, the agent fills in the corresponding template
(work order, plan, review), runs the piece's validator, and hands it back
for human review — **the validator proves the form, the human signs the
substance**. Never fabricate content (reproduction evidence, test result) to
satisfy a validator: a field the agent doesn't have, it asks for.

## What only a human decides

- Which hooks the repo actually installed — no checker in this piece
  verifies the real installation.
- Whether a rule belongs in the repo's `CLAUDE.md` or the dev's global one.
- Granting `--allow-vocab` to legitimate business codes — and refusing the
  temptation to exempt doctrine vocabulary.
