# 01 — privacy-hook · EVIDENCE

Probes, cases, and red-green history. The [README](README.md) carries
the promise; this file carries the receipts. All are from real runs —
2026-08-18 unless a section says otherwise (the scanner-override section
is from 2026-08-23): `fixture/check.py` with exit 0
(`corpus: 55 cases (28 block / 27 pass), 0 failed`) and standalone
probes (`python3`, each in a temporary git repo with the hook installed
byte-for-byte by the same `lib.make_repo` used by the corpus). `rc` is
always `git commit`'s own exit code — never an internal call inside the
scanner.

## How to run

```
cd privacy-hook/fixture
python3 check.py                    # smoke cases + gitlink + override + full corpus
python3 case_corpus.py              # tabulated corpus only
python3 case_gitlink.py             # gitlink case only (both polarities)
python3 case_scanner_override.py    # PRIVACY_HOOK_SCANNER case only (four assertions)
```

`check.py` runs five scripts and charges each one's polarity:
`case_violation.py` (fake AWS key + deny-listed token — **must fail**),
`case_clean.py` (ordinary Python file — **must pass**),
`case_gitlink.py` and `case_scanner_override.py` (both self-reporting,
see the sections below), and `case_corpus.py`. In the
corpus, each case gets **its own** temporary repo (inside
`fixture/.tmp/`, never outside it), is staged the way the case defines
it (`git add`, `git mv`, `git rm`, `git update-index`, nested
submodule), and does a real `git commit`. Besides polarity, a case can
charge a string the output **must not** contain (the secret's value,
`Traceback`) and one it **must** contain (the promised diagnostic);
**every** case, without exception, charges that no absolute path
appears in the output.

## Corpus — the 28 block cases (rc=1)

Literal outputs from the 2026-08-18 run:

| Case | Charged output |
|---|---|
| `builtin-aws-access-key-id` | `BLOCKED aws-access-key config/aws.env` |
| `builtin-aws-sts-key` | `BLOCKED aws-access-key sts.env` |
| `builtin-github-classic-token` | `BLOCKED github-token ci.env` |
| `builtin-github-fine-grained-pat` | `BLOCKED github-pat ci.env` |
| `builtin-pem-private-key` | `BLOCKED private-key-block deploy/server_key` |
| `builtin-putty-private-key` | `BLOCKED putty-private-key server.ppk` |
| `builtin-anthropic-key` | `BLOCKED anthropic-key svc.env` |
| `builtin-slack-token` | `BLOCKED slack-token svc.env` |
| `builtin-url-credentials-upper-scheme` | `BLOCKED url-credentials conn.txt` |
| `builtin-url-credentials-slash-in-pass` | `BLOCKED url-credentials conn2.txt` |
| `allowlist-aws-doc-key-one-char-off` | `BLOCKED aws-access-key app/boot.py` |
| `allowlist-url-pair-one-side-changed` | `BLOCKED url-credentials docker-compose.yml` |
| `allowlist-mixed-allowlisted-and-real` | `BLOCKED url-credentials docker-compose.yml` |
| `deny-filename-added` | `BLOCKED deny-filename .env` |
| `deny-filename-directory` | `BLOCKED deny-filename .env/local` |
| `deny-filename-via-rename` | `BLOCKED deny-filename .env` |
| `deny-token-literal` | `BLOCKED deny-token notes/internal.md` |
| `deny-regex-internal-hostname` | `BLOCKED deny-list:internal-hostname docs/runbook.md` |
| `secret-content-via-rename` | `BLOCKED aws-access-key archive/notes.txt` |
| `utf16le-builtin-pattern` | `BLOCKED aws-access-key keys.txt` |
| `utf16-bom-deny-token` | `BLOCKED deny-token notes.txt` |
| `secret-inside-deny-config` | `BLOCKED aws-access-key privacy-deny.json` |
| `case-variant-config-name` | `BLOCKED aws-access-key PRIVACY-DENY.JSON` |
| `tokens-file-redirect` | `BLOCKED aws-access-key app/creds.txt` |
| `fail-closed-missing-config` | `BLOCKED hook-error missing-config privacy-deny.json (expected at the repo root; see README: Como adotar)` |
| `fail-closed-missing-tokens-file` | `BLOCKED hook-error missing-tokens-file privacy-tokens.txt` |
| `fail-closed-malformed-config` | `BLOCKED hook-error bad-config privacy-deny.json (unreadable, not valid JSON, or a bad deny_regexes/deny_filenames entry)` |
| `fail-closed-bad-regex-config` | `BLOCKED hook-error bad-config privacy-deny.json (unreadable, not valid JSON, or a bad deny_regexes/deny_filenames entry)` |

The 2 malformed-config cases forbid `Traceback` in the output; 6 cases
charge the non-echo of the secret's value.

## Corpus — the 27 green cases, in three groups

A guard that rejects everything isn't a guard. The three roles:

- **The 16 measured false positives, verbatim** (`neg-fp-*`): each
  payload transcribed byte-for-byte from the receipt of the measurement
  that motivated the scope cut — local-dev URLs in compose/README/docs
  (green via the pair allowlist), AWS's documentation key id in a test
  (green via the literal allowlist), `.env.example` placeholders,
  `password:` as a property in JS/TS/Python, a well-known test-fixture
  password, Terraform's `random_password`, a Bitnami chart default,
  PT-BR prose with a dev value, Django's `SECRET_KEY`
  `django-insecure-...`. If any of these ever blocks again, the corpus
  goes red here.
- **The 6 non-regression tripwires** (`neg-tripwire-*`): payloads that
  **are** secrets (or placeholders the old rule contested) and today
  commit clean on purpose — a strong password with punctuation
  (`DB_PASSWORD=Xy!9kLmNp2QrStUvWx`), `"password"` quoted in JSON
  (`"hunter2hunter2hunter2"`), `.env.example` placeholders, a Django env
  lookup, shell `${VAR}` indirection, an Ansible template. Charged as
  PASS so that reintroducing a broad value-based rule goes red here
  first. It's not a claim that these are safe to commit — it's a claim
  about WHERE this piece's boundary sits; gitleaks/trufflehog in CI is
  the layer that covers them.
- **5 structural**: ordinary source, documentation prose containing the
  word "password", an innocent submodule pointer
  (`neg-submodule-pointer`), an innocent-to-innocent rename, a binary
  blob with all 256 bytes (doesn't become a false positive and doesn't
  break the encoding probe).

## Standalone probes P1–P11

| Probe | Route | rc |
|---|---|---|
| P1 | `git commit --no-verify` with an AWS key staged; the following (innocent, hook active) commit also passes and the secret stays in history | 0 |
| P2 | base64 of the same AWS key | 0 |
| P3 | spelling variant of a literal token (`example-deny-token` with `EXAMPLE-DENY-TOKEN` in the list) | 0 |
| P4 | `git cherry-pick` of a contaminated commit — secret lands on HEAD | 0 |
| P5 | UTF-16 with no NUL byte in the first 4 KB (all-CJK text) | 0 |
| P6 | large blob >8 MB (10,485,820 bytes) | 0 |
| P7 | zip **without** compression containing the key — literal bytes visible | 1 |
| P7b | zip **with** compression (deflate) containing the key | 0 |
| P8 | config neutralized in the working tree (not staged) with a deny-listed token staged | 0 |
| P9 | binary private key `.pfx` (PKCS#12) | 0 |
| P10 | hostname matching `deny_regexes` inside `tokens_file` itself | 0 |
| P11 | PEM block inside `privacy-deny.json` — output `BLOCKED private-key-block privacy-deny.json` | 1 |

## Proof that the red is real (mutation by mutation)

Each mutation isolates one piece of the design, and the corpus goes red
**only** on the cases that piece sustains. All real runs on 2026-08-18,
one at a time, with the full corpus (55 cases), on this folder's
`scan_staged.py` (restored by hash after each run); the right-hand
column is the runner's literal output.

| mutation in `scan_staged.py` | corpus result (literal output) |
| --- | --- |
| M1 — `text_views()` returns only the raw bytes | 2 failures: `utf16le-builtin-pattern`, `utf16-bom-deny-token` |
| M2 — config becomes exempt from ALL layers again | 2 failures: `secret-inside-deny-config`, `tokens-file-redirect` |
| M3 — total exemption **and** case-insensitive (`os.path.normcase`) | 3 failures: the two above + `case-variant-config-name` |
| M4 — gitlink no longer skipped | 1 failure: `neg-submodule-pointer` |
| M5 — `deny_filenames` matches only the basename again | 1 failure: `deny-filename-directory` |
| M6 — `STAGED_CHANGE_FILTER` from `"ACMRT"` to `"ACM"` | 2 failures: `deny-filename-via-rename`, `secret-content-via-rename` |
| M7 — `LOCAL_DEV_URL_CREDENTIALS` emptied | 5 failures: `neg-fp-compose-postgres-url`, `neg-fp-readme-quickstart-urls`, `neg-fp-compose-rabbitmq-guest`, `neg-fp-docs-mongo-root-example`, `neg-fp-docs-curl-admin-admin` |
| M8 — `ALLOWLIST_LITERALS` emptied | aborts at exit 2: `fixture setup failed: BLOCKED aws-access-key scan_staged.py` — the hook blocks the commit of the scanner itself, whose source carries AWS's documentation key id |
| M9 — an allowlisted occurrence shields the rest of the file (`continue`→`break`) | 1 failure: `allowlist-mixed-allowlisted-and-real` |

Three honesty notes:

- The case-fix for the exemption only goes red **together with** the
  scope narrowing (M3 vs M2). Making the comparison case-insensitive on
  its own doesn't leak yet, because the built-in patterns still apply
  to the exempt file. These are two independent fixes for the same
  defect, and both rows record that.
- The 8 built-in patterns don't have their own mutation row this round;
  their coverage comes from a block case each (one per pattern, rc=1)
  — deleting a pattern would drop its case, but that wasn't run as a
  mutation.
- The 6 tripwires can't be proven by mutation: they're already PASS,
  and only go red if someone **writes** a broad value-based rule —
  which is exactly the move they exist to catch.

## Allowlist receipts (genuinely narrow)

- Byte-exact, not a prefix: one character off from the documentation
  key id blocks (`allowlist-aws-doc-key-one-char-off`, rc=1) and the
  same suffix with the STS prefix blocks (`builtin-aws-sts-key`, rc=1).
- One allowlisted occurrence in the file doesn't shield a real
  credential in the same file (`allowlist-mixed-allowlisted-and-real`,
  rc=1; mutation M9 goes red only on this case).
- Changing one character on either half of an allowlisted URL pair goes
  back to blocking (`allowlist-url-pair-one-side-changed`, rc=1).
- Emptying either list breaks exactly the cases it sustains —
  mutations M7 and M8 in the table above.

## Gitlink red-green (5th external review, 2026-08-18)

Bypass confirmed and fixed: a staged submodule pointer (gitlink, mode
`160000`) named `.env` used to pass, because the gitlink skip ran
BEFORE the `deny_filenames` check. `scan_staged.py` now checks the path
before skipping the gitlink.

| Probe | Old scanner (`ce14aab`) | New scanner |
|---|---|---|
| gitlink staged, named `.env` | exit 0 (bypass) | `BLOCKED deny-filename .env`, exit 1 |
| gitlink named `vendor-lib` (green control) | commits | commits — the blob-read gitlink skip stays intact |

New fixture: `fixture/case_gitlink.py` (both polarities), run by
`check.py`. Full corpus re-run today via the root's `verify_all.py`:
OK; direct run of `check.py` at this doc's close:
`corpus: 55 cases (28 block / 27 pass), 0 failed`, exit 0, with
`PASS: gitlink .env blocked, innocent gitlink allowed`.

## Scanner-location override (`PRIVACY_HOOK_SCANNER`), 2026-08-23

The wrapper used to hardcode `<repo-root>/scan_staged.py`, so an adopter
who vendors the scanner under `tools/` had to edit the wrapper body —
and an edited wrapper is no longer byte-identical with upstream. It now
reads one knob. `fixture/case_scanner_override.py` charges four
assertions in one throwaway repo (`lib.make_repo`, hook installed
byte-for-byte, real `git commit`; `rc` is git's own exit code):

| # | Route | Charged output | rc |
|---|---|---|---|
| 1 | baseline — scanner at the default location, `AWS_ACCESS_KEY_ID=AKIA…` staged | `BLOCKED aws-access-key config/deploy.env` | 1 |
| 2 | same violation, scanner moved to `tools/`, `PRIVACY_HOOK_SCANNER=tools/scan_staged.py` | **the same line, byte for byte** — the case charges the output, not the polarity, because an ignored override also fails, just with an interpreter error | 1 |
| 3 | override pointing at a file that does not exist, clean content staged | `BLOCKED hook-error missing-scanner (no scan_staged.py at the configured location; set PRIVACY_HOOK_SCANNER to where it lives)`; no `Traceback`, no absolute path | 1 |
| 4 | override pointing at an **existing** file (`innocuous.py`, zero bytes), violation staged | `notice privacy-hook: scanner = innocuous.py (PRIVACY_HOOK_SCANNER is set; the default is the repo root's scan_staged.py)` on stderr | 0 |

Assertion 4 red-green (external review finding, same date). The knob is
read from the ambient environment — a shell profile, a direnv file, a CI
job env, a stale launcher from another repo — so its value appears in no
diff, and the existence check passes for **any** readable file:

| Wrapper | Commit of the planted key with `PRIVACY_HOOK_SCANNER=innocuous.py` |
|---|---|
| before (default applied quietly) | rc=0, **zero output on both streams**, `git show --stat HEAD` shows `config/deploy.env` in the commit — the fixture's literal red: `FAIL: PRIVACY_HOOK_SCANNER was honoured SILENTLY -- an ambient override redirected the scan and nothing on stdout/stderr said so (rc=0)` |
| after (notice) | rc=0 and the same commit — identity is still not validated — but stderr now carries the `notice privacy-hook: scanner = innocuous.py …` line above |

What that buys and what it does not: the notice makes a redirected scan
**observable**, it does not make it **checked**. The residual row
"scanner override that points at the wrong script" stays a `defect`, and
its route stays CI / pre-receive — reviewing the versioned hook does not
cover a value that lives in the environment. Direct run at this
section's close: `case_scanner_override.py` exit 0, four `PASS` lines.

## `pre-commit` wrapper receipts

The old form
(`python3 "$dir/scan_staged.py" 2>/dev/null || python "$dir/scan_staged.py"`)
got it wrong twice: `2>/dev/null` discarded stderr — exactly where the
fail-closed diagnostics go, so on a PATH with only `python3` (the
Debian/Ubuntu shape) a dev with a missing config saw only
`python: command not found`; and `||` fires on **any** non-zero exit,
including exit 1 for "successfully blocked" — every blocked commit
scanned the index twice, duplicating every finding.

Verified on the fix round's rig: with a PATH containing only `python3`
and no `privacy-deny.json`, the output is
`BLOCKED hook-error missing-config privacy-deny.json (...)`, exit 1;
with the config present and a secret staged, `BLOCKED aws-access-key
leak.txt` appears **once**, exit 1; with none of the three
interpreters, `BLOCKED hook-error no-python-interpreter (...)`, exit 1.
(Receipts from that round; this round the wrapper ran across all 55
corpus cases via `py -3`, the first probe on Windows.)

## Scratch cleanup (`fixture/.tmp/`)

Each corpus case deletes its own repo when it passes and preserves it
when it fails; `case_violation.py` and `case_clean.py` leave their repo
behind on purpose, for post-mortem. Re-measured on 2026-08-18: starting
from an empty `.tmp/`, a clean run of `check.py` leaves exactly **2**
directories (the two smoke cases), zero `WARN`. Before, an entirely
green run left one directory per case — **74 measured on a clean run**,
with `shutil.rmtree(tmp, ignore_errors=True)`, the flag that hides the
failure. Two causes, both Windows: (1) loose git objects are read-only
and Windows refuses to unlink them; (2) right after `git commit`, the
directory is still held by a child process exiting —
`PermissionError(13)` on `rmdir`, which resolves in 1–2 retries at
150 ms. `lib.rmtree()` covers both, **returns** whether it succeeded,
and the corpus prints `WARN: scratch tree not removed` when it
couldn't, instead of leaving a silent leftover. `fixture/.tmp/` is in
the local `.gitignore`.
