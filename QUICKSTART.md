# Quickstart — install Omama and close your first task

*[Versão em português](QUICKSTART.pt-BR.md)*

This page has two parts. **Part 1** is the normal path: build the CLI from this checkout,
initialize a disposable repository, and close one real task through the receipt gate —
including watching it refuse a red close. **Part 2** is the reference for everything the
normal path steps around: deliberate activation, linked worktrees, existing-hook conflicts,
exit codes, what `doctor` proves, the installer's own admission, and the coverage boundary.

It uses a wheel built from the checkout. It does not claim that an Omama package is
publicly released. Never experiment in the Omama source checkout; use the disposable
repository below first.

Two shells are used. **POSIX shell** blocks run on Linux, macOS, and Git Bash on Windows
(Git Bash ships with Git for Windows and is the shell Claude Code itself uses for hooks on
Windows). **PowerShell** blocks are given where the spelling differs. One step — running
the gate by hand — is POSIX-shell only; the reason is stated there.

> **What this page was tested on.** Every command in Part 1 was executed, in the order
> shown, on Windows 11 with Git 2.41, uv 0.9.10, Claude Code 2.1.269, and Python 3.8, 3.10
> and 3.12 installed; POSIX blocks ran in Git Bash, PowerShell blocks in PowerShell 5.1.
> The dispatch in step 6 was a real, authenticated Claude Code print-mode session on that
> machine. `init`, `doctor` and the gate are also exercised on Linux and macOS by the
> repository's CI, but this page's POSIX blocks were not separately re-run there. Output
> excerpts are real; machine-specific fields are replaced by `<...>` placeholders.

---

## Part 1 — the normal path

### 0. What you need

| Need | Why | How to check |
|---|---|---|
| Git 2.x, with a commit identity | Every step is a Git repository; the gate hashes trees; the walkthrough commits | `git --version`, `git config user.email` prints something |
| An existing Python 3.8 or newer, below 4 | The CLI runs on it; `init` also finds an installed base Python on its own | `python3 --version` (POSIX) / `py -0p` (Windows) lists at least one |
| `uv` | Builds and installs the wheel; `init` uses it once to create the per-repository receipt runtime | `uv --version` |
| Index access, or a warm `uv` cache | Installing the CLI and provisioning the runtime each resolve PyYAML | — |
| Claude Code | Step 6 dispatches a real session; every other step works without it | `claude --version` |
| Windows only: Git for Windows | Provides Git Bash, the hook shell; without it Claude Code falls back to PowerShell, which the gate's wiring check does not certify | "Git Bash" is in the Start menu after installing Git for Windows |

Nothing below downloads a Python, edits a user or global Python, Claude or Git
configuration, or writes outside the target repository and `uv`'s own tool directory.

### 1. Build and install the CLI (once per machine)

`<OMAMA_SOURCE_CHECKOUT>` is a clone of this repository
(`git clone https://github.com/devanomaly/omama.git`). The other placeholder is deliberate;
replace it with a path on your machine. One command per line: the same quoting works in a
POSIX shell and in PowerShell.

```text
cd "<OMAMA_SOURCE_CHECKOUT>"
uv build --wheel --no-python-downloads --python "<ABSOLUTE_PATH_TO_EXISTING_PYTHON>" --out-dir "dist"
uv tool install "dist/omama-0.1.0-py3-none-any.whl" --python "<ABSOLUTE_PATH_TO_EXISTING_PYTHON>" --no-managed-python --no-python-downloads --no-config
```

`<ABSOLUTE_PATH_TO_EXISTING_PYTHON>` is any installed Python 3.8+ interpreter, for example
the path `py -0p` prints on Windows or `command -v python3` prints on POSIX. The
`--no-managed-python` / `--no-python-downloads` flags keep `uv` from downloading a Python
of its own; `--no-config` makes it ignore any `uv` configuration files on the machine. If
`uv` reports that its executable directory is not on `PATH`, add that directory before
continuing — in Git Bash spell it as a POSIX path (`/c/Users/<you>/.local/bin`, not the
`C:/...` form `uv` prints, which Git Bash does not honor) — then:

```text
omama --version
omama --help
```

Expected: `omama 0.1.0`, and a help text listing exactly two commands, `init` and `doctor`.
These are local-artifact commands, not `uvx` or an index install. Installing the CLI does
not initialize the source checkout and does not authorize package publication. The tool is
per machine; every repository is initialized separately in step 3.

### 2. Create a disposable repository with a real, failing task

The task: `greet("World")` returns `Hello World`; its test expects `Hello, World!`. The test
already exists and already fails, so the card's proof command has something to fail on
before the fix and something to pass after it.

POSIX shell:

```sh
mkdir omama-first && cd omama-first
git init -q -b main
cat > greet.py <<'EOF'
def greet(name):
    return "Hello " + name
EOF
cat > test_greet.py <<'EOF'
import unittest

from greet import greet


class GreetTest(unittest.TestCase):
    def test_greets_by_name(self):
        self.assertEqual(greet("World"), "Hello, World!")


if __name__ == "__main__":
    unittest.main()
EOF
git add . && git commit -qm "greeter: initial code and its test"
python3 -B -m unittest -q test_greet
```

PowerShell:

```powershell
New-Item -ItemType Directory omama-first | Out-Null; Set-Location omama-first
git init -q -b main
Set-Content -LiteralPath greet.py -Encoding ascii -Value @"
def greet(name):
    return "Hello " + name
"@
Set-Content -LiteralPath test_greet.py -Encoding ascii -Value @"
import unittest

from greet import greet


class GreetTest(unittest.TestCase):
    def test_greets_by_name(self):
        self.assertEqual(greet("World"), "Hello, World!")


if __name__ == "__main__":
    unittest.main()
"@
git add .; git commit -qm "greeter: initial code and its test"
py -3 -B -m unittest -q test_greet
```

The last line must fail — that failure is the reproduction the card attaches in step 4. (In
Git Bash on Windows, `python3` is usually the Microsoft Store stub, not a Python; run that
line as `py -3 -B -m unittest -q test_greet` there, as the PowerShell block does.)

```text
AssertionError: 'Hello World' != 'Hello, World!'
...
FAILED (failures=1)
```

`init` requires a non-bare Git worktree with at least one commit, which this now is.

### 3. Initialize the repository, then read `doctor`

`<REPO>` is the absolute path of the directory you just created (`pwd` / `Get-Location`).

```text
omama init "<REPO>"
omama doctor "<REPO>"
```

`init` took about thirty seconds on the tested machine, most of it the admission described
in [R4](#r4-mandatory-admission): before reporting success it proves, in private scratch
copies, that the gate it just installed blocks a red close and verifies a green one. Its
output ends with:

```text
ADMISSION-OK: every mandatory installed command was evaluated and passed
ACTIVATED: repository-local core.hooksPath=.githooks was set after private admission passed
... (the activation-aware doctor report)
DOCTOR-OK: all required dynamic checks evaluated and passed
INSTALLED: doctor and every mandatory installed-command admission check passed
ADOPT STARTER: copy docs/templates/omama/CLAUDE.starter.md to CLAUDE.md, ...
PER-OPERATOR OUTPUT-DISCIPLINE BLOCK (copy deliberately to your global CLAUDE.md; omama did not write global configuration):
> **Output form.** ...
```

Exit 0 is the only success; 1 is a named failure with rollback, 2 is deliberately incomplete
([R2](#r2-read-exits-and-reruns-correctly)). Two `WARNING` rows are normal on a fresh
repository: `environment-boundary` (doctor cannot see user-level or managed Claude settings)
and `token-state` (the literal-tokens file exists and is empty — fill it or disable it later,
see [R3](#r3-what-doctor-actually-checks)).

**What `init` wrote, and where it lives:**

| Per repository — untracked now, meant to be committed and shared | Per machine — ignored, recreated by `init` in every clone or worktree |
|---|---|
| `tools/omama/` — receipt gate, wiring checker, card validator, S3 artifact checker, privacy scanner, license, provenance, manifest | `.omama/runtime/` — a venv holding only PyYAML, created from an installed base Python that `init` found on its own (which one: the `base_interpreter` field of `.omama/state.json`; doctor's `interpreter` row reports the runtime's Python version) |
| `.githooks/pre-commit`, `.githooks/pre-merge-commit` (chainers), `.githooks/privacy-pre-commit` (the unchanged privacy wrapper) | `.omama/state.json` — what was installed, hashes, the recorded interpreter |
| `privacy-deny.json` — team-editable secrets policy | `.claude/settings.local.json` — the Stop hook registration: the runtime interpreter's absolute path plus `"$CLAUDE_PROJECT_DIR/tools/omama/receipt-gate/receipt_gate.py"` |
| `work-order.template.yaml`, `docs/templates/omama/{CLAUDE.starter,PLAN,REVIEW}.md` — inert templates | repository-local Git config `core.hooksPath=.githooks` |
| `.gitignore` — appended with one `# Omama local state and evidence` block naming every path in the right-hand column plus `CARD.yaml`, `CARD.close`, `CARD.review.md`, `CARD.receipt.json`, `*.receipt.json` | `privacy-tokens.txt` — comment-only bootstrap for the literal-tokens layer |

`init` printed instructions to adopt `CLAUDE.starter.md`; it did not create `CLAUDE.md`
and never writes user or global configuration. That adoption is step 8's first item.

`omama doctor` re-reads all of it (a few seconds) and ends with `DOCTOR-OK`.
Dynamic doctor executes the installed gate, validator and checker with synthetic inputs
through the exact registered command, so its `settings-execution` row certifies that the
registered command string answers as the gate. It does **not** prove that a Claude Code
session loads that settings file — step 6 is where that gets exercised for real.

### 4. Write the card, then decide

Copy the template and fill it in. POSIX: `cp work-order.template.yaml CARD.yaml`;
PowerShell: `Copy-Item -LiteralPath work-order.template.yaml -Destination CARD.yaml`. The
template's comments explain every field; the filled-in card for this task is:

```yaml
goal: greet("World") returns "Hello, World!" (comma and exclamation mark), as test_greet.py already expects.
non_goals:
  - editing test_greet.py
  - adding any other file or function
tier: S1
task_type: bugfix
done_when:
  - test_greet.py passes
verify: python3 -B -m unittest -q test_greet
repro:
  - "python3 -B -m unittest -q test_greet fails with AssertionError: 'Hello World' != 'Hello, World!'"
```

**On Windows the gate runs `verify` through `cmd.exe`**, not through your shell — spell the
launcher the way `cmd.exe` finds it, normally `py -3 -B -m unittest -q test_greet`, in both
`verify` and `repro` (that is the spelling the tested run used). On every platform, run the
`verify` line yourself in that shell first: it must fail now, for the reason `repro` records.

**Why this `verify` and not another.** It is the one command whose exit status *is* the
done-when: it fails on the current tree for exactly the goal's reason and can only pass once
the goal is met — or once the test is changed, which `non_goals` forbids and nothing
mechanical prevents. Compare `verify: echo done` — the validator rejects it by name, because a
command that cannot fail proves nothing. Compare also `verify: python3 -c "pass"`: the
validator *accepts* it (it is a real command), and the gate would close it `VERIFIED`,
because re-running a command that always exits 0 produces a genuine green. Nothing
mechanical distinguishes an irrelevant proof from a relevant one; that is the human read
below, and it is the reason the receipt is evidence about the command, not about the goal.

**Validate the form.** The validator needs PyYAML, which `init` installed only into the
receipt runtime, so call that interpreter — the same absolute path recorded in
`.claude/settings.local.json`, which is `.omama/runtime/bin/python` on POSIX and
`.omama/runtime/Scripts/python.exe` on Windows:

```sh
.omama/runtime/bin/python -B tools/omama/work-order/validate_work_order.py CARD.yaml
```

```powershell
& ".omama/runtime/Scripts/python.exe" -B "tools/omama/work-order/validate_work_order.py" "CARD.yaml"
```

Expected: `OK: CARD.yaml is a valid card`, exit 0. To see the deny-list work, change `verify`
to `echo done` and rerun:

```text
VIOLATION: verify='echo done' is vacuous (deny-list: true, :, echo ...): segment 'echo done' begins with 'echo' -- a command that cannot fail proves nothing
```

Remove the `repro` block instead and the validator refuses the bugfix without a
reproduction. Restore the card before continuing.

**The human decisions, before dispatch — nothing below is checkable by a script:**

1. **Ratify `tier`.** `S1` here: one line, one test, no review artifact required. `S3`
   would additionally require an approved `CARD.review.md` before `VERIFIED`.
2. **Ratify `verify`.** Does its exit status prove `goal`? Here, yes, by construction.
3. **Ratify `repro`.** Is it something you observed? You ran it in step 2.
4. **Read `non_goals`.** Is the diff reviewable against that list? Here the diff may touch
   one function in one file.

If you cannot answer 2 with a yes, the right `task_type` is `ask-first`, not a made-up
command.

### 5. Watch the gate say no (a rehearsal, by hand)

Before spending an agent session, see what a red close looks like. Declare the close now,
with the bug still in place, and run the installed gate exactly as a Stop event would reach
it — a JSON object on stdin, from the repository root:

```sh
printf 'CLOSE\n' > CARD.close
echo '{}' | .omama/runtime/bin/python tools/omama/receipt-gate/receipt_gate.py
```

On Windows, run this block in **Git Bash** with `.omama/runtime/Scripts/python.exe` as the
interpreter. It is deliberately not given for PowerShell: on the tested machine PowerShell
5.1 prepended a byte-order mark to the piped text and the gate answered `BLOCK[BAD-INPUT]`,
which is the gate refusing input it cannot parse, not a wiring problem.

The gate re-runs `verify`, sees it fail, and blocks (exit 2):

```text
RECEIPT-GATE BLOCK[VERIFY-RED]: verify exited 1 on the current tree.
--- verify output tail ---
======================================================================
FAIL: test_greets_by_name (test_greet.GreetTest.test_greets_by_name)
...
AssertionError: 'Hello World' != 'Hello, World!'
...
FAILED (failures=1)
fix and re-close, or declare an honest FAILED in CARD.close ("FAILED: <reason>")
```

Look at the directory: `CARD.close` is still there and **no** `CARD.receipt.json` was
written. A blocked close leaves nothing to mistake for evidence. In a real session this
text is what Claude Code feeds back to the agent, whose two honest options are the ones the
last line names.

This runs the gate script directly, which is enough to see its answer; it does not exercise
the Stop wiring itself (doctor's `settings-execution` row did that, and step 6 does it
through the host). Now undo the declared close so the dispatch starts from a clean state:
`rm CARD.close` (PowerShell: `Remove-Item CARD.close`).

### 6. Dispatch Claude Code

From the repository root, either open an interactive session with `claude` and paste this
instruction, or run it non-interactively as the tested walkthrough did:

```text
claude -p "Implement CARD.yaml at the repository root. When its ratified work is complete, write CLOSE to CARD.close and stop." --allowedTools "Read,Edit,Write,Bash" --max-turns 12
```

`--allowedTools` pre-approves those tools for the print-mode session — acceptable in a
disposable repository, your call elsewhere. The instruction carries the close rule
explicitly because this repository has no `CLAUDE.md` yet; step 8 makes it permanent.

What happens, in order: the agent reads the card, edits `greet.py`, runs the test, writes
`CLOSE` to `CARD.close` and stops. Claude Code fires the Stop hook from
`.claude/settings.local.json`; the gate finds the card in the session's working directory,
re-runs `verify`, hashes the tree before and after, writes the receipt and consumes
`CARD.close`. The tested session finished in under a minute and printed its own summary
ending in *CARD.close now contains CLOSE* — **that sentence is the agent's claim, not the
evidence**. The evidence is on disk:

```text
ls CARD.*            # PowerShell: Get-ChildItem CARD.*
CARD.receipt.json
CARD.yaml
```

`CARD.close` is gone and a receipt exists. Two things to know about the host:

- Claude Code shows Stop-hook output in the transcript **only when the hook blocks**. A
  release prints nothing; the consumed `CARD.close` and the written receipt are the visible
  record.
- If the agent closes red, it sees the block text from step 5 and can fix and re-close, or
  close honestly. Claude Code caps consecutive Stop-hook blocks and then ends the turn;
  observed on a real host as nine, tracked in
  [issue #50](https://github.com/devanomaly/omama/issues/50). The outcome is conservative —
  no receipt, claim unverified — but the block is bounded by the host, not unlimited.

No Claude Code at hand? Fix the one line in `greet.py` yourself, declare `CLOSE` again, and
rerun the step-5 command: it answers `VERIFIED: verify green and fresh on <rev> -- receipt
written, CARD.close consumed.` and writes the same receipt. That proves the gate, not the
host wiring.

### 7. Read the receipt

```text
cat CARD.receipt.json    # PowerShell: Get-Content -LiteralPath CARD.receipt.json
```

The tested run produced (hashes abbreviated):

```json
{
 "command": "py -3 -B -m unittest -q test_greet",
 "exit": 0,
 "verdict": "VERIFIED",
 "rev": "7e1a581c8a059dec3b4529cdd9fb841bef08b035",
 "patch_id": "7f50aeb4…",
 "diff_sha": "f104accf…",
 "diff_hash": "f6d0de5e…",
 "timestamp": "2026-09-11T23:39:10.745772+00:00"
}
```

| Field | Meaning | How to check it |
|---|---|---|
| `command`, `exit` | The card's `verify` as it stood at close, and the exit status the gate observed | Run it yourself; a `VERIFIED` receipt always has `exit: 0` |
| `verdict` | `VERIFIED` only from a green re-run; `FAILED` / `UNVERIFIED` from an honest close (then `reason` is present) | — |
| `rev` | `HEAD` when the proof ran | `git rev-parse HEAD` — equal here, because the agent did not commit |
| `patch_id` | `git patch-id --stable` of the uncommitted diff against `HEAD` at close; `empty-diff` on a clean tree | `git diff HEAD \| git patch-id --stable` while the diff is unchanged |
| `diff_sha` | SHA-256 of the pinned `git diff HEAD` bytes | Recomputable on this checkout while the tree stands |
| `diff_hash` | SHA-256 of the whole hash material after `verify` — diff, untracked names, reflog, stash, index flags, the card family | The gate recomputes it on the next close; a mismatch between before and after is `UNEXPECTED-CHANGE` |
| `timestamp` | UTC | — |

A `VERIFIED` receipt always carries non-null `rev`, `patch_id` and `diff_sha`; one with a null
hash is forged on its face. Never create or edit the receipt yourself; the gate deletes a
receipt it finds at the start of every close attempt.

Commit the fix now (`git add greet.py && git commit -m "greet: add comma and exclamation
mark"`) — your first commit through the installed privacy hook, which prints a `notice`
about the empty tokens file and lets a clean commit through. Then rerun the step-5 command
with no `CARD.close` present: the gate answers a WIP line that ends in
`receipt: VERIFIED @ 7e1a581c… …, tree has moved since`. The receipt still names the tree it
verified; the tree is now a different one. That is the binding doing its job.

An honest close is one line: `FAILED: <reason>` or `UNVERIFIED: <reason>` in `CARD.close`.
The gate still re-runs `verify`, records its exit, writes a receipt with that verdict and
the reason, consumes the token and exits 0 — a trail, never a `VERIFIED`.

**What this receipt proves:** on commit `7e1a581…` with that diff applied, the ratified
command exited 0, at that time, unforged through the close path. **What it does not
prove:** that the command was the right proof (you ratified that in step 4), that the diff
is otherwise good (read it), or that the test could not have been weakened first
(`non_goals` says not to; the optional [protect-tests](protect-tests/README.md) guard
watches for it; the receipt does not). The residual list of the gate is in
[receipt-gate/README.md](receipt-gate/README.md#what-it-does-not-catch-honest-named-boundaries).

### 8. What to do next

1. **Make the close rule permanent.** Copy `docs/templates/omama/CLAUDE.starter.md` to
   `CLAUDE.md`, drop its header comment, resolve every `<ADJUST: ...>` (remove the hooks
   this repository did not install — protect-tests is not in the bundle), and check the
   copy with `starter-claude-md/check_starter.py` from the Omama checkout — the checker is
   not part of the installed payload. Details: [starter adoption](starter-claude-md/ADOPTION.md).
   After that, a dispatch no longer needs the explicit close instruction.
2. **Initialize a real repository the same way.** `init` refuses to displace hooks that are
   already active and never rewrites shared worktree config; [R1](#r1-deliberate-git-config-activation-worktrees-and-existing-hooks)
   covers those cases and `--no-git-config`. Then edit `privacy-deny.json` and fill or
   disable `privacy-tokens.txt`.
3. **Every clone and every linked worktree runs `omama init` for itself.** The runtime,
   the Stop wiring and `core.hooksPath` are per machine and do not travel with a clone;
   `doctor` names what is missing.
4. **Carry the evidence into review.** Paste `command`, `exit` and `rev` into the PR body.
   The receipt file stays local by policy ([why](work-order/ADOPTION.md#the-card-and-its-receipt-stay-local)).
5. **Read what you are and are not getting.** Each piece's README ends with "What it does
   NOT catch"; [R5](#r5-coverage-and-what-it-does-not-catch) below is the installer's own
   boundary.

---

## Part 2 — reference

### R1. Deliberate Git-config activation, worktrees, and existing hooks

To prepare files without changing local Git config:

```text
omama init "<TARGET_REPOSITORY>" --no-git-config
```

When activation is needed, this is intentionally incomplete (exit 2). Omama prints an
exact command shaped like:

```text
git -C "<TARGET_REPOSITORY>" config --local core.hooksPath .githooks
```

Run the printed command exactly, then rerun the same `omama init ... --no-git-config`.
Once `.githooks` is already effective, the rerun performs full admission and can exit 0.

For a linked worktree whose shared configuration is not already correct, init refuses to
change it. Run the exact remedy it prints against the **main checkout** first:

```text
git -C "<MAIN_CHECKOUT>" config --local core.hooksPath .githooks
omama init "<LINKED_WORKTREE>"
```

Omama never enables Git's worktree-config extension or silently changes shared config.
If `git init --separate-git-dir` placed this worktree's activation config outside the
worktree, init refuses before publication; phase 1 does not activate that layout.
If a custom hooksPath is effective, or any active hook anywhere in the directory that
would be displaced exists—even only `pre-push`—init refuses. Integrate those hooks manually;
whole-directory displacement is not treated as safe because the new files would coexist.

If your team already owns a durable Python/PyYAML environment, select it instead of the
managed runtime:

```text
omama init "<TARGET_REPOSITORY>" --python "<ABSOLUTE_PATH_TO_QUALIFIED_PYTHON>"
```

That interpreter must report Python 3.8+ (below 4) and import the constrained PyYAML.
Omama probes it with bytecode writes disabled and does not install into or otherwise modify
it. The recorded receipt interpreter is separate from the privacy wrapper, which retains
its upstream PATH selection (`py -3`, then `python3`, then `python`). Doctor qualifies both.

On the default route, `init` independently finds an already installed supported base
Python, creates `<TARGET_REPOSITORY>/.omama/runtime`, and uses installation-time `uv` to
install only `PyYAML>=6.0.2,<7` there. Managed-Python downloads and global configuration
discovery are disabled. Init never downloads Python, installs the CLI in that runtime, or
changes a user or global Python, Claude, or Git configuration.

A successful init installs the complete 15-file payload and records source URL/revision,
package version, license, bundle identity, and per-file hashes. It also:

- merges one owned Stop registration into ignored `.claude/settings.local.json`, using a
  quoted forward-slash absolute interpreter path and
  `"$CLAUDE_PROJECT_DIR/tools/omama/receipt-gate/receipt_gate.py"`;
- installs the receipt gate, wiring checker, work-order validator, S3 checker, privacy
  scanner, unchanged privacy wrapper, and both Git chainers;
- bootstraps team-editable deny policy, conditional comment-only tokens, work-order and
  inert starter/PLAN/REVIEW templates, while preserving existing team content;
- appends required local/evidence paths to `.gitignore` only when Git confirms the result
  is effective; and
- runs every non-activation doctor inventory check and the complete mandatory admission
  from installed bytes **privately first**, then activates local
  `core.hooksPath=.githooks`, then runs the complete activation-aware doctor before
  recording complete state. A failing install never leaves hooks live.

### R2. Read exits and reruns correctly

Both commands are tri-state:

| Exit | `init` | `doctor` |
|---|---|---|
| 0 | Every mandatory dynamic check and installed-hook admission passed; state is complete. | Every required dynamic row ran and passed. |
| 1 | Named violation, conflict, unsafe target, runtime failure, or failed/unevaluable mandatory admission. Rollback/recovery status is explicit. | At least one named violation; this dominates incomplete rows. |
| 2 | Deliberate prepared state or another required capability was not evaluated; never success. | No known violation, but required coverage is incomplete, including `--static-only`. |

Same-bundle reruns repair only eligible missing immutable/generated material. Existing
editable bootstrap files are team-owned after creation; edits and deliberate deletion of
inert templates survive. Immutable drift, generated wiring conflict, and a different bundle
are named conflicts, not an implicit update. Existing card/close/receipt/index state, tokens,
deny policy, unrelated settings/hooks, and external edits are protected.

Writes use one target lock, a finite owned-write journal, per-file replacement, and
conditional rollback. If another writer changes a path after Omama wrote it, Omama preserves
that external edit and leaves a named recovery-required state instead of restoring stale
bytes. This is bounded recovery for the documented file set under a quiescent target, not
all-files atomicity, stale-lock theft, or a general transaction service.

If init leaves `recovery-required` or reports `unfinished-install`, do not delete `.omama`,
its runtime, lock, or journal wholesale. Follow the preservation-first
[finite manual recovery procedure](cli/RECOVERY.md), retain its before-images and external
edits, and retry only after every recorded owned entry is accounted for.

### R3. What doctor actually checks

Default doctor is read-only with respect to target files, card family, index, and config,
but it executes only the expected installed artifacts after checking their identity. It
reports:

- installation state, lock/journal ownership, manifest/provenance, bundle/version skew,
  immutable/generated hashes, and editable team drift;
- both project settings files, the one eligible managed Stop command, disabled/async or
  conflicting registrations, certified quoting, and visible project/process environment
  overrides;
- receipt interpreter/PyYAML, gate response, validator valid/invalid probes, and S3 checker
  valid/malformed probes including `--budgets-advisory`;
- effective hooksPath, both chainers, wrapper/scanner identity and execution mode, privacy
  config, wrapper-selected interpreter, and token state; and
- clone/worktree/relocation mismatches and missing local runtime/settings.

Doctor does not print token values. A configured missing tokens file is a violation with
path and remedy. An existing empty/comment-only configured file produces one nonblocking
notice per scanner run: the literal layer is inactive, so fill it or explicitly use null.
`tokens_file: null` and an omitted key deliberately disable that layer without the notice.
A populated file proves only that literals exist, not that the team chose a complete list.

`omama doctor "<TARGET_REPOSITORY>" --static-only` executes none of the installed interpreter,
gate, validator, checker, scanner, or wrapper. It still checks paths, forms, bytes, settings,
and state, names every skipped dynamic row, and normally returns incomplete/2. Use it when
executing repository-controlled settings is inappropriate; do not call it a health proof.

Doctor can observe project `settings.json`, project `settings.local.json`, and its process
environment. User settings, managed policy, and a separate `claude --settings` source are
not fully observable. Dynamic doctor therefore certifies its modeled command, not the exact
settings merge a real Claude session will load.

### R4. Mandatory admission

Before init reports success, it runs the full dynamic doctor under its private transaction
owner and then tests the target-installed commands in synthetic Git repositories. It proves:

- S1 reaches real `VERIFY-RED`/2 and then `VERIFIED`/0 with close consumption and
  recomputable commit/diff binding;
- S3 reaches the installed checker with a present PASS review missing Non-findings, blocks
  as `S3-REVIEW`/2, then closes a valid review; over-budget-only is advisory;
- both privacy entrypoints block a planted synthetic literal and allow clean commit/merge;
- configured missing, empty/comment-only, populated, null, and omitted token states retain
  their distinct behavior;
- removing the scratch-installed gate, validator, checker, scanner, or wrapper fails by
  name even while healthy package/source copies exist elsewhere; and
- all files actually installed are committed together through the shipped wrapper and
  current policy. A fresh installation admits the complete 15-file payload in one commit.

Only `CLAUDE_PROJECT_DIR` changes for those scratch worktrees; there are no generated
`OMAMA_*` dependency overrides or source-tree fallback. Synthetic payloads are used, never
the adopter's token bytes.

Init's admission used synthetic cards and literals to prove the installed mechanisms. It
did not create or close your first real task; Part 1 does. See
[work-order adoption](work-order/ADOPTION.md) for human ratification and
[the receipt close model](receipt-gate/README.md#close-model-the-gate-locks-the-claim-not-the-session)
for every supported close value and receipt semantics.

### R5. Coverage and what it does not catch

The repository's release check is the full command, without `--fast`:

```sh
python3 verify_all.py # Windows: py -3 verify_all.py
```

Exit 0 requires every counted fixture—including built-wheel CLI integration—to run and pass.
The individual validator, receipt, privacy, and artifact fixtures predate this CLI; their
standalone coverage is not evidence that install/init/doctor integration passed.

*Historical record, not a current count:* for the frozen CLI source at
`efa675869f42ebcd8d9204dcfbc0f5b34c3babe7`, the full runner passed all four matrix jobs:
Ubuntu/Python 3.8, Ubuntu/Python 3.11, macOS/Python 3.11, and Windows/Python 3.11, each
with nine top-level entries and `9 ok, 0 failed, 0 not-run`. The counted CLI entry
contained six suites and 74 tests at that revision (including nine runtime tests); the CI
parent summary reports the entry, not a separate log or hash for every child suite.

| Claim | Evidence boundary |
|---|---|
| Bundle/build identity and exact installed S1/S3/privacy admission | Measured on built local artifacts in disposable repositories. |
| Supported platform and Python matrix | The exact-revision full runner passed Ubuntu 3.8/3.11, macOS 3.11, and Windows 3.11; this does not extend support beyond the named jobs. |
| Claude settings loading | Deterministic shell admission does not prove a real Claude host loaded the project settings. A separate host session is required; Part 1 step 6 is one such session, on Windows. |
| Crash/concurrency safety | Finite conditional rollback is not whole-repository or all-files atomicity; hostile writers and power loss remain outside the promise. |
| Detection efficacy | No efficacy or reduction claim is made before pilot evidence. |

Removal or relocation of the selected base Python, the repository, or `.omama/runtime` can
break future receipt execution; doctor detects these lifecycle failures but cannot make the
interpreter permanent. Local Git config and ignored machine state do not travel with a clone.
The privacy hook also retains its documented bypasses (`--no-verify`, cherry-pick/am/rebase,
history, and generic high-entropy secrets); see [privacy-hook/README.md](privacy-hook/README.md).

For manual installation, provenance, and formatter/linter exclusions, use
[VENDORING.md](VENDORING.md) and each piece's `ADOPTION.md`. Formatter configuration is never
rewritten automatically.
