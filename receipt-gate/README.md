# Receipt Gate (verify-on-Stop)

> Docs for this piece: **README** (promise, command, states, coverage) ·
> [adapt/README.md](adapt/README.md) (how to install — per-repo, with a
> mandatory self-test). The evidence is the re-runnable fixture (62 cases) +
> the empirical spike ([fixture/spike/SPIKE.md](fixture/spike/SPIKE.md)).

## The decision this piece changes

Before: nothing ties completion evidence to the current review — the agent
says "done" and the human rereads the whole diff or trusts it. After: **only
the gate emits VERIFIED**, and only after re-running the active card's
`verify` against the current tree, at close time, with the tree hashed before
and after. A VERIFIED without backing **cannot be produced through a close**;
closing honestly as FAILED/UNVERIFIED is always possible (it is the loop's
boundary) and always leaves a durable, conservative receipt.

## Close model (the gate locks the CLAIM, not the session)

The Stop hook fires at the end of every RESPONSE — observed in the spike in
`-p` mode (two invocations in one session); firing per turn in interactive
mode is INFERRED from that observation, not measured separately, and the
close model is safe under any frequency. That's why the close is
**declared**, via `CARD.close` alongside the card:

| CARD.close | Means | Gate does |
|---|---|---|
| absent | work in progress | 1-line warning (echoes existing receipt + "tree has moved" via rev+diff_sha), exit 0, nothing verified |
| `CLOSE` | close intends VERIFIED | schema (02) + verify re-run + H1/H2 freshness + (S3) review — all green ⇒ VERIFIED receipt; any failure ⇒ BLOCK exit 2 |
| `FAILED: <reason>` / `UNVERIFIED: <reason>` | honest close | always allowed; receipt with verdict + reason; degrades (hashes null, named) where git fails |

The gate CONSUMES `CARD.close` on every allowed close; the durable record is
`CARD.receipt.json`:
`{command, exit, verdict, reason?, rev, patch_id, diff_sha, diff_hash, timestamp}`.
**A VERIFIED receipt always carries non-null rev/patch_id/diff_sha — a
VERIFIED with a null hash is forged on its face.** `rev`+`patch_id`+`diff_sha`
are recomputable on the SAME checkout while the tree still exists (never
cross-machine).

## Command and states

Install: see [adapt/README.md](adapt/README.md) (per-repo, mandatory
self-test with the exact registered command string; step 1 of the self-test
is the mechanical wiring check, `adapt/check_wiring.py` — exit 0 only when
the registered Stop command answers the gate's `BAD-INPUT` block on empty
stdin, re-runnable from the adopting repo's CI). Fixture:

```
python3 fixture/run_fixture.py        # exit 0 = gate correct (62 cases)
```

| Gate exit | Means |
|---|---|
| 0 | stop allowed: NO-CARD, WIP turn, honest close, or VERIFIED |
| 2 | named BLOCK on stderr (fed back to the model): `BAD-INPUT` · `CARD-CONFIGURED-BUT-MISSING` · `CLOSE-TOKEN` · `SCHEMA` · `GIT-ERROR` · `INDEX-FLAGS` · `UNEXPECTED-CHANGE` · `VERIFY-RED` · `TIMEOUT` · `S3-REVIEW` · `GATE-ERROR` |

Structural fail-closed: the entire body sits in a guard from line 1 (`import
yaml` inside the guard); an unhandled exception ⇒ named exit 2, never 1 (1
would not block). Every git command in the material must exit 0 (one named
exception: `refs/stash` absent ⇒ "none"), otherwise `GIT-ERROR` — the output
of a failed command is never hashed.

## The hash material (H1 before verify, H2 after; H1≠H2 ⇒ UNEXPECTED-CHANGE)

Pinned diff command (single source for the material and `diff_sha`):
`git -c core.quotepath=false -c diff.noprefix=false -c diff.mnemonicPrefix=false
-c diff.interHunkContext=0 diff --no-ext-diff --no-color --no-textconv -U3 HEAD`.
Components: `rev` · pinned diff bytes · untracked file names
(`--untracked-files=all`; gitignore still excludes side-effect noise) ·
reflog tripwire (`git reflog --format='%H %gs'` — count+subjects; the tip
alone is byte-identical across a stash round-trip, proven) · `refs/stash` ·
index flags (`ls-files -v` outside `H `) · content of the CARD family
(resolved card, CARD.close, CARD.review.md). `CARD.receipt.json` is EXCLUDED
entirely (it is the gate's own output); on every BLOCKed close attempt the
receipt is deleted again — including on the guard's exception route — so that
a receipt planted by verify does not survive the block.

## S3 routing invariant

`tier: S3` + `CLOSE` close ⇒ `CARD.review.md` must (a) pass the piece-09
checker with exit 0 AND (b) have a PASS/PASS-with-issues verdict at its first
occurrence within the first 3 content lines (regex identical to the
checker's) — BLOCK, contradictory verdicts, or no verdict at all (an artifact
typed as a plan passes the checker with no verdict whatsoever) ⇒ BLOCK.
Plan-mode approval is NOT checkable by a Stop hook — an honest boundary. An
honest close of an S3 card skips the review but still writes a durable
FAILED/UNVERIFIED verdict: the skip is visible, never silent. The gate runs
the piece-09 checker with `--budgets-advisory` (CARD-03): a structure
violation (verdict absent/buried, missing section) still blocks; overrunning
the line budget alone only produces a warning and does not block an
otherwise structurally valid S3 close.

## What it does NOT catch (honest, named boundaries)

- **Receipt forgery outside a close (KNOWN-LIMITATION, fixed in the
  fixture):** an agent with write access to the tree can forge
  `CARD.receipt.json` on a WIP turn and it persists — file presence alone
  doesn't distinguish; detection is the WIP-turn echo line, the operator's
  ratification, or recomputing rev/diff_sha.
- **Non-git mutate-and-restore** (cp out / restore) inside verify —
  endpoint hashing doesn't see it; git-native variants (stash, commit,
  checkout, assume-unchanged) are caught by the tripwires.
- **Reflog scrubbing / evasions inside `.git`** (clean filters via
  `.git/info/attributes`, fsmonitor) — the material does not hash `.git`.
- **Verify that's technically real but irrelevant to the goal** — form, not
  relevance; that's human review of the card.
- **Orphaned stragglers on timeout** (Windows: reparenting gap in `taskkill
  /T`; POSIX: verify runs in its own process group and the timeout uses
  `killpg` — processes that switch groups escape).
- **Concurrency:** parallel sessions belong to separate worktrees (material
  is per-worktree); within one worktree, a tree moving during a close ⇒
  BLOCK by design, cheap to retry.
- **An interpreter that vanishes AFTER install** (upgrade, clone on a new
  machine) still leaves the gate silently absent until
  `adapt/check_wiring.py` is run again — the check DETECTS dead wiring at
  the moment it runs, nothing prevents it; re-run it (CI of the adopting
  repo is the natural place).

## Coverage

| Promised | Mechanically covered | Not covered / known bypass | Classification |
|---|---|---|---|
| VERIFIED without backing impossible via close | 62 cases: red blocks, stale blocks, planted receipts deleted (start, block-exit, guard route) | forgery on a WIP turn persists | fixed KNOWN-LIMITATION |
| Honest close always reachable | fixtures: broken/unreadable/non-git/no-git card — all exit 0 with a conservative receipt | — | covered |
| Binding catches verify mutation | tracked, untracked-dir (-uall), CARD family, stash, assume-unchanged | non-git cp-restore; inside .git | accepted limitation |
| Fail-closed | pyyaml absent, git absent, empty stdin, unborn HEAD, unreadable card ⇒ named exit 2 | broken wiring (shell exit≠2) — resolved by: adapt/check_wiring.py (+ self-test); an interpreter that vanishes after install stays undetected until the check is re-run (detection, not prevention) | accepted limitation |
