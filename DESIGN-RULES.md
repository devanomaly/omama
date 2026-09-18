# Design rules

This file indexes the invariants that hold across more than one piece of Omama. A rule belongs
here only if both are true: it spans more than one component or workflow stage, and breaking it
produces a wrong or misleading result — a false green, a receipt attesting to the wrong tree —
not merely an error message. Everything else stays in the piece's own README; this file does not
restate those docs, it points at the line that enforces the rule and says why the rule exists.
Each entry is four fields: the invariant, the failure it prevents, the incident that taught it,
and the authoritative line. If you cannot fill "Why" with a wrong result, it is not a design rule.
Omama's stance is that what the human reads per task should stop being unbounded prose: the
artifact declares its tier and carries done-when, verify, and verdict-first, so the reader's cost
per task is bounded by the artifact's own declaration rather than by however much the author chose
to write.

## How to add a rule

1. Qualify it: name the two components or stages it spans and the wrong result (not the error)
   its violation produces; if either is missing, it belongs in a component README.
2. Write the four fields; "Authoritative" must point at text that already exists in the
   enforcing doc — if it does not, land that sentence first, in the same PR.
3. Cite the incident by PR or issue number, and mark it open if unfixed; omit "Bit us" only when
   there is genuinely no incident, and say so in the PR.

## A. What a verdict may claim

### DR-1 — **Never exit 0 for what you did not evaluate.**

- **Invariant:** Partial coverage counts as `NOT-RUN`, never as approval — a checker that
  couldn't look must never report "passed."
- **Why:** Without this, an unreadable or partially-read input would exit 0, and a downstream
  gate would treat "could not evaluate" as "evaluated and clean."
- **Bit us:** PR #21 / issue #9.
- **Authoritative:** `validator/README.md:69` — "Partial coverage counts as `NOT-RUN`, never as
  approval: a checker that couldn't look must never report \"passed\"" — also
  `CONTRIBUTING.md:98-99` and `cli/README.md:22`.

### DR-2 — **Leave the unobserved empty; never estimate it.**

- **Invariant:** An observation that was not made is left empty, never estimated after the
  fact. Two fields are the exception, and there the export refuses rather than appends: a
  `t0`/`t1` given without a UTC offset, and a FAILED/UNVERIFIED row without its
  `close_reason_class` — an empty value there is a broken row, not honest absence.
- **Why:** An invented value would make every downstream statistic computed from it a fiction,
  turning a measurement of the harness into a measurement of a guess; and a FAILED row left
  unclassified cannot be classified later, because the next card overwrites the receipt.
- **Bit us:** PILOT.md amendment via PR #24 review (offset-naive t0 could not be subtracted; the
  export refuses rather than guesses).
- **Authoritative:** `PILOT.md:226-240` — "A field that was not observed is left empty. It is
  never estimated after the fact … Two fields are the exception, because leaving them empty
  would not be honest absence but a broken row, and the command refuses rather than appends."

### DR-3 — **Break ties against your own thesis.**

- **Invariant:** When a classification is ambiguous and the classifier is also the person the
  classification would vindicate, the tie resolves against the thesis.
- **Why:** Resolving an ambiguous case toward the thesis could produce a false survival, which
  is the more expensive error than a false failure.
- **Bit us:** Applied, not bitten — two recorded applications: `PILOT.md:82-89`
  (2026-08-25) and `PILOT.md:90-94` (2026-09-15, via PR #62).
- **Authoritative:** `PILOT.md:87-89` — "The tie-breaker, recorded so it binds later disputes:
  ambiguity resolves *against* the thesis, because the pre-registration author is also the
  thesis author."

## B. How a guard earns its green

### DR-4 — **Watch it fail for the right reason, through the shipped artifact.**

- **Invariant:** Every guard is proven against the artifact and configuration a team actually
  installs, never a neutralized stand-in.
- **Why:** A fixture that proves "committable" under a config nobody ships proves nothing, and a
  guard that only blocks a stand-in will pass while the shipped config blocks real work
  differently (or not at all).
- **Bit us:** privacy-hook's first self-check was green with empty team rules while the shipped
  config blocked the same files.
- **Authoritative:** `CONTRIBUTING.md:119-132` — "a fixture that proves \"committable\" under a
  config nobody ships proves nothing (privacy-hook's first self-check was green with empty team
  rules while the shipped config blocked the same files — the review caught it by making a real
  commit)."

### DR-5 — **A simulated absence must be a real absence.**

- **Invariant:** A fixture that claims to simulate a missing dependency must make that
  dependency genuinely unresolvable in the environment the fixture runs in.
- **Why:** A PATH that merely looks stripped but still resolves the dependency makes the
  "git-less" case take the normal code path while reporting green, so the degraded/refusal
  behavior it names is never actually exercised.
- **Bit us:** PR #61 / issue #55 — `gate_env(strip_path=True)` used `dirname(sys.executable)`,
  which on Debian/Ubuntu still resolves git, so three "git-less" cases took the normal route and
  reported green; CI could not catch it because setup-python installs into a tool cache with no
  git.
- **Authoritative:** `receipt-gate/fixture/run_fixture.py:159-174` — "The git-less cases used
  dirname(PY) directly. On a host where the interpreter and git share a bin directory (stock
  Debian/Ubuntu: both in /usr/bin) that PATH still resolves git, so the cases took the normal
  route and reported green while never reaching the degraded/refusal behaviour they name."
  Also `receipt-gate/README.md:262-264` — "A fixture that simulates a missing dependency
  proves the dependency is absent in the environment
  that runs it — a PATH built from the interpreter's own directory still resolves git on hosts
  where both share a bin directory."

### DR-6 — **Detect a platform no-op on the platform where it is a no-op.**

- **Invariant:** A check for a platform-specific no-op must run, and must be able to fail, on
  the platform where the operation is a no-op — not only on platforms where it isn't.
- **Why:** The producer and the victim are on different platforms. Windows runs the hook
  regardless, so nothing looks wrong where it was committed; the hook is silently skipped on
  every POSIX clone. Only a check on the producing platform catches the wrong recorded mode
  before it reaches the clones.
- **Bit us:** issue #59 / PR #63 — Windows `chmod` is a no-op, hooks commit `100644`, POSIX
  clones skip them with only a `hint:`, and doctor skipped the check on `nt`.
- **Authoritative:** `privacy-hook/ADOPTION.md:61-66` — "On Windows, `chmod` cannot set the bit
  on disk and Git for Windows runs the hook regardless... a plain `git add` records the file as
  `100644`, and Git on every POSIX clone then skips it with only a `hint:` line" (also
  `cli/README.md:148-151`).

### DR-7 — **A printed command is unverified until executed: hostile inputs, every claimed shell, the target's actual state.**

- **Invariant:** A remedy command the tool prints for the human to run is not proven correct
  merely by being printed — it must be verified against adversarial input, the shell it claims
  to run in, and the actual state of the target it will act on.
- **Why:** An unverified printed command can silently configure the wrong repository, or fail
  outright, while looking like a working remedy.
- **Bit us:** issues #64 and #66 — **both OPEN**. #64: a root containing shell-special
  characters makes the activation line configure a DIFFERENT repository. #66: the printed mode
  remedy exits 128 on a fresh install because the hooks are still untracked. The second half
  (every claimed shell, on hostile targets) is an unenforced residual.
- **Authoritative:** `cli/README.md:153-157` — "printed with `git -C \"<inspected repository>\"`
  so it acts on the repository doctor read and not on the directory it is pasted into
  (shell-quoted on POSIX; on Windows a path holding `%`, `!`, `$`, a backtick or a typographic
  double quote gets a manual step and no repository-bound line, because no quoting is common to
  CMD, PowerShell and Git Bash)."

## C. What a record binds

### DR-8 — **A receipt binds one tree on one checkout.**

- **Invariant:** A VERIFIED receipt always carries non-null `rev`/`patch_id`/`diff_sha`; those
  hashes are recomputable only on the same checkout while that tree still exists, never
  cross-machine; and a receipt is never committed, because the commit that would add it
  changes the tree it hashes.
- **Why:** A null hash makes a VERIFIED forged on its face. Treating the hashes as portable
  invites a "verification" that cannot be recomputed. And a committed receipt carries a hash
  already stale for the very commit that ships it — three ways for a record to attest to a
  tree that is not the one it names.
- **Bit us:** issue #14 / PR #19.
- **Authoritative:** `receipt-gate/README.md:36-39` — "A VERIFIED receipt always carries
  non-null rev/patch_id/diff_sha — a VERIFIED with a null hash is forged on its face" AND
  `receipt-gate/adapt/README.md:188-198` — "A committed receipt would be worse: it binds the
  hash of the tree it was written against, and the commit that adds the receipt file changes
  that tree by construction, so the hash it carries would already be stale for the commit that
  ships it."

### DR-9 — **Bind every category of input the same way; the asymmetry is the bypass.**

- **Invariant:** Every category of tree state that could hide a mutation must be bound with the
  same rigor — untracked CONTENTS not just names, `-z` raw name parsing, `lstat` before open,
  links never followed.
- **Why:** Binding one category loosely while binding another tightly lets a rewrite hide
  precisely in the loose category and still close VERIFIED.
- **Bit us:** issue #58 / PR #62.
- **Authoritative:** `receipt-gate/README.md:100-127` — "names alone left a verify free to
  rewrite an untracked source and still close VERIFIED, while the same rewrite of a tracked file
  was caught... a gate that read the escaped form would read a path that does not exist...
  following it recorded an `unreadable:` sentinel for a directory link, so a verify could
  retarget the link permanently and still close VERIFIED."

### DR-10 — **Refuse inherited Git routing before writing evidence; empty counts as set.**

- **Invariant:** Inherited Git-routing/config-injection environment variables are refused before
  any input is read or evidence written, and an empty value counts as present.
- **Why:** Inherited routing variables can silently redirect the gate to bind a different
  repository or tree than the one it reports on, producing a receipt for the wrong checkout.
- **Bit us:** PR #45; related #42 / PR #44 (CROSS-REPO).
- **Authoritative:** `receipt-gate/README.md:73-76` — "Before input or card discovery,
  `GIT-ROUTING` refuses inherited Git repository routing/config-injection variables, even empty
  ones" AND `receipt-gate/adapt/README.md:202-210` (full variable list) — "Empty values count as
  present. Unset them in the child hook environment and retry; do not merely set them to empty
  strings."

### DR-11 — **Keep the harness identifiable: record its version, keep vendored bytes identical.**

- **Invariant:** The harness version an adopting repository runs is recorded at start, every
  change to a measured piece (validator, gate, card schema) during the window is recorded as a
  dated harness-version change, and vendored copies of Omama files are kept byte-identical to
  upstream.
- **Why:** An unrecorded harness change makes a later failure uninterpretable — the harness that
  failed the card would not be identifiable — and a reformatted vendored copy loses the clean
  baseline needed to review a later update.
- **Bit us:** PR #32 (`PILOT.md:349-354`, §7 item 7, added after a self-tested machine was
  found with no Stop hook);
  vendoring issue #16, open.
- **Authoritative:** `PILOT.md:349-354` — "Any change during the window to a measured piece
  (the validator, the gate, the card schema) is recorded as a dated harness-version change next
  to the log … an unrecorded one makes `close_reason_class = harness`
  uninterpretable, because the harness that failed the card would not be identifiable" AND
  `VENDORING.md:10-12` — "Exclude copied Omama files from every formatter, linter, editor
  action, and pre-commit step that could rewrite them."

## D. What an artifact declares

Two tier vocabularies live in this repo and never mix: `S1|S2|S3` is card severity
(work-order), `XS|S|M|L` is artifact tier (output-discipline) — `CONTRIBUTING.md:78-80`.

### DR-12 — **Tier an artifact by consequence, exposure, detection difficulty, and cost to correct later.**

- **Invariant:** a plan's or review's tier (`XS|S|M|L`) is set by those four factors, not by how
  long the artifact happens to be; the tier then fixes which structure the artifact must carry
  (DR-15).
- **Why:** an artifact tiered by apparent size is under-structured exactly where it matters — a
  high-consequence review written as XS carries no Findings or Non-findings sections, and the
  checker grades it against the smaller contract it declared.
- **Bit us:** Applied, not bitten — no incident on record. Issues #46 and #47 are **open** on
  the ambiguity of these four factors and the rubric's inter-reviewer calibration. Card
  severity (`S1|S2|S3`) has no written ranking criteria of its own; DR-13 covers who decides it.
- **Authoritative:** `output-discipline/README.md:29` — "Tier = consequence × exposure ×
  detection × cost to correct later." Also `output-discipline/templates/PLAN.md:4-6` — the
  `XS | S | M | L` declaration and "Tier = consequence × exposure × detection difficulty ×
  cost-to-correct-later." The two spell the third factor differently; issue #46 is open to
  reconcile them.

### DR-13 — **A validator checks form; the human ratifies meaning.**

- **Invariant:** the validator checks that a card's fields are well-formed and nothing about
  whether they are true: a card's tier is agent-proposed and human-ratified, and whether its
  `verify` actually proves its goal is human review. For S3 cards the receipt gate enforces the
  review half of the routing invariant — a review pass before a **VERIFIED** close, via the
  `S3-REVIEW` block — while an honest FAILED/UNVERIFIED close skips the review by design, and
  plan approval before implementation is not checkable by a Stop hook at all.
- **Why:** `tier: S1` on S3-scale work, or a real but irrelevant `verify`, passes the validator
  cleanly; a green validator taken as evidence of honesty skips the routing an S3 requires or
  certifies a goal nothing tested.
- **Bit us:** Applied, not bitten — designed boundaries. `work-order/README.md:206` classes the
  S3 invariant "out of scope (by design)" for the validator; the gate implements its review
  half (`receipt-gate/receipt_gate.py:772-828`), after the honest-close return at `:667`.
- **Authoritative:** `work-order/README.md:93-94` — "`tier: S1` on S3-scale work passes the
  validator — ratification is human by design; enforcement of the S3 invariant belongs to the
  receipt gate." `work-order/README.md:87` — "a `verify` that is technically real but
  irrelevant to the goal passes — the validator checks form, not relevance." And
  `receipt-gate/README.md:138-145` — "Plan-mode approval is NOT checkable by a Stop hook — an
  honest boundary. An honest close of an S3 card skips the review but still writes a durable
  FAILED/UNVERIFIED verdict: the skip is visible, never silent."

### DR-14 — **A review's verdict goes in the first three content lines, or the check fails.**

- **Invariant:** a review's verdict appears within the first 3 content lines — non-empty lines
  after HTML comments are removed. Buried or missing, the checker records a violation and
  exits 1 (FAILED). An artifact with no type/tier declaration is not graded at all: NOT-RUN,
  exit 2. Verdict-first is mechanical for reviews; for plans, tier-L "summary first" is template
  guidance only.
- **Why:** a verdict the reader has to hunt for gets skimmed past. Naming the two exits apart
  matters as much: FAILED means assessed and wrong, NOT-RUN means not assessed at all, and
  collapsing them is the confusion DR-1 exists to prevent.
- **Bit us:** Applied, not bitten — pinned by the fixture cases `review_verdict_buried` and
  `verdict_theater_passing` (`output-discipline/README.md:99`).
- **Authoritative:** `output-discipline/README.md:38-40` — "**Reviews** (every tier): verdict
  within the first 3 non-empty lines — buried fails, mechanically. **Honest note:** in
  **plans**, tier L \"summary first\" is template guidance, **not** a mechanical check." The
  lines counted are content lines: `output-discipline/scripts/check_artifact.py:52-56`
  (`content_lines`, HTML comments removed) and `:107` (`first3 = lines[:3]`); an undeclared
  artifact raises `NotRun` at `:75` and returns 2 at `:158-162`.

### DR-15 — **Length is a tiered contract, not a style preference.**

- **Invariant:** the artifact tier sets an advisory line budget and escalating structural
  requirements (table at `output-discipline/README.md:31-36`). Structure is enforced in every
  mode; the budget fails by default and is downgraded to a warning only under
  `--budgets-advisory`, the mode the seed loop and the S3 review check run.
- **Why:** without the tiering, brevity is a matter of taste and the reader's cost per task is
  unbounded. Reading the advisory mode as universal is its own wrong result: a green from a
  `--budgets-advisory` run means "structurally sound", not "within budget".
- **Bit us:** Applied, not bitten. The advisory split is a panel decision, not a measured
  result: on 2026-08-19 a five-member panel voted 5/5 to keep structure and 4/5 to kill line
  budgets (`README.md:133` explains the tallies are panel votes). Whether the contract works is
  what the ON TRIAL ledger is still measuring.
- **Authoritative:** `output-discipline/README.md:17-19` — "The line budget is advisory: the
  checker warns, it does not fail (default mode still fails; the seed loop runs with
  `--budgets-advisory`)." `output-discipline/README.md:59` — "Without the flag, behavior is
  byte-for-byte identical to before." And `output-discipline/README.md:54-58` for what stays
  mandatory: buried/missing verdict, non-findings, done-when/verify ⇒ exit 1, while a missing
  type/tier declaration is NOT-RUN, exit 2 (DR-14).

*DR-12, DR-14 and DR-15 rest on output-discipline, marked **ON TRIAL**
(`output-discipline/README.md:6-11`): its mechanics are fixture-proven but its effectiveness
verdict does not yet exist.*
