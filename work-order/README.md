# Work Order (card slim)

> Docs for this piece: **README** (promise, command, states, coverage) ·
> [ADOPTION.md](ADOPTION.md) (integration and human decisions). The evidence is the
> re-runnable fixture; the legacy schema's red-green history lives in git
> (EVIDENCE.md through 2026-08-19).

## The decision this piece changes

Before: an agent receives "fix bug X" as loose prose and decides scope and what
counts as "done" alone. After: the task enters as a **slim card** — goal, non-goals, tier
ratified by the human, observable done-when, **one real `verify` command**, and attached
reproduction when it's a bugfix. The concrete decisions that change: **a bugfix without
attached reproduction does not pass** (exit 1), **a vacuous `verify` does not pass** (a card
whose proof command is `true`/`echo` closes nothing), and tier S3 carries the routing
invariant — plan approval + review pass before close. The validator is preflight: it
proves the card before dispatch; whoever re-runs `verify` at close and emits VERIFIED is
the receipt gate, not this validator.

## What it is

- `work-order.template.yaml` — the slim schema, every field commented in English.
- `validate_work_order.py` — deterministic validator (no LLM) of a **closed schema**:
  - required keys (`goal`, `non_goals`, `tier`, `task_type`, `done_when`,
    `verify`) present and **no unknown key**; a value that is present-but-null is a
    named violation (containment theater);
  - `tier` from the closed enum S1|S2|S3 (proposed by the agent, ratified by the human);
  - `verify` is ONE non-vacuous command — minimal deny-list: empty, `true`, `:`,
    `echo ...` — applied to the **first word of every segment** of the command line
    (after `||`, `;`, `&&`, `|`, `|&` and a newline, and inside quotes), so
    `pytest -q || true` and `cd app && echo ok` are rejected; a **backgrounded**
    command (a bare `&` at a command boundary) is rejected too, because its exit
    status is discarded;
  - `bugfix => repro` attached and typed (non-empty string/list; `repro: true` is a
    checkbox and is rejected);
  - **duplicate YAML key rejected** (the default parser would silently keep the last
    one);
  - **fail-closed**: malformed config produces a named `VIOLATION:` and exit 1, never
    a traceback.
- (GUIA.md used to describe the legacy schema; removed in the 2026-08-19 reorg —
  the commented template is the guide now.)
- `fixture/` — 11 clean cases + 35 cases with a planted violation + runner with
  regression locks (each red pinned to ALL of its named reasons). Legacy-schema
  fixtures: `fixture/archive/`.

## Command and states

```
python3 validate_work_order.py <card.yaml>
```

| Exit | State | Means |
|---|---|---|
| 0 | OK | well-formed card; prints `OK: ...` |
| 1 | VIOLATION | one `VIOLATION: ...` line per reason on stderr (includes internal error — fail-closed) |
| 2 | not runnable | pyyaml missing or wrong CLI usage |

Fixture: `python3 fixture/run_fixture.py` (exit 0 = validator correct).

## Scope and limits

### What it catches

Forty-six fixture cases, each red pinned to all of its named reasons. Classes
covered: missing/unknown/duplicate key, null values, tier outside the enum,
vacuous `verify` (four whole-command deny-list variants plus twenty-three segment
shapes: after `||`, `;`, `&&`, `|`, `|&` and a newline; inside a `( )` or `{ }`
group; spelled with quotes (`'tr'"ue"`) or a backslash (`\true`); split by a
backslash-newline continuation; behind a redirection, an assignment or a
`then`/`else`/`do`/`time`; and a backgrounded `&`), bugfix without repro,
repro-checkbox, malformed `task_type` without a traceback. Ten of the eleven clean
cases exist to pin what the segment rule must NOT reject — a `&` inside a word, a
quoted body carrying `;`, a real `|&` pipeline, a trailing separator, `! true`.

### What it does NOT catch

Named gaps, each with the layer that resolves it:

- **Truth of content.** A made-up `repro` passes; a `verify` that is technically real
  but irrelevant to the goal passes — the validator checks form, not relevance. Resolved
  by: human reading of the card before dispatch.
- **Post-execution compliance.** The validator is preflight: it never observes the diff
  or the `verify` result. Resolved by: the receipt gate (Stop-hook) re-runs `verify` at
  close and binds the result to the current tree.
- **Tier ratification.** `tier: S1` on S3-scale work passes the validator — ratification
  is human by design; enforcement of the S3 invariant belongs to the receipt gate.
- **Dispatch without the validator.** Nothing forces `validate_work_order.py` to run
  before the agent is dispatched. Resolved by: a gate in the dispatch pipeline.
- **Vacuity beyond the deny-list.** The rule changed WHERE the three denied tokens
  (`true`, `:`, `echo`) are looked for — the first word of every segment — not WHICH
  tokens are denied, and it is deliberately not a shell parser. Still undetected:
  - `|| exit 0`; the wrapper words `command`, `env`, `exec`, `nohup`; a path spelling
    of the no-op (`/bin/true`).
  - **The shell model itself.** The rule reads `verify` as a POSIX/bash command line,
    but the receipt gate runs it with `Popen(shell=True)` — /bin/sh on POSIX, **cmd.exe
    on Windows**. cmd.exe no-ops (`|| ver`, `|| rem x`, `|| echo.`, `|| exit /b 0`) and
    `true.exe` on a PATH that carries Git's `usr/bin` are not detected.
  - `| tee` masking the exit status of the command that fed it.
  - A no-op produced by expansion — `$(echo true)`, `${X:-true}`, `$'true'`,
    `true$(:)`, or brace expansion `tr{,}ue` / `{true,}` — since a token beginning with
    `$` or carrying a brace pair is legitimate (`$PYTHON -m pytest`, `cp a{,.bak}`).
  - An assignment whose value carries whitespace, or whose target is not a bare NAME:
    `X="a b" true`, `X=(1 2) true`, `X=$(a b) true`, `X[0]=1 true`.
  - Redirection operators outside the seven listed (`&>>`, `>|`, `<>`, `{fd}>`) — a
    segment behind one of them exposes the wrong first word — and `time` with a flag
    (`time -p true`).
  - `! false`, and a doubled `! ! true`.
  - A loop or conditional whose CONDITION is the no-op: `until true; do A; done`,
    `if true; then exit 0; fi`, `... elif true; then exit 0; fi`, the polling idiom
    `while true; do X && break; sleep 1; done` — plus a `while`/`until` loop whose
    status is its last body command's (0 when the body never runs, or ends in `break`).
  - `case x in x) true;; esac` — the no-op follows the pattern, not the reserved word.
  - `coproc true`; a no-op inside a shell function defined in `verify` itself.
  - An always-true shell test (`[[ 1 ]]`, `((1))`, `test 1`) or an always-green pytest.
  - A segment that is only an assignment or a redirection (`|| X=1`, `|| >/dev/null`):
    it is skipped, never a violation.
  - Backgrounding is caught only when the `&` is followed by whitespace, `)` or the end
    of `verify` — `&}`, `&#` and a `&` inside a word are not inspected.
  - `python -c "pass"`, and vacuity inside a script that `verify` calls.

  Resolved by: **the human read of the card — and nothing else.** This corrects an
  earlier version of this line: the receipt gate does NOT resolve this class. A
  cannot-fail command exits 0 for real, so re-running it at close produces a genuine
  green; the gate binds a result to the tree, it cannot tell a proof from a no-op.

- **Over-approximation: real commands the rule rejects by design.** Because the rule is
  not a shell parser, it also rejects shapes that CAN fail. Each has a rewrite — if a
  card of yours was newly rejected, it is one of these:
  - A message attached to a real command: `A && echo done`, `echo starting && A`,
    `A || { echo msg >&2; exit 1; }`, `A && echo ok || exit 1`. Rewrite as `A` alone or
    `A || exit 1` — the message belongs in the runner's output, not in `verify`.
  - An `echo` that only feeds a pipeline: `echo '{"a":1}' | python validate.py`,
    `echo hi | grep -q hi` (rejected by the first-token check before this change too;
    named here because this is where a rejected adopter is sent). Rewrite as
    `printf '...\n' | A`, a here-string `A <<< '...'`, or `A < fixture.json`.
  - An operator inside a command substitution whose fallback is a no-op:
    `V=$(A || echo default); test "$V" != default`, `X=$(A; echo $?); test "$X" = 0`.
    Rewrite as `V=$(A) || V=default; test "$V" != default`, or `A; test $? -eq 0` /
    just `A` for the status-capture form.
  - `: "${VAR:?msg}"` used as a precondition. Rewrite as `test -n "$VAR" && A` — not
    the `[ -n ... ]` spelling: unquoted in YAML a leading `[` opens a flow sequence and
    the validator rejects the card as not valid YAML — or embed the expansion in the
    real command: `A --flag="${VAR:?msg}"`.
  - A quoted `|true` alternation: `grep -Eq "PASS|true" f`. Rewrite as two patterns
    (`grep -q -e PASS -e true f`) or a bracket expression (`"PASS|tru[e]"`).
  - A quoted `; echo` / `; True` body — `python -c "import sys; True if ok else sys.exit(1)"`
    — and a heredoc line that reads as operator + no-op. Move the body or the heredoc
    into a script that `verify` calls.
  - A `#` comment that mentions an operator plus a no-op: `pytest -q  # do not add || true`.
    Drop the comment.
  - `:>file` truncation, glued or spaced: `:>out.log && pytest -q >>out.log`. Rewrite
    with `>`, which truncates on its own.
  - A quoted `& ` or `&)` at a command boundary: `python -c "... (3 & 1) ..."`,
    PowerShell's call operator `"& .\run.ps1"`, sed's whole-match back-reference in
    parentheses `s/PASS/(&)/`. Write `(3&1)` unspaced, call the script by path without
    the `&`, or use a capture group: `s/\(PASS\)/(\1)/`.
  - An unquoted `&` that starts a helper before the real check:
    `server.py & sleep 2 && curl -fsS .../health`, `A & wait $!` (the rule does not read
    as far as the `wait`). Move the helper's start and stop into a script that `verify`
    calls, so `verify` itself carries no `&`.

  Resolved by: the rewrite. In every case above the rewrite is a `verify` whose exit
  status is itself the proof — which is what the field is for.

### What only a human decides

See [ADOPTION.md](ADOPTION.md) — relevance of `verify` to the goal, narrowness of
non-goals, veracity of the repro, ratification of the tier.

### Coverage

| Promised | Covered mechanically | Not covered / known bypass | Classification |
|---|---|---|---|
| Bugfix without attached reproduction does not pass | `invalid_bugfix_no_repro` + `invalid_repro_checkbox` → exit 1 | dispatch that skips the validator | accepted limitation |
| Vacuous `verify` does not pass | 4 whole-command deny-list variants + 23 segment shapes (after `\|\|`, `;`, `&&`, `\|`, `\|&`, newline; quoted; grouped; redirected; assigned; `then`/`else`/`do`/`time`; backgrounded `&`) → exit 1, and 10 clean cases pin what stays accepted | vacuity outside the deny-list (`python -c "pass"`, `\|\| exit 0`, `/bin/true`, expansions, cmd.exe no-ops under the gate's `shell=True`) — and, in the other direction, real commands the rule over-rejects (`A && echo done`), each with a documented rewrite | accepted limitation |
| Closed schema, no silent key | unknown/duplicate/null → exit 1 | — | covered |
| Tier routes S3 to plan+review | enum value → exit 1 | the invariant itself (enforcement is the receipt gate's) | out of scope (by design) |
