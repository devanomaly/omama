<!-- review v1 · tier: M -->
<!--
  output-discipline REVIEW template. Declare the tier (XS | S | M | L) above.
  Budgets (non-empty lines, comments excluded): XS ≤5 · S ≤15 · M ≤40 · L uncapped.
  — advisory: the checker warns, structure is what fails

  Hard rule at every tier: THE VERDICT COMES FIRST — within the first three
  non-empty lines. A review that buries its verdict fails validation.

  XS floor — one line in chat, no file:
    Review (XS): <target> — Verdict: PASS|BLOCK; <one-line reason>.

  Required content by tier:
    all:  Verdict line (PASS | PASS-with-issues (N) | BLOCK (N))
    S+:   ## Findings (ranked; each: claim · falsifier/trigger · blocking
          verdict with evidence both ways) and ## Non-findings (what was
          checked and found clean — coverage is part of the deliverable)
-->
# Review: <target>

**Verdict:** <PASS | PASS-with-issues (N) | BLOCK (N blockers)> — <one line>

## Findings

<Ranked by severity. Each finding: the claim · concrete trigger + observable
wrong behavior (falsifier) · blocking verdict with the evidence that disposes
it. No falsifier → it is a question, label it as one.>

## Non-findings

<What you probed and found sound. "Nothing" is never a non-finding.>

## Detail

<M+ only. Supporting evidence, alternatives considered, minimal fixes.>
