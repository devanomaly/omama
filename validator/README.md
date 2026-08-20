# Validator

> **Library/substrate, not a governance piece** (relabeled in the reduction
> round, the panel's unanimous verdict, 2026-08-19): this is where 09 and the
> receipt gate inherit the tri-state exit contract. Docs: **README** (promise,
> command, states, coverage) · [ADOPTION.md](ADOPTION.md) (instantiation, CI and
> human decisions). The evidence is the re-runnable fixture; the red-green
> history lives in git (EVIDENCE.md up to 2026-08-19).

## The decision this piece changes

When an agent (or a human) produces a structured artifact — a labels CSV,
a config, a report — the question "does this obey the structural contract?" stops
being answered by "the agent said it's done" or by someone opening the file and taking
a look. It starts being answered by a deterministic script, with a closed
vocabulary, that runs in seconds, prints violation by field and returns an exit
code. That exit code is the gate: pipeline, CI, pre-commit hook — anything that needs
to decide "accept or reject" consults the script, not a feeling. What the script
answers is only that — conformance to the declared schema; what falls outside that
question is named, route by route, in "Scope and limits".

## What it is

A reusable skeleton (`validator_skeleton.py`) that, given a `SCHEMA` dict
(column → rules: `required`, closed `enum`, `type`), returns:

- **violation named by row and by field** (`{"line": N, "field": "x", "check":
  "enum"}`). Row checks (`missing`, `enum`, `type`, `extra-cell`,
  `missing-cell`) never put the raw value of a data cell in `field` — only
  schema column names, header names, or positions (`column-N`). Header
  checks (`unknown-column`, `duplicate-column`) echo header cell text —
  safe exactly when the row read as header is a real header. **Treat stdout as safe
  to log ONLY when header provenance is guaranteed** (the writer always emits the
  header row); the route where that assumption fails leaks raw data,
  possibly PII — see "What it does NOT catch";
- **closed vocabulary even at the structural level**: an extra cell beyond the header is
  a named `extra-cell` by position, not a silent "ok, ignore"; a row shorter than the
  header is `missing-cell` by the real name of the truncated column — flagged even
  when that column is not `required` (an interrupted write is exactly that
  case); a duplicate column in the header is `duplicate-column` with **every**
  occurrence validated — an invalid value doesn't hide behind column order, and the
  duplication is never reported only as a misleading `missing-column`;
- **`check_schema()` before any row**: a malformed `SCHEMA` (non-dict,
  non-string column, unknown rule key, non-boolean `required`, unknown
  `type` — e.g. the typo `"integer"` instead of `"int"` —, bad enum) raises
  `NotRun` → exit 2 with a named reason. A misconfigured validator has not
  evaluated anything — `NOT-RUN`, never
  a verdict;
- **a one-line JSON summary** (`status`, `rows`, `invalid`, `invalid_rows`) —
  a single source of truth, machine-readable;
- **tri-state exit contract** (table below), always closed by a
  final line that names the state literally.

The pattern comes from a mechanical labels validator used in production (checking a
labels CSV against a closed schema, no LLM in the loop, one-line summary + exit
code driving the gate). This piece extracts the generic pattern and strips everything
specific to the source project.

## Command and states

```
python3 validator_skeleton.py --csv path/to/artifact.csv
```

| Exit | State | Means |
|---|---|---|
| 0 | `VERIFIED` | ran to completion, evaluated every declared column and every row, zero violations |
| 1 | `FAILED` | ran to completion and found one or more named violations |
| 2 | `NOT-RUN` | **could not evaluate** — unreadable or empty file (no header), non-decodable bytes, embedded NUL byte (valid UTF-8, but a signature of binary garbage / wrong encoding / truncated write), malformed CSV (including a quoted field that never closes before EOF — `csv.reader(..., strict=True)` turns this into an error instead of silently swallowing the rest of the file), header with **zero** overlap with the schema (a sign of a data row read as header), or the validator itself not configured (empty or malformed `SCHEMA` — `check_schema`). Partial coverage counts as `NOT-RUN`, never as approval: a checker that couldn't look must never report "passed" |

The `2` must never be treated as "maybe it's fine" by the gate — treat it
exactly as a failure.

Fixture: `python3 fixture/run_fixture.py` (exit 0 = correct validator) — the
case-by-case table is the runner itself.

## Scope and limits

### What it catches

Thirteen fixture cases — ten CSVs against `example_instantiation.py`, one against
the standalone skeleton, two in-process directly against `validate_rows()` — covering every
state and every violation code the skeleton knows. Classes covered: value
outside the enum and empty required field; non-portable integer (`12_3` passes CPython's
`int()`, the strict ASCII regex rejects it); extra cell and missing cell; duplicate
column with the invalid value in the first occurrence; header typo (normal
path `FAILED`, never `NOT-RUN`); empty file; unterminated quotes; CSV with no
header (with an anti-echo-of-raw-data assertion); NUL byte; unconfigured
skeleton; and schema with a typo (`NotRun` naming `integer`). Exits and locks:
run the fixture.

### What it does NOT catch

Named routes, each with what resolves it (literal payloads in git history).

- **Semantic correctness of values that satisfy the schema.** `category: feature`
  on a row that describes a crash → `VERIFIED`, exit 0. The enum says `feature` is
  an allowed word, not that it's the right word for that row. Resolved by:
  human judgment (or a dedicated review stage) at another pipeline stage;
  this gate locks form, never content.
- **Consistency across rows.** Each row is validated in isolation; the same `item_id` in
  two rows → `VERIFIED`, exit 0. Resolved by: a uniqueness check in your
  instantiation (a set of already-seen `item_id` before `validate_rows`) or a
  constraint at the destination (UNIQUE in the database).
- **Raw data leak (possibly PII) under PARTIAL header
  overlap** — the route that limits the logging promise; classified as a **defect**
  in the table below. The zero-overlap guard only closes the case where *no*
  cell in the first row matches a schema column name. Just ONE match
  (e.g. the cell `notes`) is enough to send the file down the normal path and have the
  rest of that data row's cells (email, SSN) echoed as `unknown-column` in the
  stdout the gate logs. Resolved by: guaranteeing upstream that the writer always emits the
  header row (header provenance is the safety assumption for logging);
  until that guarantee exists, don't wire the validator's stdout into shared logging
  when the artifact may carry PII. Closing the class in code would
  require echoing positions instead of names in `unknown-column`/`duplicate-column`,
  destroying the header-typo diagnostic — a trade-off that is a human decision
  ([ADOPTION.md](ADOPTION.md)), not an obvious patch.
- **CSV with only a header, zero data rows** → `VERIFIED`, `rows: 0`, exit 0.
  "Every row was evaluated" is vacuously true when there are none. Resolved by:
  if your case requires a minimum number of rows (an agent that generated the header and died
  before writing data), that's a business rule (`min_rows`) in your
  instantiation — outside the skeleton's generic scope, and so "not assessed" in the
  table, not a defect.
- **Encoding tricks.** UTF-16LE read as UTF-8 falls into the NUL guard as a
  consequence (`NOT-RUN`) — this is not encoding detection; a wrong encoding *without*
  NUL in the bytes is not detected. A Unicode homoglyph in an enum (`bуg` with Cyrillic
  `у` U+0443) is caught as `enum` (exact string equality — not a bypass route).
  A value with surrounding spaces (`  bug  `) → `VERIFIED`: a deliberate `.strip()`
  before comparing; distinguishing `"bug"` from `"  bug  "` is a change to the skeleton's contract,
  not configuration.

### What only a human decides

See [ADOPTION.md](ADOPTION.md) — schema design, valid label set,
the partial-overlap route trade-off, `min_rows`, acceptance of residuals from the
coverage table.

### Coverage: promised × covered

| Promised | Covered mechanically | Not covered / known bypass | Classification |
|---|---|---|---|
| Closed vocabulary by value (`enum`, `missing`, `type`) | `violating.csv` → exit 1 (`enum` + `missing`); in-process case `type: int` → `FAILED` | value allowed by the enum but semantically wrong for the row | not assessed |
| Closed structure of row and header (`extra-cell`, `missing-cell`, `duplicate-column`, `unknown-column`/`missing-column`) | `extra_cell.csv`, `missing_cell.csv`, `duplicate_column.csv`, `typo_header.csv` → exit 1 | consistency across rows (duplicate `item_id` → `VERIFIED`, exit 0) | not assessed |
| Inability to evaluate never becomes approval (`NOT-RUN`, exit 2) | `empty.csv`, `unterminated_quote.csv`, `headerless.csv`, `nul_byte.csv`, the standalone case → exit 2; in-process schema-typo case (`"integer"`) → named `NotRun` | header-only CSV → `VERIFIED`, `rows: 0` (vacuous truth; `min_rows` is an instantiation rule) | not assessed |
| Raw data-cell value never in row checks; stdout safe to log **only** under guaranteed header provenance | row checks echo only schema names, header names, or positions; zero overlap → `NOT-RUN` with anti-echo assertion (`headerless.csv`) | partial header overlap → email/SSN echoed as `unknown-column` in stdout, exit 1 | defect |
