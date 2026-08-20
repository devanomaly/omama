# Output Discipline

> Docs for this piece: **README** (promise, command, states, coverage) ·
> [ADOPTION.md](ADOPTION.md) (integration and human decisions). The evidence is the
> re-runnable fixture; red-green history in git (EVIDENCE.md through 2026-08-19).

**Status: ON TRIAL.** Mechanics fixture-proven (11 cases, reds pinned to their named
reason); **effectiveness** under measurement in the author's harness, predictions frozen
before adoption (harness-audit, ledger 006: median length ↓≥40%, steering
non-inferior, pass-rate ≥80%). The label becomes "adjudicated" when the ledger closes;
the effectiveness verdict does not exist yet.

## The decision this piece changes

What the human reads per task stops being unbounded prose: the plan/review declares its
tier and carries done-when, verify, and verdict-first — or a script says why not, when
run (spot-check, not a block; see "Scope and limits"). The line budget is advisory: the
checker warns, it does not fail (default mode still fails; the seed loop runs with
`--budgets-advisory`).

## What it is

- `templates/PLAN.md` / `templates/REVIEW.md` — tier declared in a comment at the top,
  line budget.
- `scripts/check_artifact.py` — deterministic validator: structure and budget become
  an exit code.
- `fixture/` — 11 red-green cases plus a runner with named locks.

Tier = consequence × exposure × detection × cost to correct later.

| Tier | Advisory budget (non-empty lines, no comments) | Extra requirements |
|---|---|---|
| XS | ≤5 (usually one line in chat) | done-when + verify / verdict on the line itself |
| S | ≤15 | review: Findings + Non-findings sections |
| M | ≤40 | plan: a Risks/pillars line (honest N/A counts) |
| L | no ceiling | review: verdict first · plan: summary first (see note) |

**Reviews** (every tier): verdict within the first 3 non-empty lines — buried
fails, mechanically. **Honest note:** in **plans**, tier L "summary first" is
template guidance, **not** a mechanical check.

## Command and states

```
python3 scripts/check_artifact.py [--budgets-advisory] <artifact.md>
```

| Exit | State | Means |
|---|---|---|
| 0 | VERIFIED | type/tier declared; budget and fields ok |
| 1 | FAILED | named violations (`over-budget`…) |
| 2 | NOT-RUN | unreadable or no declaration — a coverage failure is never a pass |

`--budgets-advisory` (seed loop mode, 2026-08-19 — panel: structure 5/5,
line budgets killed 4/5): STRUCTURE stays mandatory (buried/missing verdict,
tier, non-findings, done-when/verify ⇒ exit 1); going over budget becomes a
`WARNING: over-budget…` + exit 0 + a `warnings` list in the JSON.
Without the flag, behavior is byte-for-byte identical to before.

Declaration: a **single** comment, exact `v1`, in the **first 5 non-empty lines** —
buried, split, or with an unknown version (`v10`) becomes NOT-RUN. Fixture:
`python3 fixture/run_fixture.py` (exit 0 = checker correct).

## Scope and limits

### What it catches

Seventeen cases (11 default mode + 6 `--budgets-advisory`), runner exit 0 —
the case-by-case table is the runner itself.

### What it does NOT catch

Each route with the layer that resolves it:

- **"Building to the template."** Form, never quality — a plan empty of meaning
  that fills in the fields passes. Resolved by: human review of the substance.
- **Smuggling via dense lines.** Lines are counted, not tokens. Resolved by: human
  review (escalation: count tokens, if the trial shows abuse).
- **Artifact never checked.** Spot-check: nothing forces running the script. Resolved
  by: compliance measured in the trial (ledger 006); a hook only if the decay pays for
  the ceremony.
- **Under-declared tier.** The checker accepts the declaration as given — XS on work
  of M severity buys a smaller budget than the real severity warrants. Resolved by:
  human review.
- **Plan L without summary-first.** No mechanical check. Resolved by: human review.

### What only a human decides

See [ADOPTION.md](ADOPTION.md).

### Coverage

| Promised | Covered mechanically | Known bypass | Classification |
|---|---|---|---|
| Well-formed declaration at the top | 4 fixtures → exit 2 | under-declared tier passes | not assessed |
| Fits the tier's budget | `plan_over_budget` → exit 1 (default mode; with `--budgets-advisory` becomes WARNING + exit 0) | dense lines smuggle volume | defect |
| Plan carries done-when + verify | `plan_missing_verify` → exit 1; clean → exit 0 | fields without meaning | not assessed |
| Review opens with the verdict | `review_verdict_buried` and `verdict_theater_passing` → exit 1 | verdict first, but wrong | not assessed |
| Plan L: summary first | nothing — guidance only | plan L without summary passes | accepted limitation |
| Artifacts go through the checker | nothing — spot-check | artifact never submitted | defect |
