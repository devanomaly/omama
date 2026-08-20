# Work Order (card slim)

> Docs for this piece: **README** (promise, command, states, coverage) ·
> [ADOPTION.md](ADOPTION.md) (integration and human decisions). The evidence is the
> re-runnable fixture; the legacy schema's red-green history lives in git
> (EVIDENCE.md through 2026-08-19).

## The decision this piece changes

Before: an agent receives "fix bug X" as loose prose and decides scope and what
counts as "done" alone. After: the task enters as a **slim card** — goal, non-goals, tier
ratified by the human, observable done-when, **one real `verify` command**, and attached
reproduction when it's a bugfix. The concrete decisions that change: **a bugfix without
attached reproduction does not pass** (exit 1), **a vacuous `verify` does not pass** (a card
whose proof command is `true`/`echo` closes nothing), and tier S3 carries the routing
invariant — plan approval + review pass before close. The validator is preflight: it
proves the card before dispatch; whoever re-runs `verify` at close and emits VERIFIED is
the receipt gate, not this validator.

## What it is

- `work-order.template.yaml` — the slim schema, every field commented in English.
- `validate_work_order.py` — deterministic validator (no LLM) of a **closed schema**:
  - required keys (`goal`, `non_goals`, `tier`, `task_type`, `done_when`,
    `verify`) present and **no unknown key**; a value that is present-but-null is a
    named violation (containment theater);
  - `tier` from the closed enum S1|S2|S3 (proposed by the agent, ratified by the human);
  - `verify` is ONE non-vacuous command — minimal deny-list: empty, `true`, `:`,
    `echo ...`;
  - `bugfix => repro` attached and typed (non-empty string/list; `repro: true` is a
    checkbox and is rejected);
  - **duplicate YAML key rejected** (the default parser would silently keep the last
    one);
  - **fail-closed**: malformed config produces a named `VIOLATION:` and exit 1, never
    a traceback.
- (GUIA.md used to describe the legacy schema; removed in the 2026-08-19 reorg —
  the commented template is the guide now.)
- `fixture/` — 1 clean case + 12 cases with a planted violation + runner with regression
  locks (each red pinned to ALL of its named reasons). Legacy-schema fixtures:
  `fixture/archive/`.

## Command and states

```
py -3 validate_work_order.py <card.yaml>
```

| Exit | State | Means |
|---|---|---|
| 0 | OK | well-formed card; prints `OK: ...` |
| 1 | VIOLATION | one `VIOLATION: ...` line per reason on stderr (includes internal error — fail-closed) |
| 2 | not runnable | pyyaml missing or wrong CLI usage |

Fixture: `py -3 fixture/run_fixture.py` (exit 0 = validator correct).

## Scope and limits

### What it catches

Thirteen fixture cases, each red pinned to all of its named reasons. Classes
covered: missing/unknown/duplicate key, null values, tier outside the enum,
vacuous `verify` (four deny-list variants), bugfix without repro, repro-checkbox,
malformed `task_type` without a traceback.

### What it does NOT catch

Named gaps, each with the layer that resolves it:

- **Truth of content.** A made-up `repro` passes; a `verify` that is technically real
  but irrelevant to the goal passes — the validator checks form, not relevance. Resolved
  by: human reading of the card before dispatch.
- **Post-execution compliance.** The validator is preflight: it never observes the diff
  or the `verify` result. Resolved by: the receipt gate (Stop-hook) re-runs `verify` at
  close and binds the result to the current tree.
- **Tier ratification.** `tier: S1` on S3-scale work passes the validator — ratification
  is human by design; enforcement of the S3 invariant belongs to the receipt gate.
- **Dispatch without the validator.** Nothing forces `validate_work_order.py` to run
  before the agent is dispatched. Resolved by: a gate in the dispatch pipeline.
- **Vacuity beyond the deny-list.** `python -c "pass"` or a test that always passes
  are not detected — the deny-list catches the canonical no-ops, not the whole class.
  Resolved by: human review of the command + the receipt gate requiring the red to
  already have been seen.

### What only a human decides

See [ADOPTION.md](ADOPTION.md) — relevance of `verify` to the goal, narrowness of
non-goals, veracity of the repro, ratification of the tier.

### Coverage

| Promised | Covered mechanically | Not covered / known bypass | Classification |
|---|---|---|---|
| Bugfix without attached reproduction does not pass | `invalid_bugfix_no_repro` + `invalid_repro_checkbox` → exit 1 | dispatch that skips the validator | accepted limitation |
| Vacuous `verify` does not pass | 4 deny-list variants → exit 1 | vacuity outside the deny-list (`python -c "pass"`) | accepted limitation |
| Closed schema, no silent key | unknown/duplicate/null → exit 1 | — | covered |
| Tier routes S3 to plan+review | enum value → exit 1 | the invariant itself (enforcement is the receipt gate's) | out of scope (by design) |
