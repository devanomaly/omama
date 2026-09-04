# adapt/ — EXAMPLE — NOT INSTALLED

Configuration snippet to copy and adapt (piece-04 pattern), plus
`check_wiring.py` — the mechanical "gate presence" check (step 1 of the
self-test below) — and `selftest_orchestrator_close.py`, the orchestrator
close-path proof (step 4). Nothing here is installed in any real repository. The
ordered happy path lives in [QUICKSTART.md](../../QUICKSTART.md); this file
is the reference (env vars, troubleshooting, rationale).

## How a team would adopt it

1. Copy `../receipt_gate.py` into the team's repository (e.g.
   `.claude/hooks/receipt_gate.py`, versioned alongside the code). When
   copying `check_artifact.py` (piece 09) in step 4, use the CARD-03 version
   or newer — it must accept `--budgets-advisory`; an older copy makes the
   gate block every S3 close with a named usage error (fail-closed, but
   blocking).
2. Copy the `hooks` block from `settings.example.json` into the
   **REPOSITORY'S `.claude/settings.json`** — **install is per-repo, NEVER
   in `~/.claude/settings.json`**: the broken-configuration blocks
   (BAD-INPUT, CARD-CONFIGURED-BUT-MISSING) are acceptable precisely because
   the blast radius stays confined to repositories that opted into the gate.
3. Use the **interpreter's absolute path** in the command (not `python3` — if
   the launcher doesn't exist on the host, the shell exits 9009/127, which
   does NOT block: the gate ends up silently absent forever —
   `check_wiring.py`, step 1 of the self-test in step 5, detects exactly
   this state as a named VIOLATION).
4. **Set the environment variables BEFORE the self-test** — this step is not
   optional: if you copy only `receipt_gate.py` out of the omama repo, the
   gate's relative defaults for the validator (02) and the checker (09)
   point to paths that DO NOT EXIST in the team's repo, and every CLOSE
   blocks with `SCHEMA: validator unrunnable` forever. Also copy
   `validate_work_order.py` (and `check_artifact.py`, if using S3 cards)
   into the repo, and export `OMAMA_VALIDATOR` / `OMAMA_CHECK_ARTIFACT`
   pointing to them (or place them at the relative paths the gate
   documents).
5. **Self-test MANDATORY before trusting it — wiring check first, then red
   AND green.**

   **Step 1 — mechanical wiring check** (copy `check_wiring.py` from this
   directory alongside the hook, or run it from the omama checkout):

   ```
   python3 check_wiring.py <repo-root>   # repo-root defaults to the cwd's git toplevel
   ```

   It reads the repo's `.claude/settings.json` AND `settings.local.json`
   (Claude Code merges them — the machine-specific absolute path from step
   3 naturally lands in the untracked local file), resolves every Stop
   hook command, and exits 0 **only** when the exact registered command,
   dry-invoked with EMPTY stdin, answers the gate's own
   `RECEIPT-GATE BLOCK[BAD-INPUT]` block on exit 2 — the block NAME is
   matched, not just the exit code (a Windows-Store python3 stub also
   exits non-zero).

   **It certifies exactly one hook form — the one this page prescribes:**
   a **synchronous** Stop hook of type `command`, written as **one
   shell-form command string** (no `args`), run by the **default hook
   shell** (`shell` absent or `"bash"`), the interpreter's **absolute
   path** first, the copied `receipt_gate.py` as an argument. Claude Code
   accepts other forms; here each is a named `VIOLATION`, never a quiet
   pass: a bare launcher name (`py`, `python3`, `python` — step 3;
   rejected by form even when PATH resolves it here, because PATH is per
   machine), a command with no `receipt_gate.py` argument (an interpreter
   alone, or another script, is not the gate — "gate script missing", in
   both modes, before anything runs), `async: true` /
   `asyncRewake: true` (a background hook cannot block the close — the
   gate is absent), exec-form `command` + `args` (not modeled — write one
   quoted string), `shell: "powershell"` (not modeled), and
   `disableAllHooks: true` in **either** settings file (no hook runs at
   all; a `false` in the other file is not assumed to win).

   `CLAUDE_PROJECT_DIR` is expanded the way the real hook shell does: the
   modeled hook shell is sh on POSIX and Git Bash on Windows (verified
   empirically 2026-08-24 with a live Stop hook on a Git-Bash-equipped
   Windows host; Windows without Git Bash falls back to PowerShell and is
   NOT-RUN here, see below), so `"$CLAUDE_PROJECT_DIR"` /
   `"${CLAUDE_PROJECT_DIR}"` expand (double quotes or none), while
   `%CLAUDE_PROJECT_DIR%`, a placeholder inside **single quotes**, or an
   escaped `\$CLAUDE_PROJECT_DIR` is left literal — dead wiring under the
   modeled shells (and `%VAR%` stays literal under PowerShell too) and a
   named `VIOLATION`, as are
   shell operators (`|| true` would swallow the gate's blocking exit) and
   **any other `$`** left in the command (`$(...)`, `$OTHER_VAR`): the
   real hook is shell-form, so sh would expand or run it, the check cannot
   model it, and a `--static-only` pass on such a string would certify
   PR-author-controlled settings that execute code at every Stop — so it
   is a `VIOLATION` in both modes. Write literal paths plus the
   placeholder, nothing else. A missing interpreter, a wrong script path,
   a bare launcher name, or a command without `receipt_gate.py` is a named
   `VIOLATION` (exit 1) instead of the silent 127/9009 absence; when
   neither settings file
   is readable the result is NOT-RUN (exit 2). With several Stop hooks,
   one working gate is enough for exit 0, but each broken sibling's
   failures are printed as `WARNING:` lines — read them. Re-run the check
   after an interpreter upgrade and on every fresh clone — the adopting
   repo's CI is the natural place; the check DETECTS dead wiring, nothing
   prevents it from going dead later.

   **Windows: Git Bash is established first.** Claude Code runs shell-form
   hooks through Git Bash and falls back to PowerShell when it is not
   installed — where nothing this check certifies is what runs. So on
   Windows the check looks for Git Bash the way Claude Code's own knob
   describes it (`CLAUDE_CODE_GIT_BASH_PATH` when set — authoritative, a
   value pointing at a missing file counts as absent — else `bin/bash.exe`
   next to the `git` on PATH or in the standard Git for Windows
   locations) and answers **NOT-RUN (exit 2), naming Git Bash**, when it
   cannot find one — never `WIRING-OK`. This is a proxy for Claude Code's
   detection, inferred from the documented knob and install paths, not
   read from its source: a Git Bash it cannot see gives a false NOT-RUN
   (fix: set the knob), never a false pass.

   **Not read, by design (residuals, see the README's coverage):**
   user-level `~/.claude/settings.json`, managed policy settings and a
   `claude --settings` override — a `disableAllHooks` or a gate wired in
   any of those is invisible here.

   **Do not confuse "not certified" with "does not work":** an exec-form
   or async hook may be perfectly valid for other purposes. This gate has
   to *block*, and the check only vouches for the one form whose blocking
   it has watched.

   **SECURITY — the default mode EXECUTES the registered command string it
   finds in the settings files** (that dry run is what proves the gate
   answers). Do not run it against a checkout you do not trust — e.g. CI
   that builds fork PRs, where the PR can rewrite `.claude/settings.json`
   to any command. Use `--static-only` there: it resolves the interpreter
   and script paths without executing anything and exits 0 with
   `WIRING-STATIC-OK` — which does NOT prove the gate answers (the script
   is checked by name and existence only); keep the full check (and steps
   2–3) on trusted machines.

   **Steps 2–3 — red AND green close test**, running the EXACT command
   string registered in settings.json (copy-pasted, not retyped): (a) a
   synthetic red close in a scratch repo must produce the BLOCK (exit 2,
   `VERIFY-RED`); (b) a synthetic GREEN close must reach `VERIFIED` (exit
   0, receipt written) — the green test is what catches a forgotten step 4:
   an install with a dead validator passes the red test (it blocks on
   `SCHEMA`) and would never emit VERIFIED, and the wiring check does not
   see the validator either (BAD-INPUT fires before card resolution).
   Testing the script "by hand" validates the script and leaves the wiring
   itself untested — the silent-absence failure one level up. Re-run the
   self-test after an interpreter upgrade AND after any edit to
   receipt_gate.py (a syntax error exits 1 at parse time, before the guard
   exists — the gate looks installed while actually absent).

   **Step 4 — the orchestrator's close path**, only when a dispatching
   session will close worktrees it is not itself running in: run
   `python3 selftest_orchestrator_close.py` (no arguments). Steps 1–3 prove
   the gate answers; this one proves the *session* reaches it, by closing a
   scratch repo through two real print-mode Claude Code sessions — red with
   hooks disabled, green plain — so it costs two sessions and a login and
   stays a developer-machine check, never CI (exit 2 NOT-RUN, named, when
   `claude` is absent). See
   [Closing from an orchestrator](../README.md#closing-from-an-orchestrator-worktree-dispatch).
6. Set up the flow's reproduction requirement: cards live at
   `<repo>/CARD.yaml` (or `OMAMA_CARD` pointing at the active card); the
   close is declared in `CARD.close` (`CLOSE` | `FAILED: <reason>` |
   `UNVERIFIED: <reason>`); the durable receipt is `CARD.receipt.json`.

   Gitignore all four — add this to the adopting repository's `.gitignore`
   (the omama repo itself carries it too):

   ```
   CARD.yaml
   CARD.close
   CARD.receipt.json
   *.receipt.json
   ```

   A card is per task and per machine — versioning it is
   churn on every task and a merge conflict the moment two developers hold
   different cards at the same root. A committed receipt would be worse: it
   binds the hash of the tree it was written against, and the commit that
   adds the receipt file changes that tree by construction, so the hash it
   carries would already be stale for the commit that ships it. Left local,
   the hash stays true. That does not make a VERIFIED close a local-only
   claim: the durable record for review is the `verify` command, its exit
   code, and the receipt's `rev` pasted into the PR body (or equivalent
   review surface) — the receipt file itself never has to leave the machine
   that produced it.

## Environment variables

- `OMAMA_CARD` — path to the active card (empty = disabled; a nonexistent
  path BLOCKS — a typo does not disable the gate).
- `OMAMA_VALIDATOR` — path to validate_work_order.py (piece 02).
- `OMAMA_CHECK_ARTIFACT` — path to check_artifact.py (piece 09, required for
  S3 cards); must be the CARD-03 version or newer (accepts
  `--budgets-advisory`), otherwise the gate blocks every S3 close with a
  usage error.
- `OMAMA_VERIFY_TIMEOUT` — seconds allowed for verify (default 600).

## Troubleshooting

- Receipt locked by an editor/antivirus at deletion time → exit 2,
  observable and retryable — by design, no carve-out.
- `taskkill` (tree kill on timeout) produces localized non-ASCII output; the
  gate already re-wraps stdout/stderr with `errors="replace"`.
