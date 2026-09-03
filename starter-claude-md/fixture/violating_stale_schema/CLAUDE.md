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

- Before implementing a production bugfix, request (or fill in yourself) the
  task's `work-order.yaml`, using piece 02's `work-order.template.yaml`
  schema — don't start editing code from a loose "fix bug X" in prose. [02]
- A bugfix without an attached reproduction doesn't run: run
  `python3 tools/work-order/validate_work_order.py <file>.yaml` before
  editing any code; if `reproduction.required` is `true` and there is no
  reproduction evidence (failing test, recorded command, incident
  artifact), the validator rejects it — stop and ask for the reproduction
  instead of bypassing the check. [02]
- Don't expand scope mid-execution. If you discover the problem is actually
  something else, or that the work order is incomplete/wrong, stop and
  report the contract as defective — don't redefine
  `allowed.files`/`allowed.commands` on your own. [02]

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
