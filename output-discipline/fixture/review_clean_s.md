<!-- review v1 · tier: S -->
# Review: PR 42 — webhook retry

**Verdict:** PASS-with-issues (1) — retry works; one non-blocking gap.

## Findings

1. No jitter on backoff — trigger: N clients retry in sync after outage; observable: thundering herd. Non-blocking: bounded, observable, cheap later.

## Non-findings

- Idempotency: checked — sender keys on event id, duplicates rejected.
- Tests: red case present (5xx then success), fails without the patch.
