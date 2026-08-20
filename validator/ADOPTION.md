# 03 — Validator · ADOPTION

Instantiation, CI, and human decisions. The mechanics and limits are in the
[README](README.md).

## How to instantiate the skeleton

1. Copy `validator_skeleton.py` into your project (it depends on nothing else in this
   toolkit).
2. Define the `SCHEMA` dict — one entry per column you want to lock:
   ```python
   SCHEMA = {
       "category": {"required": True, "enum": {"bug", "feature", "chore"}},
       "priority": {"required": True, "enum": {"low", "medium", "high"}},
       "notes": {"required": False},
   }
   ```
   A typo here doesn't pass silently: `check_schema()` turns a malformed schema
   (e.g.: `"type": "integer"`) into a named `NOT-RUN`, exit 2, before any row
   is evaluated.
3. Run: `python3 validator_skeleton.py --csv path/to/artifact.csv`
4. If you'd rather keep the schema in a file separate from the skeleton (common when the
   same schema is used in more than one place), import
   `run_cli`/`validate_rows`/`load_csv` in your own instantiation — see
   `example_instantiation.py`, which does exactly that for `example_labels.csv`.

## Wiring into CI / a gate

Wire the exit code into your gate (CI, pre-commit hook, deploy script): `0` =
`VERIFIED`, proceed; `1` = `FAILED`, stop — there's a named violation; `2` = `NOT-RUN`,
stop — it couldn't even evaluate; treat it exactly as a failure, never as "no
opinion". The piece's fixture (`python3 fixture/run_fixture.py`, exit 0) can sit in the
CI as a regression test of the validator itself.

Before wiring the validator's stdout into shared logging, confirm header
provenance: does the artifact's writer always emit the header row? Without that
guarantee, the partial-overlap route may echo raw data — possibly
PII — as `unknown-column` (see README, "What it does NOT catch").

## What only a human decides

- **Schema design**: which columns exist, what is `required`, what enters the
  closed vocabulary of each column. The validator applies the schema it was given; it
  has no opinion on whether the schema is right.
- **What counts as a valid label set** — e.g.: does `urgent` deserve to enter the
  `priority` enum, or is it a symptom of invented labels? A product decision, made
  outside this piece.
- **The partial-overlap route trade-off**: keeping the diagnostic by column
  name (and living with the leak route under the guaranteed-header-provenance
  assumption) or swapping names for positions (and losing the header-typo
  diagnostic). Neither is neutral.
- **Minimum row count** (`min_rows`): if your case can't tolerate a header-only
  CSV (a vacuous `VERIFIED` with `rows: 0`), that business rule belongs in your
  instantiation — not in the generic skeleton.
- **Accepting any residual** from the README's coverage table.
