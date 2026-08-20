---
name: concurrency-map
description: >
  Map and assess a repo's concurrency posture (actors × shared mutable resources
  × ordering invariants × race windows) against a frozen invariant bar; flag the
  fixture-proven shapes — read-then-write-without-CAS, post-terminal writes,
  lock-ordering deadlocks — against a broader vendor-neutral invariant catalog
  (single-writer, ordering, idempotency, cleanup-ownership). Metastability /
  tipping-point candidates are parked for failure-map, not graded here. Read-only
  by default; --generate seeds/accretes CONCURRENCY_MAP.md. Standalone, repo-agnostic.
user-invocable: true
argument-hint: "[path] [--component <dir>] [--scope changed|all] [--generate] [--no-verify | --depth quick]"
allowed-tools: Read, Grep, Glob, Bash, Write, Edit, Agent, TodoWrite
model: opus
---

# concurrency-map

Assess a repo's (or `--component <dir>`'s) concurrency posture against a frozen invariant bar;
optionally produce/accrete a `CONCURRENCY_MAP.md`. Read-only by default. **Agent-instruction skill — you, the agent, run the phases below.**

**Modes.** `--scope all` (default) sweeps the whole target; `--scope changed` ratchets on the
diff vs the merge-base (clean-as-you-build). Directed: the invoker names a component/surface;
sweeping: you survey broadly. Verification is ON by default; `--no-verify` / `--depth quick`
skips Phase 3.

**Side-effect gate.** The default run mutates nothing: do **not** call `Write`/`Edit` unless
`--generate` is set and the Output write-gate passes.

## Phase 0 — Substrate detection (enumeration, NOT judgment)

Detect the concurrency surface at **every** layer — never just `import threading`:
- **In-process:** threads, asyncio loops, multiprocessing, futures/executors.
- **Cross-process:** worker pools / task queues (e.g. Celery, Sidekiq, BullMQ), multiple web workers.
- **Cross-request on shared state:** DB rows, cache entries, files, object-store keys touched by >1 request.
- **Distributed:** queues, external APIs, idempotency keys, leases/locks.

Produce the enumeration: **actors × shared-mutable-resources × access-sites (`file:line`)**.
Use Grep/Glob to find the sites; do not yet judge whether any of it is correct.

**Sweeping-scope exclusion (`--scope all` only):** skip synthetic concurrency that is *test
input*, not runtime — `test-fixtures/`, `fixtures/`, `examples/`, and intentional-bug corpora.
An explicit `--component <path>` overrides this (directed beats sweeping): if the invoker
names a path, analyze it even under those dirs.

If there is genuinely no shared mutable state under concurrent access (pure stateless
compute) → still emit the **full assessment envelope** (canonical headers, Output below) whose
`findings` is the single entry **"no concurrency surface — nothing to map"**, then stop.
(Absence is a first-class result, not silence — and shipping the envelope keeps the run consistent.)

## Phase 1 — Freeze the bar (before any evaluative read)

Establish the invariant set, then **freeze it** before grading (anti-bias: you may not
lower the bar because the code is messy).

- **Directed + established:** if the repo already declares invariants (an existing
  `CONCURRENCY_MAP.md` / `INVARIANTS.md` / danger-zones doc), load and use them.
- **Exploratory (no prior bar):** co-discover. For each multi-actor resource, *propose*
  a candidate invariant to the human — e.g. *"`X` is written from A@L1 and B@L2 with no
  shared guard → candidate: 'X is single-writer, serialize via lock L' OR this is a live
  bug — which?"* **You only propose; the human authors the consequence** ("what breaks if
  this is false?") before it is frozen. Never launder both the claim and its stakes.

**Default Layer-1 catalog** (vendor-neutral; use when nothing else is declared):
1. **compare-and-swap / optimistic concurrency on read-then-write** — the guard is encoded
   in the conditional-write predicate (the write filter), not in surrounding code branches.
2. **single-writer** — a shared resource has exactly one writer, or writers are serialized.
3. **happens-before / ordering** — operations that must be ordered are ordered.
4. **idempotency** — repeatable operations are safe to retry.
5. **no writes to an entity after it reaches a terminal/immutable state.**
6. **a shared mutable resource with multiple writers needs a single cleanup/invalidation
   owner** (or all writers coordinate).
7. **lock-ordering for deadlock-freedom** — all actors acquire locks in a consistent order.

(Vendor-specific encodings — e.g. Mongo filter-CAS — belong in the private overlay, not
this public default.)

## Phase 2 — Evaluative read + scoring

Now read for judgment. For each (actor × resource × access-site), confront it against the
frozen bar. Apply the assessment engine on every finding:
- **falsifiability:** state "this judgment is wrong if ___".
- **epistemic tier:** label one of `Observed file:line` / `Inferred` / `Unverifiable-without-running`.
- **severity:** HIGH / MEDIUM / LOW.
Spend full rigor only on **load-bearing** surfaces (a finding whose silently-wrong outcome is
a bad decision with forensic value).

Emit a **Non-findings** section: surfaces you checked and found clean (silence ≠ coverage —
the list is your proof you looked).

**Metastability lens:** for each concurrency structure ask "tipping point? feedback loop?
recovers after a shock?" Tipping-point candidates are NOT graded here — record them in the
envelope's `tipping-points` section as claims-needing-evidence; under `--generate` they are
*additionally* copied into the `CONCURRENCY_MAP.md` "Tipping-points → failure-map" row (the seam
`failure-map` consumes later). Complete contract at this stage — no phantom consumer.

## Phase 3 — Adversarial verification (default-on; skip with --no-verify / --depth quick)

For each top-severity finding, dispatch a counter-adversary (Agent) instructed to **refute**
it: does the racing path actually co-execute? is the "missing" guard present upstream? is the
lock held by a caller? Only findings that survive refutation are confirmed; default
refuted=uncertain → drop, to avoid plausible-but-unreachable false positives.

## Output

**Read-only (default): the assessment envelope** — a markdown report with these canonical
headers (a header-presence check is the only "schema"):
- `provenance` — `assessed at commit <sha>` (+ scope: all/changed/component)
- `rubric` — the frozen Layer-1 bar used
- `findings` — each with severity · falsifiability · epistemic tier · `file:line`
- `non-findings` — surfaces checked and clean
- `tipping-points` — metastability candidates (claims-needing-evidence) handed to `failure-map`
- `Re-validate when:` — concrete triggers that would invalidate this assessment
- `reproduction` — how to re-run this assessment
- `does NOT cover` — honest scope limits

**`--generate`: seed/accrete `CONCURRENCY_MAP.md`** — gated. Write-gate (minimal default):
- NO finding at tier `Unverifiable-without-running` is written as fact.
- EVERY written invariant carries a `falsifier` field.
- The artifact is a separate contract from the envelope above (different headers; don't conflate).

`CONCURRENCY_MAP.md` template (the artifact, NOT the envelope):

```markdown
# Concurrency Map

> provenance: generated at commit <sha> · Re-validate when: <triggers>

## Actors
<threads / loops / workers / processes>

## Shared resources (× access-sites)
| Resource | Access sites (file:line) | Writers |

## Invariants
| Statement | Guard mechanism | Enforcement site | Falsifier |

## Race-windows
| Actors | Interleaving | Severity | Status |

## Tipping-points → failure-map
<metastability candidates handed to failure-map>

## Races seen in the wild (append-only)
- <date> · <PR> · <what raced> · <fix>
```

A confirmed finding may **graduate into a standing guard**: offer to add a regression test
that reproduces the interleaving, a danger-zone bullet, or an invariant row.
