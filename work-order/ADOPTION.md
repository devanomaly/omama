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
