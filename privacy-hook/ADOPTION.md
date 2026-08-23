# 01 — privacy-hook · ADOPTION

Installation and human decisions. The mechanics and limits are in the
[README](README.md); the receipts are in [EVIDENCE.md](EVIDENCE.md).

## How to adopt (step by step)

Plain git repo (no `pre-commit` framework):

1. Copy to the adopting repo's root:
   - `scan_staged.py`
   - `privacy-deny.json` (edit the deny-list for your team)
   - optionally your own `privacy-tokens.txt` (or rename it and adjust
     `tokens_file` in the JSON)

   `scan_staged.py` does not have to sit at the root: to keep the root
   clean, put it under e.g. `tools/` and tell the hook where it is with
   `PRIVACY_HOOK_SCANNER` (step 2c). `privacy-deny.json` and the
   `tokens_file` are **not** movable — the scanner resolves those from
   the repo root (step 5).
2. Install the wrapper as the repo's `pre-commit` hook. Two routes, and
   the versioned one comes first.

   **(a) Versioned hooks directory — recommended.** Commit the wrapper
   under a tracked directory, then point git at that directory once per
   clone:
   ```
   mkdir -p <REPO_ROOT>/.githooks
   cp pre-commit <REPO_ROOT>/.githooks/pre-commit
   chmod +x <REPO_ROOT>/.githooks/pre-commit
   git -C <REPO_ROOT> add .githooks/pre-commit
   git -C <REPO_ROOT> config core.hooksPath .githooks
   ```
   The `git config` line is still per clone — `core.hooksPath` lives in
   `.git/config`, which is not versioned either — but the hook ITSELF
   now is: it appears in diffs, gets reviewed in a PR, and reaches every
   colleague through `git pull` instead of a re-copy nobody remembers.

   The trade-off, stated: **versioned** = reviewable and shared, one
   `git config` per clone; **`.git/hooks`** = invisible to git,
   re-installed by hand in every clone, never reviewed. Two costs of
   route (a) to know before choosing it: `core.hooksPath` needs
   **git ≥ 2.9**, and it **replaces** the hooks directory wholesale —
   any hook still sitting in `.git/hooks` stops running the moment it is
   set, so move those into `.githooks/` first.

   If the wrapper is versioned, pin its line endings in the adopting
   repo's `.gitattributes` (`.githooks/pre-commit text eol=lf`). A
   wrapper checked out with CRLF dies with `bad interpreter: /bin/sh^M`
   on Linux and macOS — this repo's own `.gitattributes` exists because
   that shipped once.

   **(b) `.git/hooks` copy — fallback**, for a git older than 2.9 or a
   repo that must keep `.git/hooks` in charge:
   ```
   cp pre-commit <REPO_ROOT>/.git/hooks/pre-commit
   chmod +x <REPO_ROOT>/.git/hooks/pre-commit
   ```
   On Windows, git for Windows already runs `.sh`-style hooks via its
   bundled Git Bash — no `chmod` needed.

   **(c) If `scan_staged.py` is not at the repo root**, point the hook
   at it with `PRIVACY_HOOK_SCANNER` instead of editing the wrapper.
   Keep the shipped wrapper as its own file (say
   `.githooks/privacy-pre-commit`) and make the hook git calls a
   two-line launcher that sets the variable and hands over:
   ```sh
   #!/bin/sh
   # .githooks/pre-commit
   PRIVACY_HOOK_SCANNER=tools/scan_staged.py
   export PRIVACY_HOOK_SCANNER
   exec sh .githooks/privacy-pre-commit
   ```
   (Same shape as the combined hook under "Chaining" below — one file
   the repo owns, one file kept byte-identical with upstream.) A
   relative value resolves against the repo root, because git runs hooks
   from the top of the worktree. Editing the wrapper body instead is
   what this knob exists to avoid: an edited wrapper is no longer
   byte-identical with upstream, and the next update becomes a merge.
   The path is **validated**: if nothing is there, the hook blocks with
   `BLOCKED hook-error missing-scanner` (exit 1) — it never falls back
   to the default location silently. Fixture:
   `fixture/case_scanner_override.py`.
3. **Recommended:** install the same wrapper file under the name
   `pre-merge-commit` as well (this piece ships one hook file; the
   second name is a copy of it). git doesn't call `pre-commit` on an
   automatic merge — it calls `pre-merge-commit`. Without this, merging
   a colleague's branch that doesn't have the hook installed produces,
   on YOUR machine, a local commit with their secret.
   ```
   cp pre-commit <REPO_ROOT>/.githooks/pre-merge-commit    # route (a)
   cp pre-commit <REPO_ROOT>/.git/hooks/pre-merge-commit   # route (b)
   ```
   `git am`, `git cherry-pick`, and `git rebase` remain **out of
   reach** (probe P4: cherry-pick lands the secret with rc=0) — see
   "Reach and limits" in the [README](README.md).
4. Commit `scan_staged.py` and `privacy-deny.json` in the repo. With
   route (b) the hook itself, under `.git/hooks/`, **is not versioned by
   git** — each dev/clone re-does steps 2 and 3 by hand; that is exactly
   what route (a) fixes, at the price of one `git config` per clone.
   If the team uses the
   `pre-commit` framework (pre-commit.com), point a `repo: local` hook
   at `python3 scan_staged.py` (Linux/Mac) or `python3 scan_staged.py`
   (Windows — `python3` usually isn't on PATH on a standard Windows
   Python install, only the `py` launcher), with `language: system`,
   `pass_filenames: false`.
5. `scan_staged.py` resolves both `privacy-deny.json` and the
   `tokens_file` from the **git repo root** (`git rev-parse
   --show-toplevel`, not the directory the hook was called from) —
   which is why step 1 says to commit `privacy-deny.json` at the root.
   If the file isn't there, the hook fails closed (blocks every
   commit) with `missing-config privacy-deny.json`.
6. If any `tokens_file` literal is sensitive (e.g. a real client name),
   **don't commit the `tokens_file`** — add it to `.gitignore` and
   distribute it outside git (Slack, secret manager, etc). Without the
   file, the hook fails closed (blocks everything) until it exists —
   set `tokens_file` to `null`/omit it if the team doesn't want this
   layer.
7. Test: `git add` a file with `AKIA` + 16 uppercase/digit chars and
   try to commit — it should block. (Don't use AWS's own documentation
   example key id: it's in the allowlist on purpose.) Equivalent
   automated test: `fixture/check.py`.

## Chaining after an existing pre-commit

The wrapper ends in `exec`. `exec` **replaces** the shell process, so
nothing written after it ever runs — and it runs silently: no error, no
output, the appended checks simply never execute. The first naive
attempt (paste the existing checks at the bottom of the wrapper) loses
them exactly that way.

So a repo that already has a `pre-commit` (lint, formatting, hygiene)
runs its own checks **before** the scan, with the scan last. Keep the
shipped wrapper as its own file and call it from the combined hook —
that keeps it byte-identical with upstream. Verbatim example, with the
wrapper copied to `.githooks/privacy-pre-commit`:

```sh
#!/bin/sh
# .githooks/pre-commit -- repo checks first, privacy scan LAST.

# 1. whatever this repo already ran. Each must exit non-zero to block.
npm run lint --silent || exit 1
./scripts/check-format.sh || exit 1

# 2. privacy-hook last, because it ends in `exec`: nothing after this
#    line runs. PRIVACY_HOOK_SCANNER is optional -- unset means
#    <repo-root>/scan_staged.py.
PRIVACY_HOOK_SCANNER=tools/scan_staged.py
export PRIVACY_HOOK_SCANNER
exec sh .githooks/privacy-pre-commit
```

`exec sh <file>` rather than `exec <file>` so the call does not depend on
the execute bit surviving the clone. Sourcing it last (`. .githooks/privacy-pre-commit`)
is equivalent for this purpose — the wrapper's own `exec` ends the hook
either way. What is **not** equivalent: putting the scan first. Its
`exec` would make the repo's own checks dead code.

## What only a human decides

- **What goes in the deny-list**: which codenames, hostnames, and
  client names are sensitive, and every spelling each of them gets in
  `tokens_file` (the match is byte-exact — one line per spelling). No
  scanner knows the team's internal vocabulary.
- **Each entry in the built-in allowlist**: the two lists in
  `scan_staged.py` are literals, commented line by line specifically so
  they're reviewable — a team that disagrees with an entry deletes the
  line.
- **Whether a BLOCKED is an incident or an input to the config**: a hit can be a
  real secret (rotate the credential, clean history, treat as an
  incident) or a legitimate documentation example (adjust the regex, or
  propose an allowlist entry in a PR). The hook doesn't distinguish;
  triage is human.
- **Accepting any residual from the README's coverage table**, and
  owning the declared cost of each bypass — requires a named human
  signature and a date.
- **Whether to install `pre-merge-commit`** (step 3) and **whether to
  keep `tokens_file` outside git** (step 6) — operational trade-offs
  for the team, not the hook.
- **Which install route** (step 2): a versioned `.githooks/` under
  `core.hooksPath` makes the hook reviewable but takes over the whole
  hooks directory and needs git ≥ 2.9; the `.git/hooks` copy leaves
  everything as it is and is re-done by hand in every clone. Nothing in
  this piece can decide which cost a team would rather pay.
- **Where `scan_staged.py` lives** and therefore what
  `PRIVACY_HOOK_SCANNER` is set to (step 2c) — the hook validates the
  path, but only the team knows whether a vendored `tools/` copy is
  worth the extra line.

## Complementary checks (outside this piece)

- **Generic high-entropy secret and history**: gitleaks / trufflehog in
  CI (the generic half this piece deliberately doesn't reimplement) and
  history scanning (`gitleaks detect`, `trufflehog git`) with
  `git filter-repo`/BFG remediation **plus rotating the credential**.
- **Local-hook bypass** (`--no-verify`, cherry-pick/am/rebase): a
  server-side `pre-receive` hook and/or a CI pipeline scanner — which
  sees the finished commit regardless of how it was created, and runs
  against the committed config, not the local one.
