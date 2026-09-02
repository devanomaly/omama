# privacy-hook

> Docs for this piece: **README** (promise, command, states, coverage) ·
> [EVIDENCE.md](EVIDENCE.md) (corpus, probes, mutations, red-green history) ·
> [ADOPTION.md](ADOPTION.md) (installation and human decisions)

## The decision this piece changes

Decides **where the sensitive-content deny-list lives**: not in a dev's
head, not in code review, but in a pre-commit hook that blocks locally,
before anything leaves for the remote. The key pattern is **fail
closed**: if the config file (`privacy-deny.json`) doesn't exist, is
corrupted, or the referenced `tokens_file` has gone missing, the commit
is blocked with a specific diagnostic — each of these paths has a red
case in the corpus (the four `fail-closed-*`, all rc=1;
[EVIDENCE.md](EVIDENCE.md)).

## What it is

A Python `pre-commit` hook that scans **staged** content (not the
working tree, not history) and blocks the commit across four layers:

1. **Forbidden filename** (`privacy-deny.json` → `deny_filenames`):
   regex applied to **every path component**, not just the basename —
   so `^\.env$` also catches a *directory* named `.env`.
2. **Forbidden literal token** (`tokens_file`, a text file referenced by
   the JSON): one literal per line, byte-exact — internal codenames and
   hostnames, any sensitive string not worth turning into a regex.
3. **Team regex** (`privacy-deny.json` → `deny_regexes`).
4. **Patterns built into the script** — a SHORT list of structural,
   vendor-documented formats that are credentials by construction: AWS
   access key (`AKIA`/`ASIA` and the other documented key-id prefixes),
   classic GitHub token (`ghp_`/`gho_`/`ghu_`/`ghs_`/`ghr_`) and
   fine-grained (`github_pat_`), Anthropic key (`sk-ant-`), Slack token
   (`xox`), PEM private-key block, PuTTY key, and credentials embedded
   in a URL (`user:pass@host`, scheme in any case). "Long
   random-looking string near a suggestive name" **does not** meet the
   bar — see the scope cut below.

Layers 1 and 2 are the reason this hook exists **alongside**
gitleaks/trufflehog instead of pretending to replace them: no
maintained ruleset knows your client's codename or your jump host's
hostname. The content layers (2, 3, and 4) run over the staged blob
**and over its wide-Unicode reading**; layer 1 runs over the path.
Nothing in this directory depends on any project, client, or personal
path.

Design properties (case-by-case receipts in
[EVIDENCE.md](EVIDENCE.md)):

- **The scope cut.** Generic detection of "`<secret-looking key> =
  <high-entropy value>`" **no longer exists in this piece**. The
  measurement that killed it: a new attack produced **16 functional
  bypasses AND 16 false positives against the same rule**, and each
  patch traded one class for the other at roughly 1:1 — every bypass
  was a scoring point the value-class didn't model (`{`, `<`, `%`, `'`,
  backtick, URL value); every false positive was ordinary repo content,
  from dev URLs in `docker-compose.yml` to Terraform's
  `random_password` (the full list lives in the corpus as `neg-fp-*`).
  A hook that blocks `docker-compose.yml` gets uninstalled — **total**
  loss of protection, not partial. That class is a solved problem
  OUTSIDE this file (gitleaks, trufflehog: maintained, calibrated
  rulesets) and an unsolved one in a hand-rolled regex. So: no generic
  value-attribution rule, no entropy heuristic, no "warn but let
  through" mode — blocking is blocking. The cut is encoded as tests:
  the 16 false positives sit in the corpus **verbatim** as green cases
  (`neg-fp-*`) and 6 tripwires (`neg-tripwire-*`) charge rc=0 for
  payloads that **are** secrets — whoever reintroduces a broad
  value-based rule sees the corpus turn red on these cases first.
- **The built-in allowlist.** Two literal lists in `scan_staged.py` —
  no regex, no fuzzy prefix, every entry justified on the line above
  it: `ALLOWLIST_LITERALS` (built-in-pattern matches that are a
  published documentation example, such as AWS's own example key id)
  and `LOCAL_DEV_URL_CREDENTIALS` (`user:password` pairs that are a
  published default for a local dev service: `postgres:postgres`,
  `guest:guest`, `root:example`, `admin:admin`, `user:password`). The
  allowlist only suppresses a **built-in-pattern** match; it never
  touches `deny_filenames`, `deny_regexes`, or the literal token. Cost
  declared up front: the URL pair is compared **without looking at the
  host** — one of these pairs against a production hostname also
  commits clean; accepted as a deliberate case (a production database
  with password `postgres` is already lost, and host heuristics are
  exactly the kind of guessing this piece stopped doing). Changing one
  character on either half of the pair goes back to blocking.
- **Encoding.** Every blob is scanned as (a) its raw bytes **and** (b)
  the UTF-8 re-encoding of every wide-Unicode reading that decodes
  cleanly (UTF-16 LE/BE and UTF-32 LE/BE, with or without BOM) — UTF-16
  is PowerShell's `Out-File -Encoding unicode` default, and a single
  "save as" used to knock out all three content layers at once. The
  attempt only happens when there are NUL bytes in the first 4 KB
  (`WIDE_PROBE_BYTES`) and the blob is under 8 MB (`WIDE_MAX_BLOB`) —
  both limits are parameters at the top of `scan_staged.py`, at no cost
  on large binaries.
- **What counts as "staged".** `--diff-filter=ACMRT`: added, copied,
  modified, **renamed**, and type change. `R` is the point it's easy to
  forget: `git mv settings.txt .env` is a rename, not "new file" — a
  filter with only `ACM` would let it through. Out of scope: `D` (the
  path won't exist in the commit) and `U` (git refuses to commit with
  an open conflict). Index entry without a blob: a submodule pointer
  (gitlink, mode `160000`) is a 20-byte commit id, with no content to
  leak — it is **skipped**, not blocked; but the `deny_filenames` check
  runs **BEFORE** the skip, because a gitlink has no blob but does have
  a path, and the filename policy is about paths — a submodule named
  `.env` gets blocked (red-green in [EVIDENCE.md](EVIDENCE.md)).
  `unreadable-staged-blob` remains a hard block for everything else —
  the fail-closed branch for a blob the hook genuinely couldn't read.
  The hook uses `git diff --cached --raw -z` precisely to see the mode.
- **The config's own exemption, narrowed.** `privacy-deny.json` and the
  `tokens_file` contain, by definition, the very strings they define —
  scanning everything would block the config on every edit of itself.
  The exemption exists, but on two narrow axes: (1) only the
  self-referential layers are suppressed (`deny_regexes` and literal
  tokens); the built-in patterns still apply to these files; (2) the
  comparison is exact on the relative path git reports — not
  `os.path.normcase`, so a case variant of the name does **not**
  inherit the exemption (on a case-insensitive filesystem the cost is
  scanning a config with unexpected case — failing **closed**).
- **Output pasteable into a team channel.** Only the `rule id` and the
  staged file's **relative path**, never the content that matched the
  pattern, never an absolute path, never a traceback. Findings go to
  stdout; config-error diagnostics to stderr, each specific
  (`missing-config`, `bad-config`, `missing-tokens-file`,
  `no-python-interpreter` — literal messages in
  [EVIDENCE.md](EVIDENCE.md)).
- **The `pre-commit` wrapper.** It **searches** for the interpreter
  with `command -v`, in order `py -3` → `python3` → `python`, instead
  of reacting to the scanner's exit code — the old form discarded the
  fail-closed diagnostics' stderr and duplicated every finding on a
  blocked commit (receipts in [EVIDENCE.md](EVIDENCE.md)). With none of
  the three available: `BLOCKED hook-error no-python-interpreter`,
  exit 1.
- **One knob for the scanner's location.** The wrapper reads
  `PRIVACY_HOOK_SCANNER`, a single variable at the top defaulting to
  `<repo-root>/scan_staged.py`, so an adopter who vendors the scanner
  under `tools/` sets a variable instead of editing the wrapper body —
  an edited wrapper is no longer byte-identical with upstream, which is
  what turns the next update from a copy into a merge. The path is
  **validated and fails closed**: nothing there means
  `BLOCKED hook-error missing-scanner`, exit 1, never a silent fallback
  to the default location (a hook that scans a file the adopter did not
  choose is the failure this piece exists to prevent). The diagnostic
  itself names the knob, not the path — the only path in the output is
  the value the adopter typed, echoed by the notice — so hook output
  stays pasteable. And an override that IS honoured **announces
  itself**: whenever the variable is set, the wrapper writes
  `notice privacy-hook: scanner = <value> (PRIVACY_HOOK_SCANNER is set; …)`
  to its stderr before scanning, keeping stdout for the verdict lines
  (through `git commit` you see both on stderr: git folds a hook's
  stdout into its own stderr; the split matters to a chained hook or a
  CI step that pipes the wrapper's output). The value comes from the
  ambient environment — a shell profile, a direnv file, a CI job env —
  so unlike the wrapper it appears in no diff; the notice is the only
  place a redirected scan becomes visible, and an unexpected one on a
  repo you never configured is the signal. Four polarities in
  `fixture/case_scanner_override.py`: the relocated scanner produces the
  default location's verdict **byte for byte**, a broken override blocks
  with the named `hook-error`, an honoured override prints the notice
  naming its value, and the wrapper invoked directly keeps that notice
  on stderr with the verdict on stdout.
- **The wrapper ends in `exec`.** Nothing written after it runs, and it
  fails silently that way — so a repo that already has a `pre-commit`
  runs its own checks BEFORE the scan. That is an
  [ADOPTION.md](ADOPTION.md) instruction with a verbatim combined-hook
  example, not a mechanism: nothing in this piece can detect a chained
  hook that put the scan first.

## Command and states

Installed as the repo's `pre-commit` hook — a versioned `.githooks/`
directory activated with `git config core.hooksPath .githooks`, or a
copy into `.git/hooks/` (see [ADOPTION.md](ADOPTION.md)) — and runs on
every `git commit`. Direct invocation, from the adopting repo's root:

```
python3 scan_staged.py
```

| Exit | State | Means |
|---|---|---|
| 0 | OK | nothing staged matched any layer; the commit proceeds |
| 1 | BLOCKED | one `BLOCKED <rule-id> <relative path>` line per finding (stdout) — or a fail-closed `hook-error` diagnostic (stderr): missing/malformed config, missing `tokens_file`, no Python interpreter |

`git commit`'s own return code mirrors the hook's exit — that's what
the corpus charges. Fixture:
`python3 fixture/check.py` (exit 0 = hook correct). Per-case detail,
probes, and mutations: [EVIDENCE.md](EVIDENCE.md).

## Scope and limits

### What it catches

Corpus of **55 cases (28 block / 27 pass), 0 failed**, run of
2026-08-18, plus the dedicated gitlink, scanner-override and
versioned-hooks-plus-merge cases — the case-by-case list,
with charged outputs, lives in [EVIDENCE.md](EVIDENCE.md). Classes
covered, all with rc=1:

- **all 8 built-in credential formats**, each with its own case in the
  corpus (including AWS's STS prefix and the two URL variants);
- **forbidden filename in any path component**: added file, *directory*
  named `.env`, rename via `git mv` — and, since the 5th external
  review (2026-08-18), a **gitlink named `.env`**: the `deny_filenames`
  check now runs before the gitlink skip. Red-green receipt: the old
  scanner (commit `ce14aab`) let this commit through with exit 0; the
  new one answers `BLOCKED deny-filename .env`, exit 1, with a green
  control (gitlink `vendor-lib` still commits — the blob-read skip for
  gitlinks stays intact). Fixture: `fixture/case_gitlink.py`, both
  polarities;
- **team literal token** and **team regex**;
- **content never denied that arrives via rename** (committed earlier
  with `--no-verify`, blocks on the rename);
- **UTF-16 text**, with and without BOM, and an **uncompressed zip**
  (the secret's literal bytes are still visible);
- **secret inside the config itself**: an AWS key and a PEM block in
  `privacy-deny.json`, `tokens_file` redirected to an application file
  with a credential inside, a case variant of the config's name;
- **broken or missing config**: the four `fail-closed-*` cases, each
  charging the promised diagnostic.

### What it does NOT catch

Each route named with the receipt that demonstrates it (probes P1–P11
in [EVIDENCE.md](EVIDENCE.md)) and with the tool or layer that resolves
it — none of these is a "generic limitation."

- **Generic high-entropy secret outside the 8 formats.** Removed on
  purpose (see the scope cut): a strong password with punctuation and
  `"password"` quoted in JSON commit clean (`neg-tripwire-*` cases,
  rc=0). Resolved by: **gitleaks / trufflehog in CI** — a maintained,
  calibrated ruleset, which is exactly what this piece deliberately
  does not reimplement.
- **`git commit --no-verify`.** Probe P1, rc=0 — the secret enters
  history. Resolved by: a server-side **`pre-receive` hook and/or a CI
  scanner**; the local hook is a guard-rail against carelessness, not a
  security control.
- **Commits created without going through the commit hook.**
  `git cherry-pick` of a contaminated commit lands the secret on HEAD
  (probe P4, rc=0). `git am` and `git rebase` follow the same git
  design and weren't probed. Automatic merge has coverage **if**
  [ADOPTION.md](ADOPTION.md)'s `pre-merge-commit` is installed as the
  same hook git calls on commit — `fixture/case_hookspath_merge.py`
  charges a `--no-verify` leak on a colleague's branch being refused on
  the merge — and none at all if it is not. Resolved by: **CI / pre-receive**, which
  sees the finished commit regardless of how it was created.
- **Secret already committed to history.** The hook only looks at the
  current commit's index: after a `--no-verify`, the following
  (innocent) commit passes and the secret stays (probe P1). Resolved
  by: **history scanning** (`gitleaks detect`, `trufflehog git`) and
  remediation with `git filter-repo`/BFG **plus rotating the
  credential**.
- **Content encoded or compressed on purpose.** Base64 of the AWS key:
  rc=0 (probe P2). Zip **with** compression: rc=0 (probe P7b). Resolved
  by: container extensions in `deny_filenames` (e.g.
  `\.(zip|7z|xlsx|docx|sql|dump)$` — not wired in by default because it
  would block legitimate assets) and a CI scanner that opens
  containers.
- **Wide encoding outside the probe window.** No NUL byte in the first
  4 KB — all-CJK text (probe P5, rc=0); blob over 8 MB (probe P6,
  rc=0). Resolved by: raising `WIDE_PROBE_BYTES` / `WIDE_MAX_BLOB` at
  the top of `scan_staged.py` and paying the scan cost; CI covers the
  rest.
- **Spelling variant of a literal token.** `tokens_file` is byte-exact:
  with `EXAMPLE-DENY-TOKEN` in the list, `example-deny-token` commits
  clean (probe P3, rc=0). Resolved by: **one line per spelling**
  (snake_case, kebab-case, CamelCase, prose).
- **Config diverging between working tree and index.** The config is
  read from the **working tree**: neutralizing it there (without
  staging it) turns off the team layers for the staged content (probe
  P8, rc=0). Resolved by: PR review of the config (it's versioned) and
  **CI/pre-receive running against the committed config**, not the
  local one.
- **Binary private key (DER, PKCS#12).** Only PEM and PuTTY have
  built-in patterns; a binary `.pfx` commits clean (probe P9, rc=0).
  Resolved by: `deny_filenames` (e.g. `\.(pfx|p12|der)$`).
- **Team content inside `tokens_file` itself.** The path pointed to by
  `tokens_file` is exempt from the team layers: a hostname matching
  `deny_regexes` inside it commits clean (probe P10, rc=0); the
  built-in patterns still apply there (`tokens-file-redirect`, rc=1).
  Resolved by: the config is versioned and reviewable in a PR — that's
  where this redirection gets contained.

- **A scanner override that points at the wrong script.**
  `PRIVACY_HOOK_SCANNER` is checked for **existence**, not identity: an
  override aimed at any readable file runs that file and the commit is
  decided on its terms — an empty file makes the hook a no-op that
  passes the existence check. Not a new privilege (whoever can set the
  hook's environment can already run code as the committing user), but a
  typo that lands on another script decides commits on its terms.
  Reviewing the versioned hook does **not** contain this: the knob is
  read from the **ambient environment**, so a value exported by a shell
  profile, a direnv file, a CI job env or a stale launcher from another
  repo lives in no diff and redirects the scan in every repo on that
  machine. Reduced by: the wrapper **announcing** the value on stderr
  whenever the variable is set (`fixture/case_scanner_override.py`
  charges it) — that turns a silent no-op into a line the committer
  sees, but it is a notice, not a check, and nothing verifies that what
  the value points at is `scan_staged.py`. Resolved by:
  **CI/pre-receive**, which does not read the local hook or its
  environment at all.
  <br>Second-order: the notice echoes the knob's value verbatim, so an
  adopter who sets an absolute path gets that path in the hook's output
  — the only place this piece prints one, and it prints a value the
  adopter typed, never one it discovered.
- **A chained hook that runs the scan first.** The wrapper ends in
  `exec`, so a combined `pre-commit` that calls it before the repo's own
  checks turns those checks into dead code — silently. Nothing in this
  piece detects the order. Resolved by: **PR review** of the combined
  hook (versioned route) and CI running the same checks.
- **A clone where the hook was never activated.** `core.hooksPath` and
  the `.git/hooks` copy both live in `.git/`, which is not versioned:
  a fresh clone that skipped the one-time step has **no hook**, and
  nothing says so. Resolved by: **CI / pre-receive**, which sees the
  pushed commit regardless of what ran locally.

### What only a human decides

See [ADOPTION.md](ADOPTION.md) — deny-list vocabulary, allowlist
entries, triaging a BLOCKED, accepting residuals, `pre-merge-commit`,
`tokens_file` outside git, which install route (versioned `.githooks/`
vs `.git/hooks`), and where `scan_staged.py` lives.

### Coverage, promise by promise

| Promised | Mechanically covered | Not covered / known bypass | Classification |
| --- | --- | --- | --- |
| Block the 8 built-in formats in staged content | 13 block cases in the corpus (rc=1), including the 3 `allowlist-*` cases that prove the allowlist isn't fuzzy | `--no-verify` (P1, rc=0); `cherry-pick` (P4, rc=0); base64 (P2, rc=0); compressed zip (P7b, rc=0) — route: pre-receive + gitleaks in CI | defect |
| Block forbidden filename in any path component, rename included | `deny-filename-added` / `-directory` / `-via-rename` (rc=1); gitlink named `.env` (`fixture/case_gitlink.py`, red-green against `ce14aab`); mutation M5 goes red only in `deny-filename-directory`, M6 in both rename cases | same local-hook bypasses as above; `T` (typechange) is in the filter but has no case in the corpus | defect |
| Block team literal token | `deny-token-literal` (rc=1) | spelling variant passes (P3, rc=0) — route: one line per spelling | defect |
| Block team regex | `deny-regex-internal-hostname` (rc=1) | config neutralized in the working tree turns off the layer (P8, rc=0) — route: CI with the committed config | defect |
| Generic high-entropy secret | none — capability removed on purpose; 6 tripwire cases charge the rc=0 so silent reintroduction goes red | the entire class — route: gitleaks / trufflehog in CI | defect |
| Fail-closed on missing / malformed config / missing tokens_file | 4 `fail-closed-*` cases (rc=1), each charging the diagnostic in the output | the `bad-tokens-file` branch (file present but unreadable) has no case or probe | not assessed |
| Scan the blob's wide-Unicode reading | `utf16le-builtin-pattern`, `utf16-bom-deny-token` (rc=1); mutation M1 goes red only on these 2 | no NUL in the first 4 KB (P5, rc=0); blob >8 MB (P6, rc=0) — route: raise `WIDE_PROBE_BYTES` / `WIDE_MAX_BLOB`, or CI | defect |
| Config exemption restricted to self-referential layers | `secret-inside-deny-config`, `tokens-file-redirect`, `case-variant-config-name` (rc=1); P11 (rc=1); mutations M2/M3 go red only on these cases | content that only the team layers would catch, inside `tokens_file` itself, passes (P10, rc=0) — route: PR review of the config | defect |
| Pasteable output: no matched value, no absolute path, no traceback | absence of absolute path is charged on **all** 55 cases; `Traceback` forbidden on the 2 malformed-config cases; echoing the value forbidden on 6 cases | non-echo of the value is not charged on the remaining rules; the override notice echoes `PRIVACY_HOOK_SCANNER` verbatim, so an adopter who sets an absolute path sees it — a value they typed, not one the hook discovered | not assessed |
| Automatic merge covered via `pre-merge-commit` | `fixture/case_hookspath_merge.py`: route (a) + step 2c + step 3 composed — a key committed `--no-verify` on a colleague's branch is refused on the automatic merge by the scanner's verdict (rc=1); a clean automatic merge goes through (rc=0) with the notice proving the hook ran; red against the old step 3 (bare wrapper under the second name: every merge refused with `missing-scanner`) | route (b) `.git/hooks` copy of `pre-merge-commit` not exercised; `git am`, `git cherry-pick` (P4, rc=0) and `git rebase` bypass every local hook — route: CI / pre-receive | defect |
| Scanner location overridable without editing the wrapper | `fixture/case_scanner_override.py`: a scanner moved to `tools/` and reached through `PRIVACY_HOOK_SCANNER` reproduces the default location's `BLOCKED` lines exactly; an override pointing at a missing file blocks with `hook-error missing-scanner` (rc=1), no traceback, no absolute path; an override that IS honoured prints `notice privacy-hook: scanner = <value>`, charged through `git commit`; the wrapper invoked directly keeps that notice on stderr and the verdict on stdout (through git the two streams are folded together, so the split is charged on a direct run) | existence is validated, identity is not — an override aimed at another readable script runs that script, and the notice announces the redirection without checking it; the value comes from the ambient environment, so no diff carries it — route: CI / pre-receive | defect |
| Hook active in every clone (versioned `.githooks/` + `core.hooksPath`) | none — the activation is a per-clone `git config`, and `.git/config` is not versioned | a clone that never ran it has no hook and nothing warns — route: CI / pre-receive | not assessed |
| Scan runs after an existing `pre-commit`'s own checks | none — chaining is an adoption instruction with a verbatim example | a combined hook that calls the wrapper first makes its own checks dead code (`exec`), undetected — route: PR review of the versioned hook | not assessed |

Accepting a residual requires a named human signature and a date. No
row in this table becomes "accepted" by existing here: `defect` marks a
bypass demonstrated by a run this round, with the resolving route
named; `not assessed` marks a named route without a probe — neither one
is a license.
