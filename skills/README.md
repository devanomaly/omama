# skills/ — on-demand skills for Omama (zero-cost tier, outside the measured surface)

Port of the three on-demand skills referenced by the reduced global CLAUDE.md
(ratified 2026-08-19 in the internal reduction round): **belief-check**,
**triad-check**, **concurrency-map**.

- **Provenance:** a maintainer private repo (`ai-agency-toolkit` @ `83d210f`,
  main, 2026-08-12), plugin `swe-pillars` — the freshest version at the time of the port.
- **Vocabulary scrub applied:** references to the internal numbered namespace
  (`CC2`/`CC5`/`CC6`/`CC9`, shorthands `IR`/`UV`) were removed or rewritten
  in plain words — this is the contamination detector proven in the
  clean-room experiments of the reduction campaign; `P[0-9]+`, `CC[0-9]+`, and `R[0-9]+` are
  internal process codes (not publicly documented), so
  `grep -rE '\b(P[0-9]+|CC[0-9]+|R[0-9]+)\b' skills/` must return zero.
- **Single-home:** THIS folder is the only editable home. The plugin's
  local copies carry `DEPRECATED.md`; durable deprecation in the upstream repo is a
  pending operator action (the cache note dies on plugin update).
- **Invocability:** `.claude/skills/` at the omama root holds thin pointers
  (they load and defer to the canonical SKILL.md here) — invocable in a
  session in omama without duplicating content.
- **No behavior change** beyond the rename/scrub (a non-goal of the card);
  they are not part of the measured dogfood.
