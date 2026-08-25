# 02 — Work Order · ADOPTION

Integration and human decisions. The mechanics and the limits are in the
[README](README.md); the evidence is the re-runnable fixture (`fixture/run_fixture.py`).

## How to adopt (step by step)

1. Copy `work-order.template.yaml` to the task's card (e.g., `card-2451.yaml`).
2. Fill in the fields — start with `goal`; if you cannot write a concrete `goal`
   and a `verify` that proves it, the correct `task_type` is `ask-first`, not `bugfix`.
3. The agent PROPOSES the `tier`; the human RATIFIES before dispatch. S3 carries the
   routing invariant: plan approval before implementation + a review pass before close.
4. For `bugfix`, attach the reproduction in `repro` (command + observed output, failing
   test) BEFORE dispatching — the validator rejects a bugfix without it.
5. Run the validator before dispatching the agent:
   ```
   python3 validate_work_order.py card-2451.yaml
   ```
   If it rejects, fix the flagged field — do not bypass the rule by editing the validator.
6. Only dispatch after `OK`. The validated card freezes goal/non-goals — the agent may
   report the card is wrong; it may not redefine it mid-execution.
7. Close is not a feeling of readiness: it is `verify` re-run against the current tree.
   The one that does this mechanically is the receipt gate (Stop-hook); without it, run
   `verify` yourself and keep the command + exit code.

The gate only exists where the pipeline conditions dispatch on `OK` — wire the validator
into CI or the dispatch wrapper; a validator nobody runs is prose with a `.py` extension.

## Sourcing a card from an existing GitHub issue

An issue is prose, same as a verbal "fix bug X" — it does not arrive pre-ratified.
When an agent is asked to turn an issue into a card, the fields it may fill from the
issue text and the fields that stay human are not the same list:

- **Fillable from the issue:** `goal` (from the title/body), `task_type`,
  `done_when` (from stated acceptance criteria, if any).
- **Proposed, not decided:** `tier` — the agent may suggest one; ratification is
  still the human act step 3 of "How to adopt" already requires.
- **Never fabricated:** `verify` and, for `task_type: bugfix`, `repro`. Most issues
  do not contain a real proof command or an attached reproduction; inventing one to
  fill the field is exactly the fabrication [CONTRIBUTING.md](../CONTRIBUTING.md)
  and this piece's own residual warn against (see "What it does NOT catch" in the
  [README](README.md) — truth of content is a human read, not something the
  validator or an agent can certify). One refinement: when the issue states
  explicit acceptance criteria, the agent may derive a **proposed** `verify` from
  them — written next to the empty field and labeled a proposal, never filled in
  as if ratified. Proposing from stated criteria is not fabrication (the criteria
  are the issue author's, not the agent's); an unlabeled fill is. And a criterion
  that is not mechanically checkable must not be laundered into a vacuous command
  just to occupy the slot — the validator's non-vacuity check is the backstop,
  the human read is the gate. Either way the agent shows the draft and stops; the
  human supplies or confirms `verify`/`repro`, then runs
  `validate_work_order.py` before dispatch — same gate, same step 5, regardless of
  where the draft's fields came from.

No new mechanism exists for this — it is a routing note for step 2-3 above, not an
additional validator or hook.

## What only a human decides

- Ratifying the `tier` — the validator checks the value, not whether S1 was really an S3.
- Whether `verify` PROVES the `goal` — a technically real but irrelevant command passes
  the validator (form, not relevance).
- Whether the attached `repro` is genuine — not merely present and well-typed.
- Whether `non_goals` draw the RIGHT scope — narrow enough to make the diff reviewable.

## Complementary checks (outside this piece)

- Verified close: the receipt gate (Stop-hook) re-runs `verify` at the end and binds the
  result to the current tree — only it emits VERIFIED.
- Card presence: a `PreToolUse` gate that blocks editing without a valid card is a known,
  unbuilt route — today, nothing prevents dispatch without a card.
