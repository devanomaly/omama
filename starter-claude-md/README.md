# starter CLAUDE.md

> Docs for this piece: **README** (promise, command, states, coverage) ·
> [ADOPTION.md](ADOPTION.md) (adoption, `--allow-vocab`, dictation, human
> decisions). The evidence is the re-runnable fixture; red-green history is in
> git (EVIDENCE.md up to 2026-08-19). The checker validated the reduction of
> the operator's global CLAUDE.md (ratified 2026-08-19 in the internal
> reduction round).

## The decision this piece changes

The default behavior of an agent in a team repository stops being tribal
knowledge repeated (or forgotten) every new session, and becomes a versioned
file — `CLAUDE.md` — whose rules point to tools this toolkit already ships,
not loose prose. And the shape of that file becomes checkable by script: a
rule with no tag traceable to a piece that actually exists is a sign that
internal doctrine leaked into the file.

## What it is

- `CLAUDE.starter.md` — the template (EN), ready to copy. Four sections:
  where to put the file, code conventions (piece 07, optional — not included
  in this toolkit), the card contract (piece 02 — the heading still reads
  "Bugfix requires a work order", but the body governs every `task_type`;
  a bugfix is only the one that additionally owes a `repro`), hooks
  installed in the repo (pieces 01, 04 and 10 — the last being the
  receipt-gate Stop hook that owns the close). Every rule ends with the
  `[NN]` tag of the piece it comes from.
- `check_starter.py` — deterministic checker (no LLM): `untagged-rule` (every
  rule bullet in the governed sections "Code conventions", "Bugfix requires
  a work order", and "Hooks installed in this repo" ends with a `[NN]` tag
  from the closed set `{01,02,03,04,07,08,09,10}` (the pieces this toolkit
  publishes; 05 and 06 are internal, see legend in the root README);
  accounting **per section** — a governed section with no `- ` bullets is
  `empty-governed-section`, a file with no governed section is
  `missing-governed-section`); `forbidden-vocab` (the whole file free of
  doctrine vocabulary in **PT and EN** — "pilar(es)"/"pillar(s)",
  "doutrina"/"doctrine", "manifesto", "swe-pillars", `P<n>`/`CC<n>`;
  escape hatch `--allow-vocab`, see [ADOPTION.md](ADOPTION.md));
  `leftover-placeholder` (no `<!--`/`-->` header comment and no unresolved
  `<ADJUST:`); `stale-schema` (the file names no field from the SUPERSEDED
  piece-02 schema — `allowed.files`, `allowed.commands`,
  `reproduction.required`, `work-order.yaml` — a closed lexical list of four
  literals; the card shipped today is `CARD.yaml` with
  `goal`/`non_goals`/`tier`/`task_type`/`done_when`/`verify`/`repro`).
- `fixture/` — a clean case, ten planted violations, the raw template as an
  **intentional** red ("forgotten copy" vs. "adjusted copy"), one refusal
  case and one measured PIN (the pointer-only apex file, see
  [ADOPTION.md](ADOPTION.md)); runner with regression locks.

## Command and states

```
python3 check_starter.py <path-to-CLAUDE.md> [--allow-vocab=TOK1,TOK2,...]
```

| Exit | State | Means |
|---|---|---|
| 0 | PASS | form ok |
| 1 | FAIL | one line per violation, with line and named code |
| 2 | not executable | usage error, nonexistent path, or a never-exemptable token in `--allow-vocab` |

Fixture: `python3 fixture/run_fixture.py` (exit 0 = checker correct) — the
case-by-case table is the runner itself.

## Scope and limits

### What it catches

Twelve red cases, each locked to every reason it names (locks in the runner).
Classes: rule with no tag or with a tag outside the set (including `[05]`
and `[06]`, which name internal pieces this toolkit does not ship), doctrine
vocabulary, template leftovers, heading with a trailing `:`, a governed
section absent or empty (a valid one doesn't cover its empty sibling),
allowlist masking, a never-exemptable exemption refused, and a stale
piece-02 field name anywhere in the file.

### What it does NOT catch

Named routes, each with the layer that resolves it:

- **Semantic traceability of the tag.** Any tag from the closed set
  satisfies the checker, even if it points to the wrong piece. The tag
  validates form; real traceability, no. Resolved by: human review of the
  diff.
- **Rule quality.** A bad or vague rule, well-tagged and free of forbidden
  vocabulary, passes. Resolved by: human review.
- **Rules outside the governed sections.** A bullet in a new section
  doesn't require a tag (forbidden vocabulary is still checked across the
  whole file; traceability is not). Renaming a governed heading is NOT a
  route anymore: the absence of the canonical section surfaces as a named
  `[missing-governed-section]` (and de-accenting is normalized). Resolved,
  for new sections: human review of the diff; the adopter can add the
  section to the governed set.
- **Paraphrased doctrine.** `forbidden-vocab` is a closed lexical list;
  doctrine rewritten without those terms passes. Resolved by: human review.
- **Schema drift that isn't one of the four names.** `stale-schema` is a
  closed lexical list too: it catches `allowed.files`, `allowed.commands`,
  `reproduction.required` and `work-order.yaml`, and nothing else. A rule
  describing a field piece 02 never had, or paraphrasing a superseded one
  ("the work order's file allowlist"), passes — the check proves the four
  literals are gone, never that a rule matches its piece. Resolved by: human
  review of the diff; a new literal is a new entry plus its fixture case
  (see [CONTRIBUTING](../CONTRIBUTING.md) on deny-list widening).
- **Fabricated substance.** The checker proves form; content invented to
  satisfy it (the route the starter's anti-fabrication rule forbids) is only
  caught by human review — the fixture only guarantees the RULE travels with
  the `[02]` gate in the clean example. Resolved by: human review of the
  evidence.

### What only a human decides

See [ADOPTION.md](ADOPTION.md) — hooks actually installed, repo rule vs.
dev's global, granting `--allow-vocab`.

### Coverage

| Promised | Mechanically covered | Not covered / known bypass | Classification |
|---|---|---|---|
| Every governed rule traces to a real piece via `[NN]` | tag absent/outside the set (`violating`); heading with `:` (`violating_colon`); no governed section (`violating_empty`) | semantically wrong tag passes | not assessed |
| File free of internal process vocabulary, PT and EN | "Pilar" (`violating`); same-line mask + EN "doctrine"/"pillar" (`violating_vocab_mask`); `--allow-vocab=pilar` → exit 2 | paraphrased doctrine passes | not assessed |
| No copy-paste leftovers from the template | raw template → 11 × `leftover-placeholder` (every placeholder now greppable via `<ADJUST:`) | `<ADJUST:` resolved with wrong content passes | not assessed |
| No rule pointing at a superseded piece-02 field | the four literals, anywhere in the file (`violating_stale_schema`, a byte copy of the clean case as it stood before the check existed; each literal locked on its own); the shipped template asserted free of them by a runner invariant | a paraphrase, or a field name not on the closed list | accepted limitation |
| Repo rules live in the governed sections | empty governed section flagged per section (`violating_empty_governed`, `violating_persection`); renamed/de-accented heading flagged (`violating_renamed`); numbered/`*` rule visible to the tag check (`violating_numbered`) | a rule in a new, non-governed section doesn't require a tag | accepted limitation |
