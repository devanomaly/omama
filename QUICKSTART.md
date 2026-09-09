# Quickstart — install and inspect the phase-1 bundle

This page uses a wheel built from the checkout. It does not claim that an Omama package is
publicly released. Start with a clean, non-bare Git worktree that already has at least one
commit. Never experiment in the Omama source checkout; use a disposable repository first.

*[Versão em português](QUICKSTART.pt-BR.md)*

## 1. Build and install the local wheel

Prerequisites: Git, `uv`, and a user-selected existing Python 3.8+ (below Python 4). The
path placeholders below are deliberate; replace them with paths on your machine.

The commands below are deliberately one command per line: the same quoting works in a POSIX
shell and in PowerShell, with no cross-shell continuation syntax.

```text
cd "<OMAMA_SOURCE_CHECKOUT>"
uv build --wheel --sdist --no-python-downloads --python "<ABSOLUTE_PATH_TO_EXISTING_PYTHON>" --out-dir "dist"
uv tool install "dist/omama-0.1.0-py3-none-any.whl" --python "<ABSOLUTE_PATH_TO_EXISTING_PYTHON>" --no-managed-python --no-python-downloads --no-config
```

If uv reports that its executable directory is not on `PATH`, follow the temporary
shell command it prints before continuing:

```text
omama --version
omama --help
```

These are local-artifact commands, not `uvx` or an index install. Installing the CLI does
not initialize the source checkout and does not authorize package publication.

## 2. Initialize one repository

The default route creates a durable receipt runtime inside the target:

```text
omama init "<TARGET_REPOSITORY>"
omama doctor "<TARGET_REPOSITORY>"
```

Default `init` independently finds an already installed supported base Python, creates
`<TARGET_REPOSITORY>/.omama/runtime`, and uses installation-time `uv` to install only
`PyYAML>=6.0.2,<7` there. Managed-Python downloads and global configuration discovery are
disabled. Init never downloads Python, installs the CLI in that runtime, or changes a user
or global Python, Claude, or Git configuration.

If your team already owns a durable Python/PyYAML environment, select it explicitly:

```text
omama init "<TARGET_REPOSITORY>" --python "<ABSOLUTE_PATH_TO_QUALIFIED_PYTHON>"
```

That interpreter must report Python 3.8+ (below 4) and import the constrained PyYAML.
Omama probes it with bytecode writes disabled and does not install into or otherwise modify
it. The recorded receipt interpreter is separate from the privacy wrapper, which retains
its upstream PATH selection (`py -3`, then `python3`, then `python`). Doctor qualifies both.

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
- activates local `core.hooksPath=.githooks` last, then runs doctor and mandatory admission
  from installed bytes before recording complete state.

Init prints the starter adoption instructions and the output-discipline per-operator block;
it does not create `CLAUDE.md` or write that block into user configuration.

## 3. Deliberate Git-config activation

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

## 4. Read exits and reruns correctly

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

## 5. What doctor actually checks

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

## 6. Mandatory admission

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

## 7. Run a real task and inspect its receipt

Init's admission used synthetic cards and literals to prove the installed mechanisms. It
did not create or close your first real task. From the initialized repository root:

1. Copy `work-order.template.yaml` to `CARD.yaml`. On a POSIX shell use
   `cp "work-order.template.yaml" "CARD.yaml"`; in PowerShell use
   `Copy-Item -LiteralPath "work-order.template.yaml" -Destination "CARD.yaml"`.
2. Fill the real goal, non-goals, done-when, task type, and one relevant, non-vacuous
   `verify`. The agent may propose the tier, but a human ratifies it and owns confirmation
   of `verify`; for a bugfix, the human also supplies or confirms `repro`. Do not invent a
   command or reproduction merely to fill the schema.
3. A human runs the validator before dispatch, using the exact absolute receipt interpreter
   that init wrote first in `.claude/settings.local.json`.

   POSIX shell:

   ```sh
   "<ABSOLUTE_RECEIPT_PYTHON_FROM_SETTINGS_LOCAL>" -B "tools/omama/work-order/validate_work_order.py" "CARD.yaml"
   ```

   PowerShell (where a quoted executable needs the call operator):

   ```powershell
   & "<ABSOLUTE_RECEIPT_PYTHON_FROM_SETTINGS_LOCAL>" -B "tools/omama/work-order/validate_work_order.py" "CARD.yaml"
   ```

   Dispatch only after it reports `OK`.
4. Either adopt the close rule from `docs/templates/omama/CLAUDE.starter.md` into the
   repository's `CLAUDE.md`, following [starter adoption](starter-claude-md/ADOPTION.md),
   or carry the rule explicitly in this dispatch:

   ```text
   Implement CARD.yaml at the repository root. When its ratified work is complete, write CLOSE to CARD.close and stop.
   ```

The Stop hook treats no `CARD.close` as WIP. On a deliberate close it re-runs the card's
own proof; a red close is blocked and must be corrected before another deliberate close.
After a permitted close, confirm that `CARD.close` was consumed and inspect
`CARD.receipt.json` (`cat "CARD.receipt.json"` in a POSIX shell or
`Get-Content -LiteralPath "CARD.receipt.json"` in PowerShell). Do not create or edit the
receipt yourself. See [work-order adoption](work-order/ADOPTION.md) for human ratification
and [the receipt close model](receipt-gate/README.md#close-model-the-gate-locks-the-claim-not-the-session)
for every supported close value and receipt semantics.

## 8. Coverage and what it does not catch

The repository's release check is the full command, without `--fast`:

```sh
python3 verify_all.py # Windows: py -3 verify_all.py
```

Exit 0 requires every counted fixture—including built-wheel CLI integration—to run and pass.
The individual validator, receipt, privacy, and artifact fixtures predate this CLI; their
standalone coverage is not evidence that install/init/doctor integration passed.

For the frozen CLI source at `efa675869f42ebcd8d9204dcfbc0f5b34c3babe7`, the full
runner passed all four matrix jobs: Ubuntu/Python 3.8, Ubuntu/Python 3.11,
macOS/Python 3.11, and Windows/Python 3.11, each with nine top-level entries and
`9 ok, 0 failed, 0 not-run`. The counted CLI entry contains six suites and 74 tests at
that revision (including nine runtime tests); the CI parent summary reports the entry,
not a separate log or hash for every child suite.

| Claim | Evidence boundary |
|---|---|
| Bundle/build identity and exact installed S1/S3/privacy admission | Measured on built local artifacts in disposable repositories. |
| Supported platform and Python matrix | The exact-revision full runner passed Ubuntu 3.8/3.11, macOS 3.11, and Windows 3.11; this does not extend support beyond the named jobs. |
| Claude settings loading | Deterministic shell admission does not prove a real Claude host loaded the project settings. A separate host session is required. |
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
