---
name: concurrency-map
description: >
  Map and assess a repo's concurrency posture (actors × shared mutable resources
  × ordering invariants × race windows) against a frozen invariant bar; flag the
  fixture-proven shapes — read-then-write-without-CAS, post-terminal writes,
  lock-ordering deadlocks — against a broader vendor-neutral invariant catalog
  (single-writer, ordering, idempotency, cleanup-ownership). Metastability /
  tipping-point candidates are parked for failure-map, not graded here. Read-only
  by default; --generate seeds/accretes CONCURRENCY_MAP.md. Standalone, repo-agnostic.
---

This is a pointer, not the skill. Load and follow `skills/concurrency-map/SKILL.md`
at the repo root — that file is the single canonical home for this skill's
content.
