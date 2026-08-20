---
name: belief-check
description: >
  Use when an operator wants to test their own beliefs about how an EXISTING repo
  behaves against the committed tree — "am I right that X works this way?", "check my
  assumptions about this component". Takes operator-committed, falsifiable repository
  claims (claim + confidence committed BEFORE any evidence is revealed), adjudicates
  each against static committed-tree evidence at a pinned revision, and reports a
  confidence/outcome profile headlined by the sure-and-wrong risk cell. Read-only,
  static, single-session. NOT calibration. Standalone, repo-agnostic.
user-invocable: true
argument-hint: "[--component <dir>] [--claims <file|dir>] [--rev <sha>] [--no-verify]"
allowed-tools: Read, Grep, Glob, Bash, Agent
model: opus
---

# belief-check

Adjudicate an operator's own falsifiable repository claims — each frozen with a confidence **before any
evidence is revealed** — against static committed-tree evidence at a pinned revision. Read-only.
**Agent-instruction skill — you, the agent, run the phases below.**

**Charter.** Input is operator claims; the object stays the repository — *"Auditors may accept
operator-stated, falsifiable repository claims as input when conclusions remain scoped to repository
evidence."* Conclusions stay about repository evidence at the pin, never about the operator.

**Modes.** Directed only. `--component <dir>` bounds the surface; omitted, the frozen claim set is the bound
(no whole-repo sweep). **`--claims <path>` present ⇒ non-interactive**; **absent ⇒ interactive**, claims
elicited live. **Record which one you ran** — `## provenance` carries a line reading exactly
`mode: interactive` or `mode: non-interactive`; a report without it fails the run, because half the rules
below branch on the mode and an unstated mode makes them ungradable. `--rev <sha>` pins the revision; with
none given and nobody to ask, resolve `HEAD` once at session start, noting in `provenance` that it was
defaulted. `--no-verify` skips the second pass.
No `--generate`, no live stack, no transcript harvest.

**Side-effect gate — read-only, no exceptions.** Never call `Write`/`Edit`, run a mutating `git`/shell
command, bring up a stack, or execute the code under audit. Any evaluator you dispatch inherits this verbatim.

## Phase 0 — Intake and pin (enumeration, NOT judgment)

1. **Pin.** `git rev-parse --short <sha-or-HEAD>` → record the literal short SHA, never the token
   `HEAD`. Then `git status --porcelain`: a dirty tree neither blocks the run nor moves the evidence
   — note it in `provenance`, read the pinned commit anyway.
2. **Collect claims** — **1–5 in the frozen batch**, counted after Phase 1 rejections. Any surviving
   count in that range is a legal batch: a thin batch is a smaller run, not an error state.
   - `--claims <path>`: a single claim file **or a directory of them** (one claim per file). Read every
     file; `git hash-object` each in sorted path order, record that list in `provenance`. Precommitted
     **by protocol + attestation, not by construction.**
   - Interactive: elicit one at a time, asking every Phase 2 field — eliciting serially is fine,
     **revealing** anything is not (Phase 3).
   - **Zero survive Phase 1** — interactive: ask for more. Non-interactive: there is nobody to ask, so
     emit the `NO_ADJUDICATION` terminal (Phase 3) — never invent, restore or reshape a claim to reach a
     count. **More than 5** → interactive: ask which 5; non-interactive: freeze the first 5 in path order,
     rest under `does NOT cover`.
3. **Assign stable ids** in intake order (`C1`, `C2`, …) and use them everywhere.

Interactive: read no source file yet. Either mode: write nothing evaluative.

## Phase 1 — Preflight each claim (before freezing)

Reject or split claims that are **ambiguous, compound, normative** ("should", "is elegant") or **missing
time/environment scope**; reject **non-falsifiable** ones — all *before* freezing.

**Scope test — decides reject-now vs `UNRESOLVED`-later.** *Does the claim name a candidate static mechanism
— a file, function, setting or guard you could go look for at the pin?*
**No** (names none, or the operator says none exists) → reject: out of scope **on its face**.
**Yes** → **freeze it**, however unpromising. If investigation then shows only a live run could settle it,
that is `UNRESOLVED` at adjudication (*Anti-vacuity*, below), never a retroactive rejection — you may not
reject a claim for looking hard.

**If preflight reshapes or splits a claim, the operator must ratify the final wording** before it freezes —
otherwise the operator's belief silently becomes an agent-authored claim. **Interactive:** show the exact
proposed text and wait for a yes; then record the reshape on that claim's `## rubric` line as the token
`· reshaped (ratified)`. The `(ratified)` half *is* the record of the operator's yes — a rubric line
carrying `reshaped` without it fails the run, because an unratified reshape is exactly the silent
substitution this rule exists to prevent.
**Non-interactive: there is nobody to ratify** — route the claim to `## preflight-rejected` (needs
reshaping) rather than freeze wording you authored. It follows that **no rubric line in a non-interactive
report may carry `reshaped` at all**; one that does fails the run.

Rejected claims go under `## preflight-rejected` with their id and a one-line reason; never adjudicated.

## Phase 2 — Freeze each claim

Record verbatim, before any evidence read: **claim text** (exact, as ratified) · **`confidence`**
(canonical: `hunch | fairly_sure | certain`) · **falsifier** (*"contradicted if ___"*) ·
**consequence** (*"what decision or action would be wrong if this claim is false?"*) · **evidence pointer**
(optional) · **revision** (the pinned short SHA).

**The consequence is operator-authored** — propose wording; the human authors it. Never author both a claim
and its stakes. The evidence pointer does **not** bound you: seek counter-evidence outside it. Every claim
block carries its frozen consequence back verbatim in a non-empty `- consequence:` bullet; an empty or
missing one fails the run. (Only its *presence* is graded — that it is genuinely the operator's, and names
a real decision, is trust this instrument cannot check for you.)

## Phase 3 — Freeze the whole batch before revealing anything

Every claim is frozen **before any adjudication result is shown**. *"Revealing one claim's outcome before
later claims are committed contaminates them."*

When the last claim is frozen, emit on its own line, exactly: `FROZEN: <n> claims` — a whole line, nothing
before or after it, never inline in a sentence. `<n>` is the size of the frozen batch with rejected claims
excluded, so **1 ≤ n ≤ 5**, and it must equal both the number of `### <id>` blocks under `## claims` and the
number of per-claim lines under `## rubric` — a marker that disagrees with what the report actually
adjudicates fails the run. `n = 0` is legal **only** in the `NO_ADJUDICATION` terminal below.
**Interactive: emit it twice** — in-session at the freeze, and again in the report below; both must carry
the same `<n>`. Inside the report envelope the marker appears **exactly once**. A report carrying no marker
fails the run outright.

**Non-interactive.** The claim file's attestation + hash (Phase 0) *is* the freeze; the marker **records**
it, it does not perform it. So the marker appears once, in the report, and you may read the tree before
emitting it — no operator remains to contaminate — provided no outcome token precedes it.

**Reveal-leak rule — mechanical, read it twice.** The three canonical outcome tokens
`SUPPORTED_WITHIN_SCOPE`, `CONTRADICTED`, `UNRESOLVED` must not appear **anywhere** in the session output
before that marker — not in prose, not in a heading, not in a rubric restatement, not inside a quoted claim
text, not in an "early read". It is a bare-token scan over everything before the marker: an innocent echo of
the enum fails exactly like a real leak. Therefore:

- Place the marker immediately after `## provenance`'s content — the provenance line and the `mode:` line —
  and **before every other section**, including
  `## rubric`, which legitimately restates the enum and must therefore come after it.
- Before the marker, narrate without verdict vocabulary at all: *"claim 3 frozen"*, *"batch complete"*.
- **There is no such thing as a quoted marker.** The report body carries no code fences at all (Output
  rules), so every `FROZEN: <n> claims` line in it is an emission: it bounds the scan and it counts.
  Write about the marker without rendering one — *"the freeze line, with the batch size"*.

**`NO_ADJUDICATION` terminal — non-interactive, zero survivors.** When every supplied claim is rejected in
Phase 1 and there is nobody to ask for more, the run still has a result to report: *nothing was
adjudicable*. Do not fail silently and do not skip the report. Emit the full envelope, with
`## preflight-rejected` listing every rejected claim and its reason, `FROZEN: 0 claims`, `- none` under
`## claims`, and a summary whose headline and every matrix cell read `none`. This is the one shape in which
`n = 0` is legal; in interactive mode it never arises, because the answer there is to ask for more claims.

## Phase 4 — Adjudicate, then reveal

Only now inspect the evidence. For each frozen claim: (1) assemble evidence from the pinned commit
and assign `outcome` × `evidence_state` per *Verdicts & evidence semantics*; (2) unless `--no-verify`, run
*The skeptical second pass*; (3) draft its claim block. Reveal **all** outcomes together, only once
every claim is done. If `HEAD` moves mid-session, **keep reading the frozen commit** —
never silently switch; a changed pin starts a new session.

## Verdicts & evidence semantics

**Two orthogonal axes** — code, git history and committed config can conflict; not one oracle.

- **`outcome`** — `SUPPORTED_WITHIN_SCOPE` (scoped evidence supports the claim at this revision —
  *not* "proven true") · `CONTRADICTED` · `UNRESOLVED` (inconclusive, or needs evidence v1 does not gather).
- **`evidence_state`** — `CONSISTENT` · `CONFLICTING` (sources disagree, e.g. a stale committed config vs the
  authoritative implementation).

Conflict is **not** a third outcome: a claim can be `CONTRADICTED` with `CONFLICTING` evidence — one source
dissents, the verdict stays decisive.

**Substrate — committed-tree only.** Read all static evidence from the **pinned commit** via
`git show <sha>:<path>`, **never** from the working tree: a SHA does not describe a dirty tree.

| Need | Command (at the pin) |
|---|---|
| enumerate paths | `git ls-tree -r --name-only <sha> -- <component>` |
| find sites **+ line numbers** | `git grep -n <pattern> <sha> -- <pathspec>` |
| read a file | `git show <sha>:<path>` |
| history claims | `git log --oneline <sha> -- <path>` |

`Glob`/`Grep`/`Read` may orient you in the working tree, but **no evidence bullet may rest on them** —
re-derive every quoted line and number at the pin.

**Tier per evidence item, not per verdict** — one adjudication may mix them. Tag each `- evidence:` bullet
with exactly one canonical token, never translated: `Observed` · `Inferred` · `Unverifiable-without-running`.

**Cite every source the verdict rests on** — one `- evidence:` bullet per source, so a claim resting on two
disagreeing sources cites **both**, each with its own path and lines. Use `path:line` **when applicable**;
`UNRESOLVED` and history findings may instead carry a **search boundary** (pathspec + patterns searched at
`<sha>`) or `commit:path:line` — never invent a `path:line` for what static evidence cannot settle. A
negative search can be **decisive**: *no caller of `X` anywhere at `<sha>`* is `Observed`, not `Inferred`.

**Read the mechanism, not the keyword.** Before writing `SUPPORTED_WITHIN_SCOPE`, name and quote the code
path that *enforces* it: a parameter accepted but never consulted protects nothing; a comment describing a
guard is not a guard.

**Anti-vacuity.** Every **statically decidable** claim gets a decisive outcome. `UNRESOLVED` is for what
static evidence cannot settle — load, timing, concurrency, live topology — never a hedge *(needs live
stack; out of v1 scope)*. A claim that passed Phase 1's scope test but did not resolve belongs
**here**, not `## preflight-rejected`.

## Confidence/outcome summary

The **`certain` × `CONTRADICTED` risk cell is the headline** — the sure-and-wrong claims. The headline
line carries **the ids and nothing else** (comma-separated, or `none`): it is generated from the machine
record and compared to your line character for character, so per-id narration goes in the claim blocks the
headline names, never on that line. The skeleton below carries the rest of the shape.

**The summary is computed from the claim blocks, never narrated alongside them.** Every id in the headline
and in each of the nine matrix cells is exactly the set its `confidence × outcome` pair selects from
`## claims` — `none` where that set is empty, every graded id somewhere, no id in two cells. A summary that
disagrees with the blocks above it fails the run: this table is the report's one aggregate claim, so it is
graded like any other. Three ways that is easy to get wrong, all of which fail the run:

- **Only real ids.** Every id named in the headline, the `CONFLICTING evidence` list and the
  `Second-pass disagreements` list must have a block above it. Inventing a sure-and-wrong claim is exactly
  as false as dropping one.
- **The matrix has exactly three rows** — one per confidence. A second row for the same confidence is not a
  restatement, it is a contradiction.
- **Both list lines are reconciled too**, not just the headline: `CONFLICTING evidence` lists exactly the
  ids whose block reads `evidence_state: CONFLICTING`, `Second-pass disagreements` exactly those whose
  `- second-pass:` value contains `DISAGREES` — `none` when the set is empty.

**This profile is a risk signal, NOT calibration.** Claims are operator-selected (no sampling frame),
confidence is ordinal not probabilistic, *n* is tiny. It says nothing beyond *these* claims at *this*
revision — never generalize it about the operator.

## The skeptical second pass

Default-on; `--no-verify` disables it, recorded per claim. It is a **run-level** flag: either every claim
records `skipped (--no-verify)` or none does. A report skipping the second pass on *some* claims — above
all on the `certain` or `CONTRADICTED` ones the dispatch rule below exists for — describes a run that
cannot have happened, and fails. **Weighted to refute `SUPPORTED_WITHIN_SCOPE`** —
a false SUPPORTED reinforces a wrong claim, the worst error this instrument makes.

- **In-session by default — a second look, not a blinded pass.** Re-derive the evidence from the pin, from
  the claim text alone, ignoring the first pass's reasoning and search path. **Search first for a path on
  which the claim fails**; only when that comes up empty may you write `SUPPORTED_WITHIN_SCOPE`. Be exact
  about what this buys: same agent, same context, self-instructed disregard. It catches a shallow search or
  a keyword-matched verdict; it does **not** remove your own bias, and calling it "blinded" would be a
  claim this path cannot support.
- **Dispatch a separate evaluator — REQUIRED, not optional — whenever any of:** (a) the frozen
  `confidence` is `certain`; (b) your first-pass `outcome` is `CONTRADICTED`; (c) the in-session second pass
  disagreed with the first pass. A *separate evaluator* is defined by its properties, not by any one tool:
  a **fresh context** that shares none of your reasoning, holding **read-only** access to the repo, given
  **only** the blinded brief below. The `Agent` tool is the usual mechanism; where it is unavailable, a
  separate read-only CLI process (e.g. `claude -p` with tool restrictions) satisfies the definition —
  re-reading your own analysis in the same context never does. If no dispatch mechanism exists in your
  environment at all, you cannot satisfy this rule: record `second_pass.mode` truthfully as `in-session`,
  state the escalation that did not run in `## deviation note`, and expect the run to fail its
  `second-pass-dispatched` rows — a disclosed failure is the correct outcome there, not a reworded green. Those are the three cases where being wrong is most expensive — a
  sure-and-wrong claim, a verdict that overturns a belief, and a claim already in dispute — so **recording a
  bare `DISAGREES` without dispatching fails the run: disputed ⇒ escalate.** (Since v1.5 a Phase-1 reshape
  no longer triggers dispatch by itself: the operator ratified the wording and the rubric line records it.
  A reshaped claim reaches dispatch through (a)–(c) like any other.)
- **The dispatched evaluator is blinded by its brief.** The brief carries **only** the ratified claim text,
  the pinned short SHA, the component pathspec, the read-only prohibition, that same
  **search-first-for-a-failing-path** instruction, and the instruction to assemble its own evidence and
  return `outcome` + `evidence_state` + per-item tier + `path:line` citations. It must **not** receive the
  operator's confidence, your first-pass outcome, your evidence bullets, the falsifier, or the consequence —
  **and the brief must forbid it to read them**, along with any report, expectations file (`EXPECTED.md`) or
  eval artifact on disk, and must **pass these same constraints down** to anything it dispatches in turn.
  Withholding is not blinding: it holds `Read`/`Grep` over the same repo, and the claim file, freeze record,
  prior report and any expectations file all sit on disk. **A broken second pass is reported as broken,
  never counted as agreement.**
- **Disagreement is surfaced, never silently resolved.** Record both readings in the `- second-pass:`
  bullet and list the claim under "Second-pass disagreements". If the cited mechanism decides it, report
  that outcome and keep the dissent visible; if nothing at this revision does, the `outcome` is
  `UNRESOLVED` and both readings are cited.
- **Record it in exactly one of these five forms** — the `- second-pass:` value is a machine field and
  nothing else parses:
  `agrees` · `agrees — <note>` · `DISAGREES — <its outcome and reason>` · `skipped (--no-verify)` ·
  `dispatched — agrees[; <note>]` · `dispatched — DISAGREES[; <its outcome and reason>]`
  (the first two are one form, `agrees` with an optional note). Every value required by the dispatch rule
  above must begin `dispatched — `. The summary's `Second-pass disagreements` line lists **exactly** the ids
  whose recorded value contains `DISAGREES`, or `none`.

## Language

Detect the operator's language from their claims and mirror it in human-facing prose (probes, explanations,
narrative, rejection reasons). **Canonical, never translated** — the machine layer: the confidence enum, the
`outcome`/`evidence_state` tokens, the tiers, the envelope headers, the `FROZEN: <n> claims` marker. A
display label may appear in prose (`certain` → "certo") but **never in a machine field** (Output rules).
**Verbatim** (it is evidence): code, git output, config.

## Output

One markdown report — the **assessment envelope**. *You* write no files: emit it as your reply (a harness
may save what you emit; that is the harness writing, not the skill). The seven **graded** headers must
appear as `##` headings, spelled and cased exactly as below; a missing one fails the run (order is
convention — follow the skeleton, but only presence is checked).
The skeleton shows **eight**: those seven plus `## preflight-rejected`, which is **not** one of them —
always emitted, holding `- none` when nothing was rejected. Nine rules the skeleton cannot show:

- **The report body carries NO code fence — none, anywhere.** No line of it may begin with a
  ```` ``` ```` or `~~~` run (indented up to three spaces); the machine record at the very end is the
  file's one and only fence. The
  fenced block below shows the *shape*; your report is not itself fenced. This is a flat ban, not a
  judgement call about what a fence encloses: quote code with **inline code spans** (`` `coll.update_one(` ``),
  and quote a longer mechanism by citing its `path:line` and naming it in prose. A fenced report used to
  fail because it had no headers; it now fails because it has a fence.
- **Machine fields carry the bare canonical token alone, to end of line** — `- confidence:`,
  `- outcome:`, `- evidence_state:`, one bullet each per claim block. No bold, no backticks, no
  parenthetical, no display label or translation. `- outcome: **CONTRADICTED**` and
  `- confidence: certain ("certo")` are both unparseable and fail the run — and so is a **second**
  bullet of the same field in one block, whatever it says: the per-value line counts must equal what the
  machine record declares, so a contradictory twin is a failing count, not a footnote.
- **Never begin a line with a declared header token outside its own `##` heading**, in any of the `#`,
  `- `, `` - ` `` or `**` forms. A stray `- claims: 5 collected` is read as the start of the `claims`
  section, silently voiding every claim block after it. Keep `## provenance` to its two unbulleted lines —
  the provenance line, then `mode: <interactive | non-interactive>`.
- **Prose may not look like a machine field.** The body is a closed world (*The machine record*): every
  line either IS one of the canonical lines the record generates, or is ordinary prose. So a narrative
  bullet must not open `- <word>:` — write `- the second pass re-derived every citation`, never
  `- summary: every citation re-derived` — and must not open with a **field name** at all, whatever
  follows it (`- outcome (reconciled) — …` is a second outcome field, not a footnote). Ordinary colons
  **mid-sentence** are free (`Note: one commit was read; scope: the substrate directory`), as are
  blockquotes, paragraphs and any other bullet. No zero-width or bidirectional character, and no HTML
  comment, anywhere in the body:
  a line that is in the file and not on the page is a hiding channel, not a formatting choice.
- **The provenance line's `claims:` field and the `mode:` line must agree** — `claims: interactive` with
  `mode: interactive`, `claims: file …` / `claims: dir …` with `mode: non-interactive`. The mode is a fact
  about the invocation (`--claims <path>` present ⇒ non-interactive), not a free-text declaration; a report
  whose two fields disagree, or which omits the `claims:` field, fails the run.
- **Every per-claim `## rubric` line ENDS with `· revision <short-sha>`** — last field, after the
  optional `· reshaped (ratified)` token, because that is the field the checker compares by
  `endswith`: a `revision <sha>` mentioned anywhere earlier in the line satisfies nothing. The same
  literal short SHA on every line **and in `## provenance`'s `assessed at commit <short-sha>` field
  specifically**, which appears exactly once (the claim files' hashes live in that line too, and a second
  `assessed at commit` line is two pins for one run), never the token `HEAD`. One run reads one commit.
- **The rubric line's `confidence` is the frozen one** — recorded before any evidence was read — so each
  line **starts** `- <id> · <confidence> ·` and the claim block's `- confidence:` bullet repeats that same
  token. The freeze record and the adjudication disagreeing about what the operator committed to fails the
  run.
- Every frozen id appears **exactly once**: a full `### <id>` block under `## claims`, or a line under
  `## preflight-rejected` — never both, never neither.
- Every `- evidence:` bullet has one entry in the machine record — same `path`, same `line`, same tier —
  and an anchor is satisfied only by an entry whose path AND line both land inside it. A line number cited
  beside one file no longer counts toward another. This is **checked**, per claim block: each recorded item
  that cites a line must be rendered by exactly one bullet in its own `### <id>` block, opening
  `- evidence: <path>:<line>` (a range `<lo>-<hi>` is fine when `<lo>` is the recorded line) and carrying
  its `(<tier>)`; the block's bullet count must equal the record's, and an `- evidence:` bullet that sits
  in **no** claim block fails the run wherever you put it. Cite a **search boundary** as prose — it records
  `line: null`, so its wording is free, but it must carry that item's **tier token** and must contain **no
  `<path>:<line>` at all**: a boundary is exactly the shape static evidence cannot pin to a line, so a
  locator rendered into a boundary slot is an invented citation, whatever the prose around it says. The
  same holds one bullet over: **every** `<path>:<line>` on a lined citation — including one written into
  the free prose *after* the tier — must be a citation the record made. The tail is where you explain the
  mechanism, not where you cite a second file.
- `## does NOT cover` is required and may read exactly `None within the declared scope.` — state the scope.

```markdown
# belief-check assessment

## provenance
assessed at commit <short-sha> · scope: <component path, or "repo"> · claims: <interactive | file <path> sha <hash> | dir <path>, <k> files, shas <h1, h2, …>> · working tree: <clean | dirty — evidence still read from the pinned commit>
mode: <interactive | non-interactive>

FROZEN: <n> claims

## rubric
The frozen batch, one bulleted line per claim — id first, confidence second, revision last:
- <id> · <confidence> · <falsifier> · <consequence> · <evidence pointer> <· reshaped (ratified) — only if Phase 1 reshaped it, interactive only> · revision <short-sha>
Bar: static committed-tree evidence only at <short-sha>; outcome ∈ {SUPPORTED_WITHIN_SCOPE, CONTRADICTED,
UNRESOLVED} × evidence_state ∈ {CONSISTENT, CONFLICTING}; per-evidence tier; second pass weighted to refute
SUPPORTED_WITHIN_SCOPE, escalated to a dispatched evaluator for certain, CONTRADICTED and disputed claims.

## preflight-rejected
- <id> — "<claim text>" — REJECTED: <one or more, comma-separated: ambiguous | compound | normative | missing scope | non-falsifiable | out of scope (names no candidate mechanism)> — <one line why>
  <the `<id> — "<claim text>"` half is the record's `preflight_rejected[].claim` verbatim; the reason after
   the colon is yours. One bullet per rejection, no other bullet in the section, and exactly `- none` when
   nothing was rejected>

## claims
### <id> — "<claim text>"     <the record's `claim` verbatim — this whole line is regenerated and compared>
- confidence: <hunch | fairly_sure | certain>
- outcome: <SUPPORTED_WITHIN_SCOPE | CONTRADICTED | UNRESOLVED>
- evidence_state: <CONSISTENT | CONFLICTING>
- evidence: <path>:<line or lo-hi> (<Observed | Inferred>) — <the mechanism you read>
- evidence: <search boundary — pathspec + patterns searched at <short-sha> — or commit:path:line> (<Observed for a decisive absence | Unverifiable-without-running when only a live run settles it | Inferred>) — <what it establishes; a boundary bullet carries its tier token and NO <path>:<line>>
- evidence: <one further bullet per source the verdict rests on — both sides of a conflict>
- falsifier: contradicted if <the operator's frozen falsifier>
- consequence: <the operator's frozen consequence — the decision that would be wrong if the claim is false>
- second-pass: <agrees | agrees — <note> | DISAGREES — <its outcome and reason> | skipped (--no-verify) | dispatched — agrees<; note> | dispatched — DISAGREES<; its outcome and reason>>

## confidence/outcome summary
**Headline — `certain` × `CONTRADICTED`:** <comma-separated ids, or the bare word none — nothing else on this line>

| confidence \ outcome | SUPPORTED_WITHIN_SCOPE | CONTRADICTED | UNRESOLVED |
|---|---|---|---|
| certain | <ids> | <ids> | <ids> |
| fairly_sure | <ids> | <ids> | <ids> |
| hunch | <ids> | <ids> | <ids> |

- CONFLICTING evidence: <ids, or "none"> · Second-pass disagreements: <exactly the ids whose second-pass value contains DISAGREES, or "none">
- Risk signal over <n> operator-selected claims at one revision; not a measurement of the operator.

## Re-validate when:
- any cited path changes after <short-sha> (`git log <short-sha>..HEAD -- <cited paths>` is non-empty)
- a claim's wording is revised, or the operator's confidence in it changes
- an UNRESOLVED claim becomes decidable (live evidence gathered by other means)

## reproduction
- pin <short-sha> · scope <pathspec> · claims <file + hash, or the frozen list above>
- `belief-check --component <dir> --claims <file> --rev <short-sha>`, plus each citation's git command

## does NOT cover
- runtime / live-stack behavior, performance, timing (static evidence only)
- anything outside <pathspec> or absent from <short-sha>; <claims deferred past the batch cap>
```


## The machine record

**End every report with exactly one machine record** — a fenced block whose opener line is exactly
```` ```json belief-check-record ```` (at column 0, nothing else on the line), then **one JSON object**,
then a bare ```` ``` ```` closer, then nothing. It is the **last thing in the file**: text after the closer is a second
adjudication with no record, and fails the run. It is also the file's **only** fence (Output rules).

The record is what is graded. **The prose above it must render exactly what the record says** — the
headline, the nine matrix cells, the `FROZEN: <n> claims` line(s), the `mode:` line, the
`assessed at commit <short-sha>` field, one `### <id>` heading per frozen claim, the `- confidence:` /
`- outcome:` / `- evidence_state:` bullets **in the block of the claim they belong to**, that block's
`- evidence:` citations, and each rubric line's `- <id> · <confidence> ·` opening and
`· revision <short-sha>` ending. Every one of those is regenerated from the record and compared to your
lines; a divergence — a headline that drops a sure-and-wrong claim, a second contradictory bullet, two
blocks that swap verdicts while the totals still add up, an invented `file:line`, a smuggled duplicate
block, a decoy revision — fails the run and names the string it expected. **Write the record first, then
render it.** Nothing you can say in the prose changes the verdict; it can only contradict it.

Indenting a line, doubling a space inside a heading, or wrapping it in `**` or `__` hides nothing: the
comparison normalizes whitespace, emphasis (`*` and `_` alike, wherever the run reads as a delimiter and
not as part of a word such as `fairly_sure`), list markers (`*`, `+` **and the ordered forms** `1.` / `1)`),
inline HTML tags, **HTML character references** (`&#58;` is a colon) and unicode punctuation twins
first — colon, dash, interpunct **and vertical-bar** twins, so a table drawn with box-drawing pipes (`│`)
is a table. ` ### C6`, `##  claims`, `***Headline …***`, `__Headline …__`, `* outcome: …`,
`1. outcome: …`, `<b>Headline …</b>`, `│ certain │ … │`, `- C1&#58; …` and `- outcome：` are all counted as
the lines they render as. Writing machine punctuation as a character reference is itself a failing row
(`body:char-reference`), like a zero-width character: it hides the field from a reader of the source and
changes nothing on the page.

**The body is a closed world.** After that normalization every line of your report is one of two things:
a canonical line the checker regenerated from the record, or ordinary prose. **A machine-shaped line the
record cannot account for fails the run**, named by line number — there is no third category and no
tolerance. Machine-shaped means any of: a heading in **any** of markdown's three spellings — an ATX
heading at any level (`#`…`######`), a **setext** heading (a line underlined with `===` or `---`), or a
raw `<h1>`…`<h6>` tag — whose text names a section or a claim id; a table line, **edge pipes or not**
(any pipe-carrying line beside a `|---|` delimiter row); a `- <token>:` bullet; a bullet whose **first
word is a field name** (`outcome`, `confidence`, `evidence_state`, `second-pass`, `evidence`,
`consequence`, `falsifier`) whatever punctuation follows it; a `- <id>:`, `- <id> ·`, `- <id> —` or
`- <id> (` bullet; a bullet in the **pinned rejection format** — `- … — REJECTED:` — **wherever it sits**,
not only inside `## preflight-rejected`; a line carrying `FROZEN:`, opening `mode:`, or carrying
`assessed at commit`; a line
rendering as `Headline …`, **or any emphasis-led line naming the headline and a `<confidence>` ×
`<outcome>` cell** (`**Reconciled headline — …:** none`); an **emphasis-led line whose text names a
section or a claim id** (`**claims**`, `**C1 — "…" — reconciled: SUPPORTED_WITHIN_SCOPE**`). So a decoy
`- C1: on reconciliation this reads SUPPORTED_WITHIN_SCOPE`, a `- C1 — "…" — VERIFIED: …` bullet, a
`#### C1 — "…"` restatement, a `- outcome (reconciled) — …` twin, a `1. outcome: …` twin, a fourth
matrix row **written without its trailing pipe**, a `claims` heading underlined with `======`, a stray
`- evidence:` in the summary and a second `Mode:` line all fail — not because each was anticipated, but
because none of them is derivable from the record. The formats that are pinned, exactly:

- `### <id> — "<claim text>"` — the claim text is the record's `claim`, character for character.
- `- confidence:` / `- outcome:` / `- evidence_state:` — the bare canonical token, one per block.
- `- second-pass:` — the value **opens** with what the record recorded: `agrees` · `DISAGREES` ·
  `dispatched — agrees` · `dispatched — DISAGREES` · `skipped (--no-verify)`. Your note follows it freely;
  the mode and the verdict do not.
- `- consequence:` / `- falsifier:` — exactly one non-empty bullet each, per block.
- `- evidence:` — inside its own claim block, opening `- evidence: <path>:<line>` with its `(<tier>)`; a
  boundary bullet carries its tier token and no `<path>:<line>` (*Output* rules above), and **names the
  same file the record's boundary item names** — no file on either side is fine, a different file is not.
  The wording around it stays yours; the file is the citation, not decoration.
- `- <id> — "<claim text>" — REJECTED: …` under `## preflight-rejected`, one per record rejection, or
  exactly `- none`. **This format is owned by that section**: a line wearing it anywhere else in the
  report is a fabricated entry inventing a claim the record never froze, and fails.
- the headline, the matrix header, its `|---|` separator and its three data rows — **adjacent, in that
  order**: a header parked elsewhere heads nothing.

**What stays free, and it is most of the report:** paragraphs, blockquotes, headings — and bold lead-ins —
that name something of your own (`## session log`, `**Reading note.**`), every bullet that does not open
`- <token>:` or with a field name, the reason on a rejection, the note on a second pass, the mechanism
prose after an evidence tier, and both free-form sections. None of it is graded — which is exactly why
none of it may wear a machine field's clothes. Write `- the evidence was re-derived`, never
`- evidence (re-derived) — …`.

**What this checking guarantees, and what it cannot.** It guarantees the report **contains the truth**:
every canonical line is regenerated from the machine record and matched and counted exactly; every
line that renders as a machine element **through a channel the checker models** must be one of them;
the record's **claim set is the operator's frozen batch** — its adjudicated claims plus its preflight
rejections are exactly the claims that were submitted, one entry each, so a claim nobody froze cannot be
adjudicated and a rejection cannot stand in for a claim it does not name; and the record's **citations,
quotes, frozen claim text (adjudicated *and* rejected) and mode** are reconciled against the repository
tree, the operator's frozen wording and the invocation — not against themselves. Write the record and it
will be checked against the world, not merely against your own prose.

It does **not** guarantee the prose contains **no lies**. Rendering-equivalence over the whole of
CommonMark + GFM + inline HTML is not decidable by a static, stdlib checker, so an author who is
deliberately composing a decoy can always reach for a channel that is not modelled — **link-reference
definitions** (`[note]: …`, whose text renders where the reference sits), **footnote definitions**,
raw `<table>` / `<dl>` blocks, image alt text, nested-blockquote restatements. Read the prose as prose.

Nor does it reach the record fields **no external artifact can falsify**, and you should know exactly
which those are rather than assume the record is fully bound: `consequence` and `falsifier` are checked
for **presence only** — whether the stakes you state are the operator's is trust this instrument cannot
check; the record's `known_false` and `kind` are **not** graded (ground truth is the fixture's to declare,
and the hard gates read it there); a `quote` that names **no identifier and no delimited literal** is
grounded by nothing — **on every claim, whatever its outcome** — because a faithful quote is usually a
paraphrase of the mechanism and a verbatim rule would reject the very report this skill instructs you to
write; and for a lined item **outside every declared anchor**, grounding is **file-level**, so where in
that file the name lives is not checked — a true token cited beside the wrong line still passes. A weak
verdict is *not* a weaker binding: an `UNRESOLVED` claim's citations are grounded exactly like a
`CONTRADICTED` one's. The threat model this instrument is
built for is **agent drift and laziness** — a run that stops doing the work and pads the report —
**not forgery**.

Keys — all required, no others accepted (an unknown key fails, so a field cannot ride along):

- `belief_check`: `"1.5"` · `mode`: `interactive | non-interactive` — **the invocation's mode, and it is
  checked against the invocation**, not taken on your word: a run whose claims arrived as precommitted
  files is non-interactive, and recording `interactive` there fails the run (it would turn a reshape
  nobody ratified into a ratified one) · `revision`: the literal short SHA
  (7–40 lowercase hex — the token `HEAD` cannot be recorded) · `component`: the scope you bounded.
- `frozen`: `{"n": <int>, "claim_ids": [<id>, …]}` — `n` equals the number of entries in `claims` and the
  number of ids, **1 ≤ n ≤ 5**, or the `NO_ADJUDICATION` terminal (`n = 0`, non-interactive, `claims`
  empty, `preflight_rejected` non-empty).
- `claims`: one object per frozen claim, each with `id` · `claim` (the ratified text) · `confidence` ·
  `consequence` · `falsifier` · `known_false` (bool) · `kind` — exactly one of `false` | `true` |
  `unresolved` | `conflict` | `greptrap` | `nonfalsifiable` (a closed vocabulary: the closest label for
  what the claim turned out to be, not free prose — `unresolved` not "unresolvable", `conflict` not
  "conflicting") · `reshaped` (bool) · `ratified` (bool) ·
  `outcome` · `evidence_state` · `evidence` · `second_pass`. `claim` is **the operator's frozen wording**
  — the text as submitted, or the reshaped text they ratified, and never a tidier sentence you preferred:
  where the operator's own wording is recoverable (a precommitted claim file, a fixture manifest), the
  record is reconciled against it, and a claim nobody froze fails the run with `reshaped: false` as its
  own indictment. A **reshaped** claim must be `ratified` and
  interactive; ids are unique and match `frozen.claim_ids` exactly.
- `evidence`: one object per source the verdict rests on — `{"path": …, "line": <int or null>,
  "tier": "Observed | Inferred | Unverifiable-without-running", "quote": "<the line you read>"}`. The tier
  is **per item** and mandatory; `line` is `null` for a search boundary, which is the only shape with no
  line. An anchor is satisfied only by an item whose path *and* line both land inside it. Two further
  bindings, so that an item you did not actually read cannot be written down: a `path` that cites a
  **line** must name a file that **exists** at the pin — a plausible `file:line` for a file that is not
  there fails the run — and the `quote` must be **grounded**: any identifier or backtick/quote-delimited
  literal in it has to actually appear in the source you cited. The bound is tighter inside a declared
  anchor than outside one, because that is where the fixture's premise ends: a quote on an item landing
  **inside an anchor** is checked against that anchor's **line range**; a quote on a **lined item outside
  every anchor** is checked against the **whole cited file** (the file is known to exist; its unanchored
  line is not something the manifest declares). Both bindings apply to **every claim**, whatever outcome
  it reached and whether or not it declares an anchor — an `UNRESOLVED` verdict buys no exemption.
  Paraphrase the mechanism freely; do not attribute to a source a name or a value it does not contain.
- `second_pass`: `{"mode": "in-session | dispatched | skipped", "verdict": "agrees | DISAGREES",
  "note": "…"}` — `dispatched` is REQUIRED whenever the frozen `confidence` is `certain`, the `outcome` is
  `CONTRADICTED`, or the verdict is `DISAGREES` (*The skeptical second pass*). `skipped` is `--no-verify`,
  and it is all claims or none. **`skipped` with `DISAGREES` is rejected outright**: `skipped` says the
  second pass never ran and `DISAGREES` says it ran and dissented, so the pair describes a run that cannot
  have happened — and `--no-verify` exempts the `certain`/`CONTRADICTED` legs of the dispatch rule, never
  the disputed one.
- `preflight_rejected`: one `{"claim": …, "reason": …}` per rejected claim, matching `## preflight-rejected`.
  A frozen id may not appear here. `claim` opens with **that one claim's id** and carries **the operator's
  own wording** (`<id> — "<claim text>"`): one entry never speaks for two claims, and where the wording is
  recoverable the rejected text is reconciled against it exactly as an adjudicated `claim` is — screening
  out a belief nobody submitted fails the run. Together with `claims`, this array **accounts for the whole
  submitted batch and nothing else**: every claim the operator froze is adjudicated or rejected, exactly
  once, and neither array may carry an id nobody submitted.

```json belief-check-record
{
  "belief_check": "1.5",
  "mode": "non-interactive",
  "revision": "<short-sha>",
  "component": "<pathspec, or \"repo\">",
  "frozen": {"n": 1, "claim_ids": ["C1"]},
  "claims": [
    {
      "id": "C1",
      "claim": "<the ratified claim text>",
      "confidence": "certain",
      "consequence": "<the operator's frozen consequence>",
      "falsifier": "<the operator's frozen falsifier>",
      "known_false": false,
      "kind": "false",
      "reshaped": false,
      "ratified": false,
      "outcome": "CONTRADICTED",
      "evidence_state": "CONSISTENT",
      "evidence": [
        {"path": "<path>", "line": 12, "tier": "Observed", "quote": "<the line you read at the pin>"}
      ],
      "second_pass": {"mode": "dispatched", "verdict": "agrees", "note": "<what it re-derived>"}
    }
  ],
  "preflight_rejected": [
    {"claim": "<id> — \"<claim text>\"", "reason": "<why it never froze>"}
  ]
}
```
