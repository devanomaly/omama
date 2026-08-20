# protect-tests

> **Zero-cost passive layer of the seed loop** (panel returned the piece 4/5 against the
> announced cut; re-ratified 2026-08-19: the only mechanical coverage of test
> weakening until the receipt gate covers this). Docs: **README**
> (promise, command, states, coverage) · [ADOPTION.md](ADOPTION.md)
> (install, sanctioned route, human decisions). Provenance of the vendored code:
> `vendor/PROVENANCE.md`; probe history in git (EVIDENCE.md up to
> 2026-08-19).

## The decision this piece changes

An agent that "makes the suite pass" by deleting, renaming-to-disabled, or marking tests as
skip/xfail **via the lexical patterns covered below** stops being able to do that
silently. The decision that changes is about THOSE patterns — the most common in practice — not
about every conceivable deactivation (routes not covered are in "Scope and limits"). Fixing the
code stays the default path; triggering a covered pattern becomes a deliberate exception, not a
side effect of "let me just make this pass".

## What it is

A Claude Code `PreToolUse` hook (Node.js), vendored **verbatim** from the repository
[karanb192/claude-code-hooks](https://github.com/karanb192/claude-code-hooks) (MIT), commit
`eb091e4723a748af15f3a05782e6b1c9ff8cd17b`. It intercepts `Bash`, `Edit`, `MultiEdit`, and
`Write` calls **before** they execute and denies (`permissionDecision: "deny"`) three patterns:

| Level | Trigger |
|---|---|
| `critical` | `rm` / `unlink` / `shred` / `trash` / `git rm` on a test file or directory |
| `high` | renaming a test file to a "disabled" name (`.bak`, `.old`, `.disabled`, `.skip`, `.ignore`, `.tmp`, `~`) **or** inserting a skip/xfail/ignore marker (`@pytest.mark.skip`, `it.skip(`, `@Disabled`, `#[ignore]`, etc.) into an **existing** test via `Edit`/`MultiEdit` |
| `strict` | writing, from scratch, a test file that is already born marked as skip (`Write`) |

The active level is `high` (constant `SAFETY_LEVEL`): it covers `critical` + `high`. It does
**not** block writing new, real tests, renaming a test to another test name (refactor), nor
editing a test's body (legitimate fix).

- `vendor/` — original script and tests, byte-identical to upstream, + `LICENSE` (MIT) +
  `PROVENANCE.md` (origin + maintenance decision).
- `adapt/` — example of how a team would plug this in (`settings.example.json`) — **not
  installed**.
- `fixture/` — `run_fixture.py` + 3 `case-*.json` payloads; does not depend on a real
  installation.

## Command and states

```
cd fixture
python3 run_fixture.py <violation|skip|clean|all>
```

The hook itself **always exits with exit 0**; the block is communicated only via the stdout JSON
(`permissionDecision: "deny"`; an allowed call prints `{}`), which the harness reads. The states
below are from the RUNNER, which translates that decision:

| Exit | State | Means |
|---|---|---|
| 0 | correctly allowed | `clean` case allowed (the action proceeds); in `all`, ALL cases matched |
| 1 | correctly blocked | `violation`/`skip` case denied — the action does NOT proceed |
| 2 | broken | hook different from expected, infra failed (node/JSON), or wrong CLI usage; in `all`, some case did not match |

## Scope and limits

### What it catches

3-case fixture run on 2026-08-18 (`python3 run_fixture.py all`, Node.js on PATH), all with
the expected result, runner exit 0: deleting a test via Bash denied (`delete-test`), skip via
Edit denied (`skip-test`), ordinary production edit allowed. Case-by-case receipts and
the proof of non-vacuousness: the fixture itself. Rename-to-disabled and the
`strict` level come from upstream and **have no case in the local fixture** — see the coverage
table.

### What it does NOT catch

Bypass routes **confirmed on 2026-08-18** by direct probe (receipts in
git history), not fixed. The hook is lexical, not semantic. A determined agent
can still do it — each route with the layer that would resolve it:

- `find tests/ -type f -delete` — deletion without lexical `rm`/`unlink`: **allowed**. Resolved
  by: fork/adaptation (deletion patterns beyond the current lexicon); extra layer: sandboxing
  (evaluated and dropped in an earlier round; see project history) or diff review.
- `Write` of empty content over an existing test — empties without deleting: **allowed**.
  Resolved by: fork/adaptation; in CI, compare collected test count
  (`pytest --collect-only`) between base and branch.
- Rewriting assertions to `assert True` — the test runs and tests nothing: **allowed**. No
  lexical hook decides this: resolves with mutation testing and human diff review.
- Windows path (`C:\repo\tests\test_auth.py`) in a skip/deselect command — the patterns assume
  a POSIX separator: **allowed** (serious: Windows is this toolkit's primary platform). Resolved
  by: fork/adaptation (normalize path separator).
- malformed stdin → the hook responds `{}` and **fails open** (the action goes through). Resolved
  by: fork/adaptation (fail-closed on unreadable input).

While these routes exist, the honest sentence is "the covered lexical patterns stop being an
option," never "disabling a test stops being an option." Closing the gaps would require
fork/adaptation of the vendored script — **decision made: ACCEPT (upstream untouched), by the
maintainer, 2026-08-18, revisit after one dogfooding cycle**; full record with the reasoning in
`vendor/PROVENANCE.md`. This section is the piece's ACCEPTED failure map, not a backlog.

### What only a human decides

See [ADOPTION.md](ADOPTION.md) — real installation, the sanctioned route for legitimate
deactivation, and the fork-vs-accept maintenance decision (made 2026-08-18: ACCEPT, residual
formally accepted; reopening it is a human decision).

### Coverage

| Promised | Mechanically covered | Not covered / known bypass | Classification |
|---|---|---|---|
| Deleting a test stops being silent | `rm`/`unlink`/`shred`/`trash`/`git rm` denied (fixture `violation` → deny `delete-test`, exit 1) | `find tests/ -type f -delete` (2026-08-18) | defect — accepted residual |
| Deactivating an existing test (skip/xfail/ignore) stops being silent | marker via Edit denied (fixture `skip` → deny `skip-test`, exit 1) | skip/deselect command with Windows path (2026-08-18) | defect — accepted residual |
| Emptying a test without deleting it is stopped | nothing | `Write` of empty content over existing test (2026-08-18) | defect — accepted residual |
| A test that runs but tests nothing is blocked | nothing | assertions rewritten to `assert True` (2026-08-18) | not assessed |
| The hook decides even with invalid input | nothing | malformed stdin → `{}`, fails open (2026-08-18) | defect — accepted residual |
| Renaming a test to a "disabled" name is denied (`high` level) | pattern present in the vendored script (upstream) | no case in the local fixture — not proven in this environment | not assessed |
| Writing a test that is already born skipped is denied (`strict` level) | nothing — the shipped active level is `high`, `strict` is off | route open in the shipped configuration | not assessed |

Accepting a residual requires a named human signature and date — **satisfied 2026-08-18: ACCEPT,
by the maintainer** (record in `vendor/PROVENANCE.md`).
