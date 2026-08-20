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
2. Copy `pre-commit` to the adopting repo's `.git/hooks/pre-commit` and
   grant execute permission:
   ```
   cp pre-commit <REPO_ROOT>/.git/hooks/pre-commit
   chmod +x <REPO_ROOT>/.git/hooks/pre-commit
   ```
   On Windows, git for Windows already runs `.sh`-style hooks via its
   bundled Git Bash — no `chmod` needed.
3. **Recommended:** copy the same file to `pre-merge-commit`. git
   doesn't call `pre-commit` on an automatic merge — it calls
   `pre-merge-commit`. Without this, merging a colleague's branch that
   doesn't have the hook installed produces, on YOUR machine, a local
   commit with their secret.
   ```
   cp pre-commit <REPO_ROOT>/.git/hooks/pre-merge-commit
   ```
   `git am`, `git cherry-pick`, and `git rebase` remain **out of
   reach** (probe P4: cherry-pick lands the secret with rc=0) — see
   "Reach and limits" in the [README](README.md).
4. Commit `scan_staged.py` and `privacy-deny.json` in the repo (the
   hook itself, under `.git/hooks/`, **is not versioned by git** — each
   dev/clone needs to install steps 2 and 3). If the team uses the
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

## Complementary checks (outside this piece)

- **Generic high-entropy secret and history**: gitleaks / trufflehog in
  CI (the generic half this piece deliberately doesn't reimplement) and
  history scanning (`gitleaks detect`, `trufflehog git`) with
  `git filter-repo`/BFG remediation **plus rotating the credential**.
- **Local-hook bypass** (`--no-verify`, cherry-pick/am/rebase): a
  server-side `pre-receive` hook and/or a CI pipeline scanner — which
  sees the finished commit regardless of how it was created, and runs
  against the committed config, not the local one.
