---
name: triad-check
description: >
  Use when docs, docstrings, specs, comments, or tests may have drifted from the code
  they describe — a stale architecture doc, a docstring claiming a guard the code lacks,
  a test asserting behavior the code no longer has, or a doc describing unbuilt/future
  behavior. Audits the tests↔code↔docs triangle for contradictions against a frozen bar;
  the doc/spec↔code (or test↔code) mismatch is the finding. Read-only by default;
  --generate seeds/accretes TRIAD_MAP.md. Standalone, repo-agnostic.
user-invocable: true
argument-hint: "[path] [--component <dir>] [--scope changed|all] [--vertex doc|code|test] [--generate] [--no-verify | --depth quick]"
allowed-tools: Read, Grep, Glob, Bash, Write, Edit, Agent, TodoWrite
model: opus
---

# triad-check

Assess a repo's (or `--component <dir>`'s) tests↔code↔docs self-consistency against a frozen bar;
optionally produce/accrete a `TRIAD_MAP.md`. Read-only by default. **Agent-instruction skill — you, the agent, run the phases below.**

**Modes.** `--scope all` (default) sweeps the whole target; `--scope changed` ratchets on the
diff vs the merge-base (clean-as-you-build). Directed: `--vertex` names the **primary vertex** —
`doc` = spec/doc-conformance (is the code true to the doc?); `code` = drift/coverage (is the doc/test
true to the code?); `test` = test-fidelity. The reconciliation *direction* changes the finding.
Verification is ON by default; `--no-verify` / `--depth quick` skips Phase 3.

**Side-effect gate.** The default run mutates nothing: do **not** call `Write`/`Edit` unless
`--generate` is set and the Output write-gate passes.

## Phase 0 — Substrate detection (enumeration, NOT judgment)

Enumerate the three vertices for the surface — never just one:
- **Code:** the modules/functions in scope (Grep/Glob for the symbols).
- **Tests:** unit/integration/e2e files exercising that code (by import, by name, by `test_`/`*.spec.*`).
- **Docs:** docstrings, module headers, `README`/`docs/` pages, ADRs, design specs, and **code comments that make behavioral claims**.

Produce the enumeration: **claim/assertion × vertex × site (`file:line`)** — every behavioral claim a
doc/comment makes, every behavior a test asserts, each anchored. Do not yet judge whether any is true.

**Sweeping-scope exclusion (`--scope all` only):** skip synthetic corpora that are *test input*, not
the project's own triad — `test-fixtures/`, `fixtures/`, `examples/`, intentional-bug corpora. An explicit
`--component <path>` overrides this (directed beats sweeping): if the invoker names a path, analyze it.

If there are genuinely no load-bearing doc/test claims to reconcile against the code (pure undocumented,
untested scratch) → still emit the **full assessment envelope** (canonical headers, Output below) whose
`findings` is the single entry **"no triad surface — nothing to reconcile"**, then stop.
(Absence is a first-class result, not silence.)

## Phase 1 — Freeze the bar (before any evaluative read)

Establish the invariant set, then **freeze it** before grading (anti-bias: you may not excuse a drift
because the doc is old or the test is convenient).

- **Directed + established:** if the repo declares the contract (a spec, an ADR with `Re-validate when:`,
  an API doc), load it as the bar and reconcile the code/test against it.
- **Exploratory (no prior bar):** co-discover. For each behavioral claim, *propose* the reconciliation —
  e.g. *"the docstring says writes are guarded by X; the code's write filter omits X → candidate: the
  doc is the contract and the code is buggy, OR the doc is stale — which?"* **You only propose; the human
  authors the consequence** ("what breaks if this is false?") before it freezes. Never launder both the
  claim and its stakes.

**Default Layer-1 catalog** (vendor-neutral; use when nothing else is declared):
1. **doc↔code consistency** — every load-bearing doc/spec/comment claim about behavior is true of the code.
2. **code↔test agreement** — every test asserts the behavior the code actually has, and exercises the
   *real* path (behavioral-over-structural; mock fidelity).
3. **doc-lifecycle labeling** — a doc describing not-yet-built behavior is explicitly labeled
   future-state/planned (and exempt until that work ships); a doc past its `Re-validate when:` is suspect.
4. **no stale orphan docs** — a doc that no longer matches the code is revised or removed, not left to mislead.
5. **no inert tests** — a test that cannot fail (tautology, never calls the unit, over-mocked) is not coverage.
6. **third-vertex generalization** — for a failure/architectural claim the third vertex is a
   *probe/falsification mechanism*, not necessarily a unit test.

## Phase 2 — Evaluative read + scoring

Now read for judgment. For each (claim × vertex × site), confront it against the frozen bar — the
**doc/spec↔code (or test↔code) mismatch is the finding** (the doc states intent, the code is the evidence; trust
neither, the mismatch is the signal). Apply the assessment engine on every finding:
- **falsifiability:** state "this judgment is wrong if ___".
- **epistemic tier:** label one of `Observed file:line` / `Inferred` / `Unverifiable-without-running`.
- **severity:** HIGH / MEDIUM / LOW.

**Cost-proportional collapse:** the triad collapses to **code↔test by default**; spend the full
triad (the doc leg) only on **load-bearing** doc claims — a claim is load-bearing iff *(silently-wrong →
bad decision) AND (forensic value)*. A prose "module has three layers" claim is not load-bearing; "writes
are CAS-guarded" is.

**Hardest leg — code silently invalidating *untouched* docs.** A doc nobody edited can be falsified by a
code change. For each changed/under-review symbol, `grep -rn <symbol-or-file-basename>` across `docs/`,
`*.md`, and docstrings to find docs that still describe the old behavior; reconcile each hit.

Emit a **Non-findings** section: claims you checked and found consistent, or docs correctly labeled
future-state (silence ≠ coverage — the list is your proof you looked).

## Phase 3 — Adversarial verification (default-on; skip with --no-verify / --depth quick)

For each top-severity drift, dispatch a counter-adversary (Agent) instructed to **refute** it: is the
doc correctly labeled future-state (exempt)? is the cited code path dead/unreachable? is the "failing"
test actually collected and run (not skipped, not un-imported)? does an upstream layer satisfy the claim?
Only drifts that survive refutation are confirmed; default refuted=uncertain → drop, to avoid
plausible-but-wrong findings.

## Output

**Read-only (default): the assessment envelope** — a markdown report with these canonical headers (a
header-presence check is the only "schema"):
- `provenance` — `assessed at commit <sha>` (+ scope: all/changed/component, and `--vertex` if directed)
- `rubric` — the frozen triad bar used
- `findings` — each: the **claim (doc/test) vs the code evidence**, severity · falsifiability · epistemic tier · `file:line` for *both* vertices
- `non-findings` — claims checked and consistent (incl. docs correctly labeled future-state)
- `Re-validate when:` — concrete triggers that would invalidate this assessment
- `reproduction` — how to re-run this assessment
- `does NOT cover` — honest scope limits

**`--generate`: seed/accrete `TRIAD_MAP.md`** — gated. Write-gate (minimal default):
- NO finding at tier `Unverifiable-without-running` is written as fact.
- EVERY written claim carries a `falsifier` field.
- The artifact is a separate contract from the envelope above (different headers; don't conflate).

`TRIAD_MAP.md` template (the artifact, NOT the envelope):

```markdown
# Triad Map

> provenance: generated at commit <sha> · Re-validate when: <triggers>

## Surfaces (× vertices)
| Surface | Code (file:line) | Tests (file:line) | Docs (file:line) |

## Load-bearing claims
| Claim | Vertex (doc/test) | Load-bearing? | Reconciles with code? | Falsifier |

## Drifts
| Claim | Doc/test site | Code site | Severity | Status |

## Doc-lifecycle
| Doc | Label (current/future-state) | Re-validate when: | Action |

## Drifts seen in the wild (append-only)
- <date> · <PR> · <what drifted> · <fix>
```

A confirmed drift may **graduate into a standing guard**: offer to add a regression test that pins the
behavior, a corrected doc + `Re-validate when:` trigger, or a future-state label.
