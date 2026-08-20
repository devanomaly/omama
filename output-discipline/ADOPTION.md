# 09 — Output Discipline · ADOPTION

Mechanics and limits in the [README](README.md).

## How to adopt

Rule that comes with any adoption of this piece (the anti-Goodhart clause for the
whole toolkit): **the validator proves the form; the human signs the substance.
Never fabricate content (reproduction evidence, a test result) to satisfy a
validator: a field you don't have, you ask for.** Without it, a deterministic gate
becomes a fabrication target — the deepest risk of validating form is the agent
fabricating the content that passes it.

Two routes, combinable — in both, **the human dictates, the agent fills in**: human
prose, template materialized by the agent, form proven by the validator (exit code),
substance reviewed by the human. Nobody copies the template by hand.

1. **Per repository:** adopt piece 08 (starter CLAUDE.md), whose `[09]` bullets already
   instruct this format from human dictation. Adjust the paths.
2. **Per operator (all sessions and repos):** a block in the global CLAUDE.md:

   > **Output form.** Plans and reviews follow the templates of the Omama output-discipline piece
   > (`<path>/output-discipline/templates/`): structure is mandatory — severity
   > tier declared; **reviews open with the verdict** within the first 3 non-empty lines,
   > followed by Findings/Non-findings. Line budgets (XS ≤5 ·
   > S ≤15 · M ≤40 · L no ceiling) are advisory — the checker warns, it does not fail.
   > XS floor: one line in chat (`Plan (XS): goal; done when X; verify: cmd`).
   > Spot-check: `py -3 <path>/scripts/check_artifact.py --budgets-advisory <file>`.

   (The block the author runs in trial.)

## What only a human decides

- The right tier — severity is judgment, not parsing.
- Content that is true and sufficient (the right done-when, the right verdict).
- A plan L opening with the summary — the checker does not prove this.
- Adjudicating the trial: closing ledger 006 and swapping the ON TRIAL label for the verdict.
