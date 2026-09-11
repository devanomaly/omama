# Omama

[![verify](https://github.com/devanomaly/omama/actions/workflows/verify.yml/badge.svg)](https://github.com/devanomaly/omama/actions/workflows/verify.yml)

*[Leia em português](README.pt-BR.md)*

*In Yanomami cosmology, Omama is the demiurge who gave the world its shape and its rules — a
fitting name for a toolkit whose job is to give shape and rules to agent behavior.*

**Fastest path: [QUICKSTART.md](QUICKSTART.md)** — build and install the local wheel,
initialize a synthetic or adopting repository, inspect it with doctor, then dispatch.

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
   FAILED/UNVERIFIED leaves a receipt after routing and repository identity checks pass. S3 cards require an
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
| 10 | [receipt-gate](receipt-gate/README.md) |

## Prerequisites

The CLI supports Python 3.8 or newer (below Python 4) and requires Git. Build/install it
from this checkout with `uv`; no public package release is claimed here. Default `init`
also needs `uv` at installation time and an independently discoverable existing base
Python. It disables managed-Python downloads: it does not download Python, change a user
or global Python installation, or write user/global Claude or Git configuration.

Default `init` creates `.omama/runtime` in the target and installs only constrained PyYAML
there. `--python <ABSOLUTE_PATH>` instead qualifies an existing Python/PyYAML environment
read-only. The privacy hook has a separate upstream contract: its unchanged wrapper selects
`py -3`, `python3`, then `python` through PATH. A receipt interpreter does not configure or
replace that privacy interpreter.

The standalone pieces retain their documented prerequisites. In particular,
**work-order** and **receipt-gate** need PyYAML, and **protect-tests** needs Node.js.

## Principles (why these pieces)

A rule without enforcement is a wish — every piece is a hook, a validator, or a script with an
exit code, never prose. Evidence before confidence — every piece ships a fixture with a planted
red case; proving a guard means watching it fail for the right reason before watching it pass.
Every piece owns its own residual — each README carries "what this does NOT catch," with the
named route that would close the gap.

### Honesty, by design

The gate locks the *claim*, not the session. After routing and repository identity checks,
honest states (WIP, FAILED) are exit 0 with a
trail — cheap. A dishonest VERIFIED claim is expensive — it has to beat hash binding and
tripwires, and the known residual forging routes are documented and pinned in fixtures, not
hidden.

The inherited routing boundary includes `GIT_CONFIG_GLOBAL` and
`GIT_CONFIG_SYSTEM`; a wiring probe reports their refusal as an environment
failure, not a missing gate. Non-Git directories mounted inside a checkout
retain NO-CARD, WIP and honest closes across that filesystem boundary.

## How to adopt

Use the local wheel workflow in the [Quickstart](QUICKSTART.md) for the phase-1 bundle:
receipt gate, validator, S3 checker, privacy scanner and both Git entrypoints, templates,
sample policy, local runtime/wiring, provenance, and state. Initialization is per repository.
It merges its Stop entry into ignored `.claude/settings.local.json`, preserves unrelated
settings, and never creates `CLAUDE.md` or changes user/global configuration.

Manual piece-by-piece adoption remains supported. Follow each piece's `ADOPTION.md` and the
[vendoring guide](VENDORING.md): copy bytes unchanged, record upstream source/SHA/files,
and manually exclude copies from formatters and linters. The CLI deliberately does not
rewrite formatter configuration. **Third-party code:** protect-tests vendors an MIT-licensed
script (`vendor/PROVENANCE.md` has the full record); protect-tests itself is outside the
phase-1 CLI bundle.

Re-running the same bundle repairs eligible missing immutable files while preserving adopted
editable material, including deliberate removal of inert templates. It refuses immutable
drift and another bundle; it is not an implicit update command. Existing team deny policy,
tokens, card/receipt/index state, unrelated settings, and custom hooks are not overwritten.
If activating `.githooks` would displace any active hook in the effective hooks directory,
including a lone `pre-push`, init refuses and asks for manual integration.

## Verification and packaging

```
python3 verify_all.py # Windows: py -3 verify_all.py
```

The release verification command is the full runner without `--fast`. End-to-end tri-state:
`OK` / `FAILED` / `NOT-RUN` per entry; exit 0 only when every required fixture, including the
counted built-artifact CLI integration, ran and passed. The measured platform/build matrix and
remaining limits are summarized in the Quickstart; synthetic shell admission is not evidence
that a real Claude host loaded project settings.

At frozen CLI source revision `efa675869f42ebcd8d9204dcfbc0f5b34c3babe7`, that runner
reported `9 ok, 0 failed, 0 not-run` on Ubuntu/Python 3.8, Ubuntu/Python 3.11,
macOS/Python 3.11, and Windows/Python 3.11. Its counted CLI entry contains six suites and
74 tests at that revision, including nine runtime tests; CI exposes the nine-entry parent
summary rather than a distinct artifact hash or log for each child suite.

## License

MIT (`LICENSE` at the root — code and docs). Provenance exception: `protect-tests/vendor/`
retains its upstream license — see [NOTICE.md](NOTICE.md).
