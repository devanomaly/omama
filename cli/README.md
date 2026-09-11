# Omama CLI packaging surface

[Português (Brasil)](README.pt-BR.md)

The package exposes `omama init [PATH] [--python ABSOLUTE_PATH] [--no-git-config]`
and `omama doctor [PATH] [--static-only]`, plus help and version. The installer
resolves only non-bare Git worktrees, rejects inherited Git routing and
unsafe destinations before publication, and provides finite lock/journal/conditional
rollback mechanics.

A normally activated init runs in this order: publish the payload, run every
non-activation doctor inventory check and the complete installed
adopter-specific admission privately, and only then set repository-local
`core.hooksPath=.githooks` and run the complete activation-aware doctor. It
returns 0 only after that final check passes, so a failing installation never
leaves hooks live in the repository while its own state is still incomplete. It
otherwise reports a named failure and conditionally rolls back, activation
included. Deliberate `--no-git-config` preparation remains the distinct
incomplete/2 route while activation is still required.

Exit codes are exact: `0` means every required selected check ran and passed;
`1` means a named observed failure; `2` means deliberately incomplete or
NOT-RUN coverage. No success language accompanies `1` or `2`.

Builds generate the packaged payload from the authoritative repository files listed in
`build_backend/inventory.py`. `omama_cli.bundle.load_bundle()` reads only installed
package resources and verifies every recorded SHA-256 before exposing bytes. The manifest
distinguishes immutable vendored files, editable bootstrap material, generated wiring,
and later local state. `omama_cli.identity` supplies read-only conservative classifications;
it performs no installer writes.

Publication uses one canonical repository lock in the Git common directory,
shared by every linked worktree of the repository, with no stale-lock theft. It
records each finite before-image before the first asset write, verifies every
durable write by reading it back before recording it as applied, uses individual
same-directory replacements, and conditionally restores only bytes still written
by that attempt. An intervening edit is preserved and leaves a named
recovery-required journal.

`omama init` reconciles an interrupted installation itself when every journal
entry is unambiguous **and no lock is present**. A lock that already exists is
never taken automatically, whatever its schema, recorded owner or apparent age:
whether the process that took it is still running is not something this
installation can establish safely — a PID alone is not identity because PIDs
are reused, and age alone is not identity because a slow install is not a dead
one. Instead, init and recovery both refuse and print one documented step,
identical on every platform: confirm that no `omama` process is running for the
repository, rename the lock aside to
`<git-common-dir>/omama-install.lock.stale-<UTC timestamp>` keeping it as
evidence, and rerun `omama init`.

With no lock present, init classifies every entry, including entries still
marked `applied: false`, against the bytes on disk as `before` (unapplied),
`after` (applied even if the journal had not recorded it yet) or `neither`. If
anything is `neither` it changes nothing at all, preserves the journal and every
byte, and stops with `recovery-ambiguous`. Reconciliation rolls `after` entries
back to their recorded before-images; it does **not** complete the interrupted
installation, so the init run that recovered then installs from the beginning,
and the reconciled journal is kept as
`.omama/install-journal.json.reconciled-<owner>` rather than discarded. Follow
the linked, preservation-first [manual recovery procedure](RECOVERY.md) for the
ambiguous case; never delete `.omama`, its runtime, lock, or journal wholesale. Re-init refuses another
recorded bundle, repairs missing same-bundle immutable material, and preserves adopted
editable bootstrap files (including deliberate deletion). Active closes, tracked local
state, immutable/generated drift, read-only paths, path escapes and symlink/junction
traversal are named preflight failures. The operational boundary remains a quiescent
target: an uncooperative writer can still win the final check-to-replace race, so this is
not an all-files atomicity claim or a generic transaction service.

Python 3.8+ is the runtime contract on both routes. The managed route installs
and requires `PyYAML>=6.0.2,<7`; the read-only `--python` route is qualified by
the capability the installed gate actually needs rather than by that version
floor (see below). The build-only backend is constrained to `setuptools>=68,<76`.

The default receipt runtime is `.omama/runtime`, created from an existing independently
probed system Python. Installation-time `uv` discovery and provisioning explicitly disable
managed-Python downloads and config/project discovery, target the selected interpreter,
use copy mode, and keep cache/temp beneath `.omama/cache`. Every inherited `UV_*`
and `PIP_*` control and every unsafe Python control is removed from the
environment uv runs in, so a caller cannot add unapproved distributions or
redirect the Python selection; `--no-seed` is not credited as enforcement,
because it is inert on the uv versions exercised. The scrubbed environment
carries the guarantee and a post-provision inventory proves it: the owned
runtime must contain the selected PyYAML distribution and nothing else. The
Omama CLI is rejected from the receipt runtime. uv's actionable `error:` lines
are preserved in diagnostics instead of whatever printed last.

An absent owned managed runtime is re-provisioned, so doctor's "rerun init in
this clone/worktree" remedy works. A managed runtime that is present but not
owned by omama, or whose owner marker has drifted, is named and refused without
being deleted or overwritten. The effective base, interpreter, Python version,
resolved PyYAML version and the path the dependency was actually imported from
are recorded in local state.

`--python ABSOLUTE_PATH` is a separate, read-only route. It requires Python
>=3.8,<4 and a PyYAML that actually satisfies the installed gate — qualified by
executing the `safe_load`/`safe_dump` round trip the gate depends on, and
recording which module file was imported — rather than by the universal
`>=6.0.2,<7` floor it never earned. A missing or incapable dependency fails
closed. It probes with `-B`/`PYTHONDONTWRITEBYTECODE`, runs from a neutral
working directory with only the unsafe current-directory entry removed from the
search path, and never calls uv against the supplied environment. That
interpreter's real HOME and user-site selection are deliberately preserved:
rewriting them would qualify a different dependency than the gate will import.
An empty `--python` is a named invalid value, not a silent fall-through to the
managed route. The privacy wrapper remains byte-identical and continues
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
When activation would write a separate Git directory outside the worktree, init refuses
before publication; phase 1 does not activate that unsupported layout.
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

The counted `cli/fixture/run_fixture.py` builds the phase-1 wheel in an explicitly owned
disposable root, asserts that no source distribution was produced, and installs the console
entrypoint from that wheel into a test-owned tool environment outside the delivery checkout. It admits real public
`init`/`doctor` from those installed resources, retains complete child logs, and treats a
missing prerequisite as NOT-RUN rather than success. The fixture also runs the preservation,
conflict, rollback, recovery, linked-worktree, doctor, and installed-admission contract suites
against built package resources. A required unittest skip is a fixture failure.

Its lifetime case installs the built CLI into a separately marked tool environment, performs
a full default managed init, validates that the recorded executable is the repository venv
entrypoint (not merely its canonical base target), removes only that marked tool environment,
and then runs installed S1 and S3 closes plus a privacy commit with package/network access
disabled. The repository runtime and its independently recorded base Python remain. Removing
or relocating that base is deliberately not simulated by deleting a real interpreter: it is
an explicit doctor-detectable prerequisite and relocation limitation.

The full command is `python verify_all.py` without `--fast`, run with the
interpreter the operator selects; it uses that interpreter for its child
fixtures. CI runs the same counted entry on Windows, Linux, and macOS with
Python 3.11 plus Linux with Python 3.8. Platform-specific inability is
reported as NOT-RUN and fails the job; it is never replaced by a static portability claim.

`--static-only` executes no installed interpreter, gate, validator, checker, scanner, or
wrapper. It keeps existence/hash/config inspection, names every skipped dynamic row, and
returns incomplete/2 unless a known violation makes exit 1 dominate. Standalone lock/journal
state is unhealthy; only the private in-process admission context can recognize its exact
owner. Missing clone-local state/runtime, relocation, foreign ownership, dependency drift,
or untrusted overrides get concrete re-init/recovery messages. Doctor creates synthetic
probe files only in temporary space and does not modify the target, card family, index, or
configuration through its own operations.

Phase-1 pilot delivery is **wheel-only**. The build backend produces an
installable wheel and refuses to build a source distribution; no wheel-to-sdist
equivalence is claimed, and whether a public release requires a source
distribution is a separate, later decision. Build provenance names this source
tree or nothing: a revision is recorded only when Git's top level is the Omama
source root, so a copy sitting inside an unrelated repository reports its
revision as unavailable and non-clean instead of borrowing that repository's
commit. Payload generation discards this project's own stale setuptools staging
first, and overlapping builds of one checkout are serialized by a build lock so
each produces the same payload inventory and identity.
