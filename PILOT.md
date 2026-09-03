# PILOT.md — what the internal pilot measures, and what would refute the thesis

**Status: PRE-REGISTERED.** Every threshold, window, and classification below was fixed by the
maintainer on 2026-08-25, before the first pilot card. The commit that introduces this file is the
registration rev — the numbers are pre-registered, not remembered. Any change to a threshold after
the first closed card voids the pre-registration and is said so in the write-up.

**Amended 2026-09-02, still before the first pilot card**, after an external review of the
registration found four protocol defects, each reproduced before it was fixed: the window could
qualify with zero S2 cards while the headline median is computed on S2 alone (§2); the export row
dropped `close_reason` and `close_reason_class`, the two fields T4 depends on (§3 b); the sample
`t0`/`t1` had no UTC offset and could not be subtracted from the receipt's offset-aware timestamp
(§1, §3 b); and the log sink was a path relative to the card directory, i.e. per-worktree, not
per-developer (§3 b). The registration rev is the commit that lands this amended file.

**Amended 2026-09-03, still before the first pilot card**, after the mechanical wiring check
landed (`receipt-gate/adapt/check_wiring.py`) and a machine that had been installed and
self-tested was found with no Stop hook at all: §7 item 5 now records the wiring check alongside
the self-test, and a new item 7 records the harness version at start and any change to a measured
piece during the window. No threshold, window, trigger, or classification changed. The
registration rev is the commit that lands this amended file.

**Amended 2026-09-03 (second), still before the first pilot card:** the two-developer premise did
not hold — the pilot runs with **one developer, the maintainer, dispatching agent executors**. §1's
`tier_dispute` definition, §2's scope sentence, §3's concatenation note, §4, §5 and §7 items 5–6
are reworded to say so. No threshold, window, or trigger changed; what changed is what a result is
worth — a non-refutation from the author's own use is worth less (§5), a refutation more. The
registration rev is the commit that lands this amended file.

**No efficacy claim is made here, and none is made by running this pilot.** The README says the
mechanics are what's proven — red-green fixtures and an external adversarial review that converged
on what to measure — and nothing more. This document does not add a claim; it fixes, in advance,
what would count as *evidence against* the smallest-sufficient-harness thesis, so that the pilot
can do something other than confirm. A pilot with no pre-registered stopping rule has exactly one
possible outcome, and it is not knowledge.

The thesis under test, quoted from the README: *the best harness is the least harness that still
holds* — one slim card, ONE `verify`, a receipt at close — and *if a piece here costs more
attention than the failure it prevents, that's a bug in Omama*. The falsifiable half is the first
half: attention cost. The second half (failures prevented) is counterfactual and this pilot cannot
measure it — see [What this pilot cannot show](#5-what-this-pilot-cannot-show).

---

## 1. What is measured, per closed card

One row per card that reaches a receipt, plus one row per card that is abandoned without one.
"Closed" means the gate wrote `CARD.receipt.json` — VERIFIED, FAILED, or UNVERIFIED alike.

| Field | Values | Source | Mechanical? |
|---|---|---|---|
| `tier` | `S1` \| `S2` \| `S3` | the ratified card | yes — `tier` in `CARD.yaml` |
| `task_type` | bugfix \| implementation \| refactor \| config \| do-nothing \| ask-first | the card | yes |
| `t0` | ISO timestamp **with explicit UTC offset** (`2026-08-23T09:12+00:00`) — card written and tier ratified | recorded by the developer, or `CARD.yaml` mtime at first write | approximate |
| `t1` | ISO timestamp **with explicit UTC offset** — **first** close attempt (`CARD.close` first written) | `CARD.close` mtime at first write | approximate |
| `t2` | ISO timestamp — receipt written | `timestamp` in `CARD.receipt.json` (the gate writes it offset-aware, UTC) | yes |
| `minutes_card_to_receipt` | `t2 − t0`, minutes | derived by the export command in §3 (b), which refuses an offset-naive `t0` rather than guessing a zone | derived |
| `minutes_close_loop` | `t2 − t1`, minutes | derived by the export command in §3 (b), same refusal on `t1` | derived |
| `blocks` | count + the **named** reasons, in order | gate stderr: `BAD-INPUT` · `CARD-CONFIGURED-BUT-MISSING` · `CLOSE-TOKEN` · `SCHEMA` · `GIT-ERROR` · `INDEX-FLAGS` · `UNEXPECTED-CHANGE` · `VERIFY-RED` · `TIMEOUT` · `S3-REVIEW` · `GATE-ERROR` | by hand — see §6 |
| `verdict` | `VERIFIED` \| `FAILED` \| `UNVERIFIED` | `verdict` in the receipt | yes |
| `close_reason` | free text, present on FAILED/UNVERIFIED | `reason` in the receipt | yes |
| `close_reason_class` | `work` \| `harness` \| `external` | classified by the developer at close — the sixth argument to the export command; **required** on FAILED/UNVERIFIED, refused on VERIFIED | by hand |
| `self_test_skipped` | `y` \| `n` | did this close happen on a worktree/machine where the receipt-gate install self-test (red AND green, per `receipt-gate/adapt/README.md`) had been run? | by hand |
| `tier_dispute` | `y` \| `n` (+ proposed → ratified, if `y`) | did the human ratify a tier different from the one the agent proposed? | by hand |
| `review_artifact` | `y` \| `n` \| `n/a` | S3 only: was `CARD.review.md` produced before close? | yes (S3 close implies `y`) |

**Two intervals, not one.** `minutes_card_to_receipt` is elapsed task time; most of it is the work,
not the harness, and it is not attributable. `minutes_close_loop` (`t2 − t1`) is the interval from
"I think I'm done" to "there is a receipt" — the card re-read, the verify re-run, every BLOCK and
every retry. That interval is close to harness-attributable, and it is the one the stopping rule
puts a threshold on. Both are recorded; only one is decisive.

**BLOCKs split into two kinds, and they are counted separately.** This split is pre-registered
because collapsing it would let the harness's successes and its friction cancel out:

- **Signal BLOCKs** — the gate refusing an unbacked claim: `VERIFY-RED`, `UNEXPECTED-CHANGE`,
  `S3-REVIEW`. These are the guard doing the job it was built for. A high rate here is not
  evidence against the thesis.
- **Friction BLOCKs** — the gate refusing on its own inputs or wiring: `BAD-INPUT`,
  `CARD-CONFIGURED-BUT-MISSING`, `CLOSE-TOKEN`, `SCHEMA`, `TIMEOUT`, `GATE-ERROR`. These are
  attention spent on the harness, not on the work. This is the number the thesis is exposed to.
- **Decided by the maintainer, 2026-08-25, before the first card:** `INDEX-FLAGS` counts as
  **signal** — it fires on assume-unchanged/skip-worktree flags whose effect is to hide mutations
  from the receipt's binding, which is the gate doing its designed job on the tree. `GIT-ERROR`
  counts as **friction** — its triggers (card directory outside a git repo, `git` itself failing
  before or after verify) say nothing about the work; the developer's next action is plumbing, not
  the task. The tie-breaker, recorded so it binds later disputes: ambiguity resolves *against* the
  thesis, because the pre-registration author is also the thesis author — misclassifying friction
  as signal could produce a false survival, which is the expensive error.

**Abandoned cards are measured too.** A card written, worked, and never closed leaves no receipt
and would silently vanish from a receipt-only dataset — which would bias the pilot toward exactly
the cards the harness handled well. One row per abandonment: `tier`, `t0`, date abandoned, and a
one-line reason.

---

## 2. The pre-registered stopping rule

The rule below is a **refutation rule**, not a success criterion. Nothing in this document defines
what "the harness worked" would look like, because a pilot of this shape cannot establish that
(§5). It defines only what would make the maintainer stop and say the thesis did not survive
contact with a real repository.

### Window

The rule is evaluated once, when **`30` cards have closed**, of which at least
**`10` are S2** — or when **`90` days** have passed since the first
closed card, whichever comes first. If the window closes with fewer than `10` S2
cards, the pilot reports **INCONCLUSIVE on attention cost** and reports nothing else. It does not
extend the window to reach a number it likes; extending the window after seeing the data is how a
pre-registration becomes a story.

The qualifying count is S2 specifically, not S2-or-S3. The headline trigger below is computed on
S2 cards alone, so a window that qualified on `20` S1 + `10` S3 cards would have licensed a
non-refutation with an undefined headline median — the protocol would have permitted a result
without evaluating its own metric. Amended 2026-09-02 from "S2 or S3", before the first pilot card.
T3's denominator is unchanged: it is stated on S2/S3 and is evaluated on whatever S2/S3 cards the
window holds.

### Headline trigger

> **The thesis is refuted if the median `minutes_close_loop` on S2 cards exceeds
> `10` minutes, or if friction BLOCKs per closed S2 card exceed a median of
> `1`.**

*Rationale for the default.* The thesis claims the common path costs one card, one `verify`, and a
receipt. If that is true, the close loop is: write `CARD.close`, wait for the verify the developer
had already been running anyway, read one line of gate output. Ten minutes is roughly the point
where that stops being a punctuation mark on the work and becomes a task of its own — long enough
to absorb one honest retry (a red verify caught at close is the gate working, and it is *supposed*
to cost something), short enough that a second and third retry breaks it. The paired BLOCK
threshold exists because the median minute count can stay low while a minority of closes turn into
fights: a median of more than one *friction* BLOCK per card means the typical close is being
refused for reasons that have nothing to do with whether the work is done, which is the precise
failure mode the README invites people to file as a bug in Omama. Both halves are set on S2
deliberately — S1 is the path the design was optimized for and would flatter it, S3 is rare enough
that its median will be noise at this sample size. These numbers were ratified by the maintainer on
2026-08-25, before the first pilot card, after the rationale above was argued and accepted.

### Secondary triggers (each independently sufficient)

Any one of these firing counts as refutation of the thesis as stated, and stops the pilot:

- **T2 — the self-test is being skipped.** `self_test_skipped = y` on more than
  `20%` of closed cards. The install self-test (red AND green) is the one step the
  adoption docs call mandatory. If the people who wrote the harness skip it, the harness is not the
  least harness that holds — it is the least harness that gets held.
- **T3 — tier semantics are not carrying weight.** `tier_dispute = y` on more than
  `25%` of S2/S3 cards. Rigor bought by tier only works if the tier is legible; a quarter
  of cards being re-tiered means the ladder is being negotiated per task, which is the ritual the
  design set out to avoid.
- **T4 — the harness is what fails the card.** `close_reason_class = harness` on more than
  `15%` of FAILED/UNVERIFIED closes. Honest closes are cheap and expected; honest closes
  *caused by the toolkit* are the thesis failing out loud.
- **T5 — abandonment.** More than `25%` of cards written are abandoned without a
  receipt. A loop people leave rather than close is refuted by revealed preference, and this
  trigger is the one that catches the failure the other four would miss, because abandoned cards
  contribute no minutes and no BLOCKs.

### What does NOT count as refutation

Signal BLOCKs at any rate. A high `VERIFY-RED` count means the gate is catching unbacked closes;
reading that as friction would define the piece's success as its failure. Likewise, S3 review
artifacts costing real time is the design working as documented, not evidence against it.

### What a non-refutation is worth

If no trigger fires, the correct statement is: **"in one repository, with one developer dispatching agent executors, over
`30` cards, no pre-registered refutation trigger fired."** That is the whole claim. It is
not "this works", it is not "the harness pays for itself", and no stronger sentence should appear
in this repository's README or anywhere else on the strength of this pilot.

---

## 3. How receipts are collected (they are local, and gitignored by policy)

`CARD.yaml`, `CARD.close`, `CARD.receipt.json` and `*.receipt.json` are gitignored in the adopting
repository by policy: a card is per task and per machine, and a committed receipt would carry the
hash of a tree that the committing commit itself changes. So the pilot cannot collect data by
reading the repository's history. Two routes, both required:

**(a) The durable record of a close — pasted into the PR body.** The verify command, its exit code,
the receipt's `rev` and `verdict`, under a fixed heading so it can be found later:

```
## Receipt
command: <the card's verify, verbatim>
exit:    0
verdict: VERIFIED
rev:     <rev from CARD.receipt.json>
tier:    S2
```

This is what keeps VERIFIED from being a local-only claim; the pilot reads tier, verdict and rev
off it. `rev`/`patch_id`/`diff_sha` are recomputable only on the same checkout while the tree still
exists — never cross-machine — so the pasted block is a record, not a portable proof, and it is
recorded as such.

**(b) A one-command export at close time, appending one line to a local log.** Run in the card
directory, immediately after the gate writes the receipt (`py -3` on Windows). VERIFIED 2026-09-02:
this command was executed against a sample card and a FAILED receipt and exited 0, appending the
row shown below; the refusal paths (offset-naive timestamp; missing or misplaced
`close_reason_class`) were each executed and exited 1 without appending a row:

```
python3 -c "import json,sys,yaml,os;from datetime import datetime as D;c=yaml.safe_load(open('CARD.yaml',encoding='utf-8'));r=json.load(open('CARD.receipt.json',encoding='utf-8'));a=(sys.argv+['']*6)[1:7];P=lambda s:(lambda d:d if d.utcoffset() is not None else sys.exit('REFUSED: timestamp without UTC offset (write 2026-08-23T09:12+00:00, not 2026-08-23T09:12): '+s))(D.fromisoformat(s)) if s else None;t0,t1,t2=P(a[0]),P(a[1]),P(r['timestamp']);M=lambda x,y:round((y-x).total_seconds()/60,1) if x and y else None;v=r.get('verdict');k=a[5];(v!='VERIFIED')!=(k in('work','harness','external')) and sys.exit('REFUSED: close_reason_class must be work|harness|external on FAILED/UNVERIFIED and empty on VERIFIED; got verdict=%s class=%r'%(v,k));row={'card':os.path.basename(os.getcwd()),'tier':c.get('tier'),'task_type':c.get('task_type'),'verdict':v,'exit':r.get('exit'),'rev':r.get('rev'),'command':r.get('command'),'timestamp':r.get('timestamp'),'t0':a[0],'t1':a[1],'minutes_card_to_receipt':M(t0,t2),'minutes_close_loop':M(t1,t2),'blocks':[b for b in a[2].split(',') if b],'self_test_skipped':a[3],'tier_dispute':a[4],'close_reason':r.get('reason'),'close_reason_class':k or None};p=os.environ.get('PILOT_LOG') or os.path.join(os.path.expanduser('~'),'PILOT-LOG.jsonl');open(p,'a',encoding='utf-8').write(json.dumps(row)+chr(10));print(json.dumps(row))" <t0> <t1> <BLOCK,BLOCK> <y|n> <y|n> <work|harness|external|>
```

```json
{"card": "…", "tier": "S2", "task_type": "implementation", "verdict": "FAILED", "exit": 1,
 "rev": "abc123def456", "command": "…", "timestamp": "2026-08-23T10:00:00+00:00",
 "t0": "2026-08-23T09:12+00:00", "t1": "2026-08-23T09:51+00:00",
 "minutes_card_to_receipt": 48.0, "minutes_close_loop": 9.0,
 "blocks": ["SCHEMA", "VERIFY-RED"], "self_test_skipped": "n", "tier_dispute": "y",
 "close_reason": "verify exited 1", "close_reason_class": "harness"}
```

The hand-supplied arguments are the fields no file carries: the two timestamps, the BLOCK reasons
seen during this card, the two yes/no answers, and — on a FAILED or UNVERIFIED close only — the
`close_reason_class`. **A field that was not observed is left empty. It is never estimated after
the fact** — an invented minute count would make every median in §2 a fiction, and the stopping
rule would then be testing the log, not the harness. Two fields are the exception, because leaving
them empty would not be honest absence but a broken row, and the command refuses rather than
appends:

- `t0` and `t1`, when given, must carry an explicit UTC offset (`+00:00`, not `Z` — Python 3.8's
  `fromisoformat` accepts the former only). The receipt's `timestamp` is always offset-aware, and
  subtracting a naive value from it either raises or, in a lenient parser, silently shifts both
  durations by the machine's zone. Empty `t0`/`t1` is still allowed and yields `null` minutes: not
  observed, not invented.
- `close_reason_class` must be one of `work` · `harness` · `external` when the verdict is FAILED or
  UNVERIFIED, and must be empty when it is VERIFIED. T4 is computed on this field; a FAILED row
  without it cannot be classified later, because the next card at the same root overwrites the
  receipt (see below), and §6 says the classification is made at close and never revised.

**Where the row goes.** The command appends to `PILOT-LOG.jsonl` **in the developer's home
directory** (`~/PILOT-LOG.jsonl`), or to the path in `$PILOT_LOG` if set — never to a path relative
to the card directory. Parallel cards belong to separate worktrees by design (§6), so a relative
sink would have produced one log per worktree, with rows omitted from consolidation or deleted with
a removed worktree. One developer, one sink, regardless of how many worktrees the cards ran in. The
the logs of every machine the developer used are concatenated at the end of the window; no shared file, no merge conflict,
and no ordering assumption in the analysis.

**Run the export at close time or lose the row.** The gate consumes `CARD.close` on every allowed
close, and the next card at the same root overwrites `CARD.receipt.json`. Nothing recovers a row
afterwards. That is a real cost of the local-receipt policy and it is stated here rather than
discovered at week six.

---

## 4. Where the pilot runs

**An internal one-developer repository.** One developer — the maintainer — dispatching agent executors, one repository, one stack. The repository
adopts the LOOP as documented — `work-order` at the root, the gate wired into that repository's own
`.claude/settings.json` (per-repo, with the mandatory install self-test), output-discipline's
templates for plans and reviews — not loose pieces. Passive layers (privacy-hook, protect-tests)
are installed alongside and are outside the measured per-task surface.

No further identifying detail about the repository, its owner, its domain, or the developers
appears in this document or in any published result, and none is carried in the pilot log: the
export above records the card directory name, and if a card directory name would identify anything,
it is renamed before the log is shared. This is the same sanitize invariant the rest of this public
repository is held to.

---

## 5. What this pilot cannot show

Stated up front so it cannot be quietly dropped from the write-up:

- **No control group.** Nothing here observes the same tasks done without the harness. The
  counterfactual — what these closes would have cost, or what would have shipped broken — is not
  measured and cannot be inferred. No comparative claim ("faster than", "safer than", "cheaper
  than") is available from this design at any sample size.
- **The prevented failure is unobservable.** The thesis weighs a piece's attention cost against
  *the failure it prevents*. The pilot measures only the first term. A trigger firing shows the
  cost was high; no result shows the prevented failures were few, and no result shows they were
  many.
- **One developer, and it is the maintainer.** The author of the harness is its only human user in
  this pilot: self-selection at the maximum, no second reader of any card, tier, or close, and it
  biases every number toward the harness. Habit, tooling fluency, and vocabulary are confounded
  with the design throughout. The asymmetry cuts one way: a non-refutation from the author's own
  use is worth close to nothing; a refutation from it is the most credible result this pilot can
  produce. Throughput is also one person's — the `30`-card window is reachable inside `90` days
  only if the cadence holds, so INCONCLUSIVE is the likeliest outcome, and an extension "with more
  developers" means recruiting one.
- **One repository.** One stack, one review culture, one branching model, one CI. Nothing here
  generalizes to a repository with more developers at different rhythms — which the motivating
  issue names as exactly where S2/S3 cost is expected to show up. A two-developer repository is the
  *easiest* case for tier disputes and review artifacts, not a representative one.
- **Small N, unstable medians.** At `30` cards with `10` at S2/S3, a single
  bad week moves a median. No confidence interval is reported because none would be meaningful; the
  triggers are deliberately coarse for the same reason.
- **Elapsed time is not attention.** Both intervals measure wall clock, including interruptions,
  meetings and lunch. `minutes_close_loop` is narrower but still not a measure of cognitive load.
- **Windows-primary.** The pilot exercises the environment this toolkit is developed on. POSIX
  behavior is covered by CI, not by this pilot.
- **The pilot cannot refute the pieces individually.** The LOOP is adopted whole; a trigger firing
  indicts the loop as configured, not `work-order` or `receipt-gate` or `output-discipline` in
  isolation.

---

## 6. Known measurement gaps (this document's own residual)

In the style every other README here follows — what this measurement does NOT catch:

- **BLOCK counts are hand-recorded.** The gate names its BLOCK on stderr and writes no file; a
  blocked close deletes any receipt. So `blocks` depends on the developer noticing and typing it.
  Undercounting is the likely direction, and it undercounts the friction side — the side that could
  refute the thesis. Route that would close it: tee the gate's stderr to a local append-only file
  from the registered hook command. Not done here; the card that produced this document adds no
  hooks or validators.
- **`t0` and `t1` are mtimes or memory.** An edited card updates its mtime; a re-attempted close
  rewrites `CARD.close`. "First write" is a discipline, not a mechanism.
- **`close_reason_class` and `tier_dispute` are judgments** made by the same people whose approach
  is under test. Both should be recorded at close, before any analysis, and never revised.
- **Only one card can be active per root**, so the pilot cannot observe two concurrent cards in the
  same worktree — by design, parallel sessions belong to separate worktrees.

---

## 7. Pre-registration checklist (do all of this before the first pilot card)

1. ~~Replace every placeholder with a chosen value~~ — done 2026-08-25; no placeholder remains
   in this document.
2. ~~Classify `GIT-ERROR` and `INDEX-FLAGS` as friction or signal, in writing, in §1~~ — done
   2026-08-25 (`INDEX-FLAGS` → signal, `GIT-ERROR` → friction, rationale in §1).
3. Commit this file with a date, and record the commit rev. The rev is what makes the numbers
   pre-registered rather than remembered.
4. Add `PILOT-LOG.jsonl` to the adopting repository's `.gitignore` alongside the card family
   anyway — the export writes outside every worktree by default, but a `$PILOT_LOG` pointed inside
   the repository must not become a committed file.
5. Run the receipt-gate install self-test (red AND green) on every machine the developer uses, and record
   that date — it is the baseline `self_test_skipped = n` depends on. Record, on the same date and
   per machine, the output of `receipt-gate/adapt/check_wiring.py` (`WIRING-OK` and the command it
   certified): a self-test run once does not survive a later wiring change, and a Stop hook that
   is absent does not announce itself.
6. Commit in advance, in writing and dated, that the write-up gets published whichever way the
   triggers land. With one developer this is a commitment device, not an agreement — and it is the
   only thing that makes the stopping rule a rule. A refutation that only gets written down if it
   is flattering is not a stopping rule.
7. Record the harness version the adopting repository runs — the upstream `omama` rev in its
   provenance note — at start. Any change during the window to a measured piece (the validator,
   the gate, the card schema) is recorded as a dated harness-version change next to the log. A
   harness change is not a protocol change and does not void the registration; an unrecorded one
   makes `close_reason_class = harness` uninterpretable, because the harness that failed the card
   would not be identifiable.
