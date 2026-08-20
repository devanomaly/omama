<!-- plan v1 · tier: M -->
# Plan: migrate label store from CSV to SQLite

- **Done when:** all 60 rows readable via new store; validator returns invalid: 0; old CSV path removed.
- **Verify:** py -3 extractor/validate_labels.py --labels store.db
- **Tier:** M — durable-state write, detection easy, correction cheap pre-freeze.

## Approach

- Add store adapter with same row interface.
- Migrate via one-shot script, keep CSV as read-only backup for one week.
- Cut over validator, then remove CSV path.

## Risks / pillars

- P7: migration script gets a planted-corruption red fixture before trust.
- P8: N/A — single writer, no concurrency.
