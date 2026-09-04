# Quickstart — the minimum loop, from clone to first receipt

Every command below was executed on a scratch repository before this document
was committed (on Windows, with the interpreter substitutions noted inline);
the mechanical path — not counting reading — took the author's machine just
over 6 minutes. Commands are written `python3` — on Windows substitute `py -3`
(see [Prerequisites](README.md#prerequisites)).

*[Versão em português](QUICKSTART.pt-BR.md)*

## 1. Watch it refuse to overclaim (2 commands, no commitment)

Install the dependencies FIRST — without PyYAML the fixtures report `FAILED`,
which reads as "broken repo" when it means "missing dep" (the detail lines do
say `pyyaml not installed`, but only if you read past the summary):

```
pip install pyyaml
python3 verify_all.py --fast
echo $?
```

Expected: `7 ok, 0 failed, 1 not-run` — and **exit code 2, not 0**. Seven
passes plus one skipped check is not a pass; a verifier that reports success
for coverage it skipped is lying. That exit code is this toolkit's entire
posture in one observable bit. (`python3 verify_all.py` without `--fast` runs
the skipped corpus too — takes minutes — and exits 0.)

## 2. The minimum loop is three pieces

- **[work-order](work-order/README.md)** — the task enters as a card: goal,
  non-goals, human-ratified tier, observable done-when, ONE `verify` command
  that can fail. Without it the gate has nothing to hold you to.
- **[receipt-gate](receipt-gate/README.md)** — a Stop hook that re-runs the
  card's own `verify` before a close may claim VERIFIED, and writes a receipt
  either way. Without it the card is prose.
- **[output-discipline](output-discipline/README.md)** — structure for
  plans/reviews (verdict first, explicit non-findings). Needed from day one
  only for S3 cards; adopt the templates when you get there.

Everything else in the repo is optional and separable — see
[How to adopt](README.md#how-to-adopt).

## 3. Install into your repository

From your repo root (`<OMAMA>` = your clone of this repo):

```
mkdir -p .claude/hooks tools
cp <OMAMA>/receipt-gate/receipt_gate.py   .claude/hooks/
cp <OMAMA>/work-order/validate_work_order.py  tools/
cp <OMAMA>/work-order/work-order.template.yaml .
```

Register the hook: copy the `hooks` block from
[receipt-gate/adapt/settings.example.json](receipt-gate/adapt/settings.example.json)
into **your repository's** `.claude/settings.json`. Three rules, each of which
prevents a gate that *looks* installed while being silently absent or
permanently blocking:

- **Per-repo, NEVER `~/.claude/settings.json`** — a broken global gate blocks
  every repo you own; a broken per-repo gate blocks only the repo that opted in.
- **Absolute interpreter path in the command, not `python3`** — if the
  launcher is missing on the host the shell exits 127/9009, which does NOT
  block: the gate is silently absent forever.
- **Set the env vars BEFORE the self-test** — `OMAMA_CARD` (path to the
  active card) and `OMAMA_VALIDATOR` (path to your copied
  `validate_work_order.py`). Without them every close blocks with
  `SCHEMA: validator unrunnable`. `OMAMA_CHECK_ARTIFACT` is only required
  once you use S3 cards. Full table:
  [receipt-gate/adapt/README.md](receipt-gate/adapt/README.md).

The gate needs a git repo with at least one commit (an unborn HEAD
fail-closes, by design).

## 4. Prove the gate: wiring check, then red, then green (mandatory — do not skip)

An install you haven't watched block is not installed. This section is the
self-test that [adapt/README.md](receipt-gate/adapt/README.md) makes
mandatory — first the mechanical wiring check, then run the gate via the
EXACT command string you registered in `settings.json`, copy-pasted, not
retyped.

**Step 1 — wiring check.** From your repo root:

```
python3 <OMAMA>/receipt-gate/adapt/check_wiring.py    # Windows: py -3 ...
```

**Expected: `WIRING-OK ...` and exit 0.** It resolves the registered Stop
hook command and dry-runs it on empty stdin — a missing interpreter, a
bare launcher name instead of its absolute path, a wrong or missing
`receipt_gate.py` argument, a `CLAUDE_PROJECT_DIR` the hook shell would
leave literal (`%VAR%` spelling, single quotes), a hook in a form the
check does not certify (`async`, exec-form `args`, `shell: powershell`),
any other `$` expansion in the command, or `disableAllHooks` in a
settings file is a named `VIOLATION` (exit 1) instead of the silent
127/9009 absence; on Windows without Git Bash the answer is NOT-RUN (exit
2), because the hook would run through PowerShell. (It EXECUTES the
registered command — that is the point; details, the certified form, CI
use, and `--static-only` in [adapt/README.md](receipt-gate/adapt/README.md).)

**Steps 2–3 — red, then green.** Add the gitignore snippet first — a card is per task and per machine, not
something to version (see [work-order/ADOPTION.md](work-order/ADOPTION.md#the-card-and-its-receipt-stay-local)
for why):

```
cat >> .gitignore <<'EOF'
CARD.yaml
CARD.close
CARD.receipt.json
*.receipt.json
EOF
git add .gitignore
git commit -m "gitignore: card and receipt stay local"
```

Write a first card, `CARD.yaml`, whose `verify` does not pass **yet** —
e.g. for a repo where `app.js` still says `hi`:

```yaml
goal: app.js greets with "hello" instead of "hi"
non_goals:
  - any file other than app.js
tier: S1
task_type: implementation
done_when:
  - app.js source contains the string hello
verify: python3 -c "exit(0 if 'hello' in open('app.js').read() else 1)"
```

(Write `verify` in whatever runs on YOUR machine — on Windows, `python`.)

```
python3 tools/validate_work_order.py CARD.yaml   # expect: OK ... valid card
echo "CLOSE" > CARD.close
echo '{}' | <exact command string from your settings.json>
```

Nothing to commit yet — `CARD.yaml` and `CARD.close` are gitignored, and
`app.js` hasn't changed.

**Expected: `RECEIPT-GATE BLOCK[VERIFY-RED]` and exit 2.** That block is the
product working. (The `{}` on stdin stands in for the Stop-hook payload
Claude Code sends; empty stdin is itself a named block, by design.)

Now do the work and close again:

```
# ...make app.js print hello...
git add -A && git commit -m "greet with hello"
echo "CLOSE" > CARD.close
echo '{}' | <exact command string from your settings.json>
```

**Expected: exit 0, `VERIFIED ... receipt written`, and `CARD.receipt.json`
on disk** with the verify command, exit code, and tree hashes bound together.
`CARD.close` is gone — the gate consumes it on every allowed close; the
receipt is the durable record. Honest closes (`FAILED: <reason>`,
`UNVERIFIED: <reason>`) always pass and always leave a receipt too.

If you saw WIRING-OK, the red BLOCK **and** the green VERIFIED, the loop is
installed. A red/green result without the other means broken wiring — see the self-test section of
[adapt/README.md](receipt-gate/adapt/README.md) for what each partial result
means.

## 5. Dispatch

The loop is installed. Dispatching a task through it is one line:

```
Implement CARD.yaml at the repo root.
```

Three things have to be true first, and §§1–4 produce none of them: the real
card is on disk where §4's sample was (`CARD.yaml`, validated, `tier`
ratified by a human); the branch is cut from the default branch's tip; and
the repo's `CLAUDE.md` was adopted from
[starter-claude-md](starter-claude-md/ADOPTION.md) (piece 08) and passes its
checker. §§1–4 install the gate, not the starter — and the starter is where
the close and branch rules in the table below live. Without it the agent
stops with no `CARD.close`, the gate correctly reads that as WIP, and the
task ends with no receipt.

That line is sufficient **because the pieces carry the rest**. Each time a
dispatch here needed an extra line, the extra line turned out to name
something a piece already owns:

| Extra line the dispatch needed | What already owns it | Carried by |
|---|---|---|
| "touch nothing outside this directory" | the card's `non_goals` — the frozen list of what the diff must not contain | 02 |
| "write `CLOSE` to `CARD.close` when you're done, then stop" | the starter file's Stop-hook rule, under "Hooks installed in this repo", tagged `[10]` | 08 |
| "branch off the default branch's tip and open a PR against it" | the starter file's branch rule, under "Bugfix requires a work order", tagged `[02]` | 08 |

**A dispatch prompt that needs a second line names a missing or unadopted
piece.** Read the extra line as a finding, not as prose to keep: either the
card's `non_goals` is too loose, or this repo's `CLAUDE.md` is missing the
rule (see [starter-claude-md](starter-claude-md/README.md), whose checker
rejects an untagged or out-of-set rule; whether a tag names the *right*
piece stays human review). Fix the artifact, not the prompt.

**Closing, from the agent's side.** When the card's work is done the agent
writes `CLOSE` to `CARD.close` next to the card — the gate reads it from the
card's directory, here the repo root — and stops; that is the whole protocol
it owns. The gate does the rest: re-runs the card's own `verify` against the
current tree, writes `CARD.receipt.json`, and blocks a red close (exit 2,
named) instead of letting it claim VERIFIED. Stopping with no `CARD.close`
is a WIP turn and is allowed. Every value `CARD.close` can carry — including
the honest `FAILED:`/`UNVERIFIED:` closes — is in the table at
[receipt-gate/README.md](receipt-gate/README.md#close-model-the-gate-locks-the-claim-not-the-session);
it is not restated here, so there is only one copy to keep true.

When the dispatching session is **not** the session in the worktree, the
close is one print-mode `claude -p` run with the worktree as cwd — see
[Closing from an orchestrator](receipt-gate/README.md#closing-from-an-orchestrator-worktree-dispatch),
whose `adapt/selftest_orchestrator_close.py` proves it on your machine.

## 6. You now have

- Cards that freeze goal/non-goals/verify before dispatch, validated by
  `tools/validate_work_order.py`.
- A gate that re-runs the card's own proof before any close may claim
  VERIFIED, and writes a receipt for every close, honest failures included.
- A red self-test receipt proving the gate actually blocks on your machine.

Next: tier semantics and what only a human decides —
[work-order/ADOPTION.md](work-order/ADOPTION.md); S3 review artifacts —
[output-discipline/ADOPTION.md](output-discipline/ADOPTION.md); what the gate
does NOT catch — the residuals section of
[receipt-gate/README.md](receipt-gate/README.md). No efficacy claim is made
for any of this; see the [README](README.md).
