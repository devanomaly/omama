# Contributing to Omama

**A rule without enforcement is a wish** — including the rules on this page. What follows
is written so that most of it is checkable by `verify_all.py`, the CI matrix, or a
validator in this repo. The handful of things that are human by design are named as such
at the bottom, not smuggled in as if CI covered them.

## Before you touch anything

Prerequisites are in the [README](README.md). Confirm a green baseline first:

```
python3 verify_all.py          # py -3 on Windows
```

| Exit | Means |
|---|---|
| 0 | every fixture ran and VERIFIED |
| 1 | a fixture FAILED |
| 2 | something was NOT-RUN — a coverage hole, not a pass |

Exit 1 on a clean checkout is the bug — open a card about it before opening one about
anything else. Exit 2 usually means a prerequisite is missing on **your** machine (the
detail line names which); fix your environment and re-run before concluding anything.

## The card comes first

Contributions enter the same way tasks do. Open an issue containing a card built from
[`work-order/work-order.template.yaml`](work-order/work-order.template.yaml): `goal`,
`non_goals`, `tier`, `task_type`, `done_when`, `verify`, plus `repro` if `task_type` is
`bugfix`. Then prove the card before you argue for it:

```
python3 work-order/validate_work_order.py your-card.yaml   # must exit 0
```

`tier` is **proposed by you, ratified by a maintainer** — that ratification is a human
act by design, and a card that self-declares S1 on S3-scale work passes the validator and
still gets re-tiered in review. **S3 carries the routing invariant:** plan approval before
implementation, and a review pass before close.

> Two tier vocabularies live in this repo and do not mix. `S1|S2|S3` is card severity
> (work-order). `XS|S|M|L` is artifact budget tier (output-discipline). A card is never
> tier M; a plan is never tier S2.

## What a pull request has to carry

**1. Red before green.** Every behavior change ships a fixture case with a planted
violation, pinned in that piece's runner to **all** of its named reasons — not just the
first one that fires. A guard nobody has watched fail for the right reason is not a proven
guard. Paste both runs in the PR body: the output before your fix (red, for the named
reason) and after (green).

**2. The tri-state exit contract.** New scripts inherit it from
[`validator/`](validator/README.md): `0` OK/VERIFIED · `1` one `VIOLATION: ...` line per
reason on stderr · `2` NOT-RUN. **Fail closed** — malformed input produces a named
violation, never a traceback. A script that returns 0 because it could not evaluate
anything is the single failure this repo exists to prevent.

**3. Your own residual.** If you touch a piece, update its **"What it does NOT catch"** —
each named gap with the layer that resolves it. A new guard shipped without a residual
section reads as a complete guard, which is a claim this repo does not make. Update the
**Coverage** table in the same edit (Promised · Mechanically covered · Not covered /
known bypass · Classification).

**4. Both READMEs.** `README.md` and `README.pt-BR.md` are peers. A change landing in one
and not the other is an incomplete PR. If you cannot write the pt-BR, say so in the PR and
a maintainer will — do not machine-translate it silently.

**5. No new dependencies without a card that argues for one.** The current floor is
Python 3, plus PyYAML (work-order, receipt-gate), `git` (receipt-gate), and Node
(protect-tests). Anything added has to survive the full CI matrix, including py3.8.

**6. Nothing installs itself.** Every piece is opt-in, per repository. PRs that wire a
hook globally, edit a user-level `~/.claude` path, or add an installer that touches
anything outside the target repo will be declined regardless of merit.

## Prose is not an escape hatch

If your change says an agent *should* do something, name the hook, validator, or exit code
that makes it so. If there is no such mechanism, the sentence belongs in the residual
section, not the rules section. This applies to `starter-claude-md/CLAUDE.starter.md`
especially — every rule there traces to a piece via its `[NN]` tag, and
`check_starter.py` will reject an untagged or dangling one.

## What will not be merged

- **Efficacy claims.** The repo asserts mechanics only; the pilot has not run. A PR cannot
  add "reduces X by Y%" on the repo's behalf, however well-sourced.
- **Vote tallies** attributed to any panel other than the documented five-member one.
- **Fixtures that only prove green.**
- **Deny-list widening without a fixture case per new entry** — `verify` vacuity, privacy
  tokens, protect-tests patterns alike.
- **Vendored code with no `PROVENANCE.md`** recording upstream source, revision, and
  license. See [NOTICE.md](NOTICE.md).
- **Reformatting bundled with behavior change.** Split them; the diff is the review
  surface.

## PR shape

One card, one PR. Title is the card's `goal`, one line. Body carries the card, the red
output, the green output, and the residual you added or amended. CI
(`.github/workflows/verify.yml`) runs `verify_all.py` on ubuntu, windows, and macos plus
py3.8 — green on **all four** is the entry condition, not a nice-to-have. A NOT-RUN on any
leg fails the job by design.

**Branch off `master`'s tip, not off another PR branch.** A branch cut from an unmerged
sibling silently carries that sibling's commits along; if this PR merges first, they land
on `master` without having gone through their own review. `check_pr_base.py` fails the CI
job (exit 1) when a PR's base ref isn't `master` — but it only checks the *base ref*, not
where the branch was actually cut from: a branch aimed at `master` that was nonetheless
forked from a stale local ref can still carry stray commits, and CI only sees them if they
show up in the diff. Rebase (`git rebase origin/master`) before opening the PR if you are
not sure your branch is current.

## Found a bypass?

`privacy-hook` scans for secrets and `protect-tests` guards tests from deletion and
skipping. If you have a working route around either, **do not open a public issue with the
bypass in it.** Use GitHub's private vulnerability reporting (Security tab → Report a
vulnerability). Known residual forging routes are already documented and pinned in
fixtures — check the piece README first; you may be looking at a gap that is already
named.

## What only a human decides

CI does not read for sense. Maintainers do, and these are the questions they answer:
whether `verify` is actually relevant to `goal`, whether `non_goals` is narrow enough to
make the diff reviewable, whether an attached `repro` is real, and whether the proposed
tier is the right one. Each piece's `ADOPTION.md` carries its own version of this list.

## License

MIT. By contributing you agree your contribution is licensed under it. The
`protect-tests/vendor/` exception is recorded in [NOTICE.md](NOTICE.md) and is not
affected.
