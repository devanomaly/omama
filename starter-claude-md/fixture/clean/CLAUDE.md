# CLAUDE.md — checkout-api

## Where to put it

This file, versioned as `CLAUDE.md` at the root of the repository, applies to
every agent working in this repo — it's the recommended option for team rules. A
dev can reuse parts of this file in their `~/.claude/CLAUDE.md` (global, applies
to every repo they touch), but **only the code-convention lines** (the "Code
conventions" section below) — never the "Hooks installed in this repo" section,
because the hooks named there are specific to this repository and don't exist
elsewhere.

## Code conventions

- When creating a new file, keep it to at most 500 lines; if a file you're
  editing goes past that, propose a split instead of letting it keep
  growing. [07]
- When naming a top-level function, class, or module, choose a grep-unique
  name — before using a generic name (`process`, `handler`, `validate`), run
  `grep -rn "<name>" .` (or, since this repo has a naming-convention checker
  installed, `python3 tools/check_conventions.py .`, which already detects
  top-level name collisions automatically) and confirm it doesn't collide
  with something already present elsewhere in the repo. [07]
- At every public boundary (module API, endpoint, interface between layers),
  declare explicit input and output types — no `any`, no `Dict`/generic
  object, no public function without a typed signature. [07]
- Every plan/review declares a tier and follows piece 09's structure (review
  opens with a verdict; line budgets are advisory). [09]
- The human dictates, you fill in: fill in the corresponding template
  (work order, plan, review) from what the human described, run the piece's
  validator, and hand it back for review — the validator proves the form,
  the human signs the substance. Never fabricate content (reproduction
  evidence, test result) to satisfy a validator: a field you don't have,
  you ask for. [09]

## Bugfix requires a work order

The heading says "bugfix" because that is where a missing contract hurts
most, but the rule is not limited to it: **every** `task_type` — bugfix,
implementation, refactor, config, do-nothing, ask-first — enters through a
card. A bugfix is only the one that additionally owes a `repro`.

- Before editing code for a task of any `task_type`, request (or fill in
  yourself) the task's card as `CARD.yaml`, at the repo root or at the path
  `OMAMA_CARD` names when this repo sets it (that is the card the gate
  reads), using piece 02's slim schema — don't start from a loose "fix bug
  X" in prose. Run
  `python3 tools/work-order/validate_work_order.py CARD.yaml` before the
  first edit; it must exit 0. [02]
- `tier`, `verify` and (for a bugfix) `repro` are human-owned: you may
  propose them, a human ratifies them, and you never invent one to make the
  card validate — no fabricated reproduction, no proof command that cannot
  fail. A bugfix card with no attached reproduction does not validate, and
  the answer to that is to stop and ask for the reproduction, never to
  supply one you did not observe. A field you don't have, you ask for. [02]
- Don't expand scope mid-execution. `non_goals` is the frozen list of what
  the diff must not contain. If you discover the problem is actually
  something else, or that the card is incomplete or wrong, stop and report
  the contract as defective — you may not redefine it on your own. [02]
- A card's work lands as **one branch cut from the default branch's tip**,
  opened as a pull request against it — never cut from another open PR's
  branch, which silently carries that branch's commits along. The receipt
  written at close names the `rev` the proof ran against, so the branch you
  verified on is the branch under review. [02]

## Hooks installed in this repo

- This repo has a privacy `pre-commit` hook that scans staged content against
  a deny-list of secrets/regexes/names/tokens. If it blocks a commit, don't
  bypass it (don't use `--no-verify`, don't comment out the rule) — review
  the staged content the hook flagged; if the rule is wrong, that's a
  decision for the team that owns the deny-list, not the agent. [01]
- This repo has a `PreToolUse` hook (`protect-tests`) that denies deleting,
  disabling, or marking a test as skip/xfail via Bash/Edit/Write. If it
  blocks an action, that means removing the test's protection is a
  deliberate human decision, not something the agent decides on its own to
  unblock a green — fix the code instead of disabling the test. [04]
- This repo has a `Stop` hook (`receipt-gate`) that owns the close. When the
  card's work is done, write `CLOSE` to `CARD.close` **next to the card** (the
  gate reads it from the card's directory: the repo root by default, or
  wherever `OMAMA_CARD` points) and stop — the gate re-runs the card's own
  `verify` against the current tree and writes `CARD.receipt.json`; only the
  gate emits VERIFIED. Stopping with no `CARD.close` is a work-in-progress
  turn and is allowed. If the gate blocks
  the close, report the named block — do not route around it: no deleting
  `CARD.yaml`, no editing `verify`, no retrying `CLOSE` until something
  gives. Closing honestly (`FAILED: <reason>`, `UNVERIFIED: <reason>`) is
  always allowed and always leaves a receipt. [10]
