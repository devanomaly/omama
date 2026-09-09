# Omama CLI packaging surface

The package exposes `omama init [PATH] [--python ABSOLUTE_PATH] [--no-git-config]`
and `omama doctor [PATH] [--static-only]`, plus help and version. The T5 installer
foundation resolves only non-bare Git worktrees, rejects inherited Git routing and
unsafe destinations before publication, and provides finite lock/journal/conditional
rollback mechanics. A normally activated init returns 0 only after private-owner doctor
and mandatory exact-installed-command admission both pass; it otherwise reports a named
failure and conditionally rolls back. Deliberate `--no-git-config` preparation remains
the distinct incomplete/2 route while activation is still required.

Builds generate the packaged payload from the authoritative repository files listed in
`build_backend/inventory.py`. `omama_cli.bundle.load_bundle()` reads only installed
package resources and verifies every recorded SHA-256 before exposing bytes. The manifest
distinguishes immutable vendored files, editable bootstrap material, generated wiring,
and later local state. `omama_cli.identity` supplies read-only conservative classifications;
it performs no installer writes.

Publication uses one target-owned lock with no stale-lock theft, records each finite
before-image before the first asset write, uses individual same-directory replacements,
and conditionally restores only bytes still written by that attempt. An intervening edit
is preserved and leaves a named recovery-required journal. Re-init refuses another
recorded bundle, repairs missing same-bundle immutable material, and preserves adopted
editable bootstrap files (including deliberate deletion). Active closes, tracked local
state, immutable/generated drift, read-only paths, path escapes and symlink/junction
traversal are named preflight failures. The operational boundary remains a quiescent
target: an uncooperative writer can still win the final check-to-replace race, so this is
not an all-files atomicity claim or a generic transaction service.

Python 3.8+ and `PyYAML>=6.0.2,<7` are the runtime contract. The build-only backend is
constrained to `setuptools>=68,<76`. Local Python 3.11 execution remains a CI requirement;
this development host has no Python 3.11 interpreter.

The default receipt runtime is `.omama/runtime`, created from an existing independently
probed system Python. Installation-time `uv` discovery and provisioning explicitly disable
managed-Python downloads and config/project discovery, target the selected interpreter,
use copy mode, and keep cache/temp beneath `.omama/cache`. Only constrained PyYAML is
installed; the Omama CLI is rejected from the receipt runtime. The effective base,
interpreter, Python version and resolved PyYAML version are recorded in local state.

`--python ABSOLUTE_PATH` is a separate, read-only route. It requires Python >=3.8,<4 and
existing PyYAML >=6.0.2,<7, probes with `-B`/`PYTHONDONTWRITEBYTECODE`, and never calls uv
against the supplied environment. The privacy wrapper remains byte-identical and continues
to select `py -3`, `python3`, or `python` through PATH independently. Removing the selected
base Python, moving the repository, or deleting its managed runtime can still break the
gate; doctor reports those lifecycle failures rather than promising interpreter lifetime.

T7 writes machine-specific Stop wiring only to ignored
`.claude/settings.local.json`. It preserves unrelated JSON and sibling hooks, registers one
synchronous command containing the quoted forward-slash absolute interpreter plus
`"$CLAUDE_PROJECT_DIR/tools/omama/receipt-gate/receipt_gate.py"`, and generates no OMAMA
environment overrides. Malformed/disabled/async/duplicate/conflicting gate settings in
either project file are preflight failures.

The two LF chainers and byte-identical privacy wrapper live under `.githooks`; the scanner
remains under `tools/omama`. Existing team `privacy-deny.json` and token bytes are preserved.
For the shipped `privacy-tokens.txt` reference, a missing file is bootstrapped comment-only
on first install, ignored, and never printed. Null/omitted `tokens_file` stays deliberately
disabled. Required local/evidence paths are appended once to `.gitignore` and verified with
Git's effective ignore behavior before activation.

Before changing `core.hooksPath`, init resolves the effective value including repository
includes and enumerates the complete currently effective hook directory. A custom value or
any active default hook (including pre-push/post-checkout) is a preflight conflict. Main
checkout activation is local and last; linked worktrees may reuse an already-effective
`.githooks` value but never rewrite shared config or enable worktree-config extensions.
`--no-git-config` leaves prepared state, returns 2, and prints the exact local command.
If `.githooks` is already the effective value, the same flag performs normal admission and
may return 0. A first init and same-bundle prepared/complete reruns all use the live private
transaction owner; only an all-green run promotes local state from `installing` to `complete`.

`omama doctor` inventories both project settings files, the exact managed command and
visible project/process environment sources; it explicitly warns that user, managed-policy,
and CLI-session settings are not all observable. It compares the installed manifest/state
and every immutable/generated byte while reporting editable team drift separately. Local
provenance is traceability, not cryptographic authenticity, and a different running CLI
bundle is reported as version skew rather than silently applied or called corruption.

Default doctor dynamically qualifies the recorded Python/PyYAML, invokes the certified
installed wiring parser against only the identified managed gate, and performs real
valid/invalid validator plus valid/malformed `--budgets-advisory` S3-checker probes in
temporary synthetic files. Gate-like and ordinary sibling registrations are inspected but
never executed. It also checks effective hooksPath, both chainers, wrapper/scanner identity,
LF/executable behavior, privacy config/token state, and the wrapper-selected Python route.
No token values are printed.

Mandatory admission first requires the full dynamic doctor report under the current private
transaction owner. Doctor's temporary validator/checker/privacy probes are placed beneath the
owner's target-local `.omama/.admission-*` scratch for this internal call; standalone doctor
continues to use external temporary probes and treats every lock/journal as unhealthy.

The admission harness then copies the validated, currently installed manifest topology and
local settings into private target-owned scratch Git repositories. It executes the recorded
settings command unchanged, with only `CLAUDE_PROJECT_DIR` pointing at each synthetic
worktree and with zero `OMAMA_*` overrides. A valid S1 card proves real VERIFY-RED/2 then
VERIFIED/0, close consumption, and recomputable HEAD/diff binding. S3 proves a present PASS
review genuinely missing Non-findings reaches the installed checker, a valid review closes,
and an over-budget-only review warns under `--budgets-advisory`. The malformed review contains
neither a Non-findings heading nor that phrase in prose; the earlier false-red construction
that mentioned Non-findings outside a section remains a warning, not red evidence.

Independent omission challenges remove the scratch-installed gate, validator, checker,
scanner, or wrapper while healthy package/source copies remain elsewhere; no omitted file is
reconstructed. Privacy challenges exercise the unchanged wrapper through both shipped
chainers, including real Git commit and merge behavior. Missing, comment-only, populated,
null, and omitted token states use synthetic token input only; adopter token values are never
read or copied. Finally every installed manifest file is committed together through the
shipped wrapper and the target's current privacy configuration. Failure or unavailable shell
coverage is named and prevents complete state; NOT-RUN is translated to init exit 1.
On a same-bundle rerun, deliberately absent inert editable templates stay absent: admission
reports them and commits every file that is actually installed, without reconstructing package
copies. Fresh installation still proves the complete 15-file payload in one commit; executable
gate/validator/checker/privacy dependencies are never waived by this editable-material rule.

Successful init prints inert starter-template adoption guidance and the output-discipline
per-operator block. It never creates `CLAUDE.md` or writes user/global Claude configuration.
These deterministic shell tests prove the installed commands and Git entrypoints, not that a
real Claude host loaded project settings; paid/login-dependent host sessions remain separate.

`--static-only` executes no installed interpreter, gate, validator, checker, scanner, or
wrapper. It keeps existence/hash/config inspection, names every skipped dynamic row, and
returns incomplete/2 unless a known violation makes exit 1 dominate. Standalone lock/journal
state is unhealthy; only the private in-process admission context can recognize its exact
owner. Missing clone-local state/runtime, relocation, foreign ownership, dependency drift,
or untrusted overrides get concrete re-init/recovery messages. Doctor creates synthetic
probe files only in temporary space and does not modify the target, card family, index, or
configuration through its own operations.
