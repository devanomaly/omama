<!-- plan v1 · tier: M -->
<!--
  output-discipline PLAN template. Declare the tier in the comment above
  (XS | S | M | L) — the validator refuses to grade an undeclared artifact.

  Tier = consequence × exposure × detection difficulty × cost-to-correct-later.
  Budgets (non-empty lines, comments excluded): XS ≤5 · S ≤15 · M ≤40 · L uncapped
  but summary-first. — advisory: the checker warns, structure is what fails

  XS floor — skip this file entirely and write one line in chat:
    Plan (XS): <goal>; done when <observable check>; verify: <command>.

  Required content by tier:
    all:  Goal, Done when, Verify
    M+:   Risks / pillars line (honest N/A allowed, but written)
-->
# Plan: <goal in one line>

- **Done when:** <observable end state — bullets, each one checkable>
- **Verify:** <command or named check whose result decides — not "looks right">
- **Tier:** <XS|S|M|L> — <one-line justification via the severity factors>

## Approach

<S: ≤3 bullets · M: ≤10 lines · L: sections. The only elastic section.>

## Risks / pillars

<M+ only. One line per applicable pillar or hazard, or "N/A — <reason>".>
