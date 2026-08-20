<!-- plan v1 · tier: S -->
# Plan: add retry to webhook sender

- **Done when:** transient 5xx no longer drops events.
- **Tier:** S — bounded, observable.

## Approach

- Wrap send in 3-attempt backoff.
