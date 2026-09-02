# Omama

[![verify](https://github.com/devanomaly/omama/actions/workflows/verify.yml/badge.svg)](https://github.com/devanomaly/omama/actions/workflows/verify.yml)

*[Leia em português](README.pt-BR.md)*

*In Yanomami cosmology, Omama is the demiurge who gave the world its shape and its rules — a
fitting name for a toolkit whose job is to give shape and rules to agent behavior.*

**Fastest path: [QUICKSTART.md](QUICKSTART.md)** — clone to first receipt, every
command pre-executed, the install landmines called out where they bite.

**A rule without enforcement is a wish.**

Omama is a small set of deterministic guardrails for working with coding agents: hooks,
validators, and scripts with exit codes — not CLAUDE.md prose an agent can rationalize its way
around under pressure. Every piece ships with a fixture that proves it fails red before it passes
green, and every README documents its own known gaps instead of hiding them.

**The smallest sufficient harness.** Omama bets that the best harness is the least harness
that still holds: the common path per task is one slim card (a dozen lines of YAML), ONE
`verify` command, and a receipt written at close — nothing else. Rigor is bought by tier, not
paid by default: only S3 cards require a review artifact before VERIFIED. Verification is the
cheapest sufficient proof for the risk, never a fixed ritual. This shape is subtractive by
construction — an adversarial review killed most of what was originally built, and the cut
pieces ([05, 06, 07](#piece-numbers-nn-legend)) are named, not hidden. If a piece here costs
more attention than the failure it prevents, that's a bug in Omama — file it.

**No efficacy claim is made here.** What's proven is the mechanics (red-green fixtures, an
external adversarial review process that converged on what to measure) and nothing more. Where a
piece's README quotes a vote tally (e.g. "4/5", "5/5"), that's the count from a five-member panel
convened during that review — the process as a whole wasn't always five members, but every tally
quoted in this repo's docs comes from a five-member phase of it. An internal pilot is the next
step before any "this works" claim gets made — see [Honesty, by design](#honesty-by-design)
below.

*This repository is a seed extracted from a private working history; the process record — the
adversarial review that killed most of what was built, and the reasoning behind each cut — lives
there, not here. The initial commit is the extraction, not the work.*

## The seed loop (card → receipt → structured artifact)

A task enters, runs, and closes like this:

1. **[work-order](work-order/README.md)** — the task enters as a **slim card**: goal, non-goals,
   a tier ratified by a human (S1|S2|S3), an observable done-when, ONE non-vacuous `verify`
   command, a repro attached if it's a bugfix. Closed-schema validator, preflight checked.
2. **[receipt-gate](receipt-gate/README.md)** — a Stop hook that, on a DECLARED close, re-runs
   the card's own `verify` against the current tree, hashes before/after, and writes the
   receipt — **only the gate emits task-completion VERIFIED**. Closing honestly as
   FAILED/UNVERIFIED is always possible and always leaves a receipt. S3 cards require an
   approved review artifact before VERIFIED.
3. **[output-discipline](output-discipline/README.md)** — plans/reviews with mandatory structure
   (verdict first, tier, done-when/verify, explicit non-findings) and **advisory-only line
   budgets** — structure is enforced; budgets just nudge.

**Low-friction passive layers (enabled alongside, outside the measured per-task surface):**
[privacy-hook](privacy-hook/README.md) (pre-commit secrets scan) and
[protect-tests](protect-tests/README.md) (a PreToolUse guard against deleting/disabling/skipping
a test — the only mechanical coverage against test-weakening until the receipt gate covers it).

**Substrate and starter (active, not measured):**
[validator](validator/README.md) — a library, not a governance piece: the tri-state validator
skeleton that output-discipline and the receipt gate both inherit their exit contract from.
[starter-claude-md](starter-claude-md/README.md) — a `CLAUDE.md` starter plus a coherence
checker (untagged/dangling rules, renamed headings, vocabulary bypasses).

**On-demand ([skills/](skills/README.md), outside the measured per-task surface):**
belief-check, triad-check, and concurrency-map. The canonical files live in `skills/`; this repo
does not wire them into its own sessions (`.claude/` is untracked here except `settings.json`).

### Piece numbers ([NN] legend)

The starter template and its checker ([starter-claude-md](starter-claude-md/README.md)) trace
every rule back to a piece via a `[NN]` tag. Here's what each number maps to in this repo:

| NN | Piece |
|---|---|
| 01 | [privacy-hook](privacy-hook/README.md) |
| 02 | [work-order](work-order/README.md) |
| 03 | [validator](validator/README.md) |
| 04 | [protect-tests](protect-tests/README.md) |
| 05 | *evaluation of a third-party tool; cut before adoption, not included* |
| 06 | *evaluation of a third-party tool; cut before adoption, not included* |
| 07 | code conventions, optional — not included in this toolkit |
| 08 | [starter-claude-md](starter-claude-md/README.md) |
| 09 | [output-discipline](output-discipline/README.md) |

## Prerequisites

Python 3 on PATH — `python3` on macOS/Linux, `py -3` on Windows. Every command in this repo is
written with `python3`; substitute `py -3` if you're on Windows. The code itself is
launcher-agnostic (it shells out via `sys.executable`), but it is **developed and routinely
exercised on Windows** — POSIX is supported by construction and covered by CI, not by daily use.

**work-order** and **receipt-gate** need PyYAML (`pip install pyyaml`); **receipt-gate** needs
`git`; **protect-tests** needs Node.js. validator, starter-claude-md, and output-discipline run
with just Python 3.

## Principles (why these pieces)

A rule without enforcement is a wish — every piece is a hook, a validator, or a script with an
exit code, never prose. Evidence before confidence — every piece ships a fixture with a planted
red case; proving a guard means watching it fail for the right reason before watching it pass.
Every piece owns its own residual — each README carries "what this does NOT catch," with the
named route that would close the gap.

### Honesty, by design

The gate locks the *claim*, not the session. Honest states (WIP, FAILED) are exit 0 with a
trail — cheap. A dishonest VERIFIED claim is expensive — it has to beat hash binding and
tripwires, and the known residual forging routes are documented and pinned in fixtures, not
hidden.

## How to adopt

Each piece is opt-in, per repository — nothing here installs itself. Adopt the LOOP, not loose
pieces: work-order at the repo root, the gate wired into that repo's `.claude/settings.json`
(per-repo, never global — self-test both red AND green required, see
[receipt-gate/adapt/README.md](receipt-gate/adapt/README.md)), output-discipline's templates for
plans/reviews. The passive layers (privacy-hook, protect-tests) install alongside (pre-commit and
PreToolUse). **Third-party code:** protect-tests vendors an MIT-licensed script
(`vendor/PROVENANCE.md` has the full record).

## Verification and packaging

```
python3 verify_all.py        # every active fixture (privacy-hook takes minutes — real git corpus)
python3 verify_all.py --fast # skip privacy-hook's corpus (becomes NOT-RUN; exit 2)
```

End-to-end tri-state: `OK` / `FAILED` / `NOT-RUN` per entry; exit 0 only when everything ran and
passed.

## License

MIT (`LICENSE` at the root — code and docs). Provenance exception: `protect-tests/vendor/`
retains its upstream license — see [NOTICE.md](NOTICE.md).
