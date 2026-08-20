# Provenance

- **Repo:** https://github.com/karanb192/claude-code-hooks
- **Commit SHA:** `eb091e4723a748af15f3a05782e6b1c9ff8cd17b` (2026-08-13 11:07:53 +0530)
- **Files vendored verbatim (byte-identical, `diff` confirmed):**
  - `hook-scripts/pre-tool-use/protect-tests.js` -> `protect-tests.js`
  - `hook-scripts/tests/pre-tool-use/protect-tests.test.js` -> `protect-tests.test.js`
  - `LICENSE` -> `LICENSE` (MIT, Copyright (c) 2026 Karan Bansal)
- **No modifications.** Any adaptation for team use lives in `../adapt/`, not here.

Retrieved by reading an already-cloned local copy of the upstream repo at `<STAGING_ROOT>/claude-code-hooks/`
and copying the files unmodified. Command used to obtain the SHA above:

```
git -C <path-to-cloned-repo> log -1 --format='%H %ai'
```

## Maintenance decision: ACCEPT (upstream untouched)

- **Decision:** ACCEPT — keep the vendored code byte-identical to upstream; do NOT fork now.
  The confirmed bypass routes (`find -delete`, empty Write over a test, Windows path
  separator, fail-open on malformed stdin) remain a documented residual risk in the piece's
  README "Scope and limits," each with the layer that would resolve it.
- **Why:** forking closes 4 lexical routes but breaks the byte-identical provenance claim
  and shifts maintenance onto us before any evidence of real use of the piece. The
  `assert True` route stays open in any fork (no lexical hook decides semantics), so the
  fork never buys "complete protection" — it only shrinks the map. Dogfooding first; if the
  piece proves used and the routes hurt in practice, the minimal fork (fail-closed + Windows
  separator) is the first candidate.
- **Owner:** the maintainer. **Date:** 2026-08-18. **Revisit:** after one dogfooding cycle
  (internal pilot) or at the next external review, whichever comes first.
