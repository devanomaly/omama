#!/usr/bin/env python3
"""receipt_gate.py -- the receipt gate: a Claude Code Stop hook that, when a
close is DECLARED, re-runs the active card's `verify` against the current
tree, binds the result to that tree (hash material before/after), writes a
receipt, and blocks the stop unless the close is VERIFIED (green + fresh) or
honestly declared FAILED/UNVERIFIED. Only this gate emits VERIFIED; an
unbacked VERIFIED cannot be produced through a close.

Exit contract (empirically pinned on Claude Code 2.1.236 -- fixture/spike/):
  0 -> allow the stop (NO-CARD, WIP turn, honest close, VERIFIED close)
  2 -> BLOCK the stop; stderr (the named reason) is fed back to the model
  anything else -> would NOT block, which is why the entire body runs inside
  one guard from line 1: any uncaught exception exits 2, named, never 1.

Close protocol (CARD.close, sibling of the card):
  CLOSE                 -> close intends VERIFIED: schema + verify + freshness
                           (+ S3 review) must all hold.
  FAILED: <reason>      -> honest close; ALWAYS allowed (degrades, never
                           crashes: unreadable/weird card files become named
                           sentinels, git failures null the hash fields).
  UNVERIFIED: <reason>  -> honest close; same.
  (absent)              -> work-in-progress turn: warn, exit 0, verify nothing.
The gate CONSUMES CARD.close on every allowed close; the durable record is
the receipt, CARD.receipt.json:
  {command, exit, verdict, reason?, rev, patch_id, diff_sha, diff_hash,
   timestamp}
A VERIFIED receipt always carries non-null rev/patch_id/diff_sha -- the gate
BLOCKS rather than write a VERIFIED with a null or unverifiable hash field.
rev+patch_id+diff_sha are recomputable on the same checkout while the tree
stands (never cross-machine), via the exact pinned diff command below, which
EXCLUDES the receipt path itself so the gate's own write never poisons
recomputation (even when the receipt is git-tracked).

Single-read discipline (TOCTOU): the card, CARD.close and CARD.review.md are
read ONCE at the start of a close attempt; every decision (verify command,
tier, review verdict) is made on those exact bytes, H1 hashes those exact
bytes, and H2 re-reads fresh -- so any mid-attempt swap lands in
UNEXPECTED-CHANGE instead of splitting decisions across two versions. The
review is re-read and compared once more after the S3 checks (the checker
subprocess reads the file itself).

Named block reasons: BAD-INPUT, CARD-CONFIGURED-BUT-MISSING, CLOSE-TOKEN,
SCHEMA, GIT-ERROR, INDEX-FLAGS, UNEXPECTED-CHANGE, VERIFY-RED, TIMEOUT,
S3-REVIEW, GATE-ERROR.

Honest boundaries (README carries the full list): a receipt forged on a WIP
turn persists (pinned KNOWN-LIMITATION); non-git mutate-and-restore inside
verify is invisible to endpoint hashing; reflog scrubbing and .git-internal
evasions are named residuals; a blocked close whose planted receipt is HELD
OPEN by a straggler process cannot be deleted -- the block message then warns
loudly that any standing receipt is untrusted.
"""
import sys


def _ascii_safe():
    # cp1252 consoles must never crash the gate into a non-2 exit; localized
    # tool output (taskkill) flows through this too.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass


class Block(Exception):
    def __init__(self, name, msg):
        super().__init__(msg)
        self.name = name
        self.msg = msg


class GitError(Exception):
    pass


class VerifyTimeout(Exception):
    def __init__(self, output):
        super().__init__("verify timed out")
        self.output = output


def main(state):
    import hashlib
    import json
    import os
    import re
    import subprocess
    from datetime import datetime, timezone
    from pathlib import Path

    # ---------------------------------------------------------------- input
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else None
    except Exception:
        payload = None
    if payload is None or not isinstance(payload, dict):
        raise Block("BAD-INPUT",
                    "Stop-hook stdin was empty or unparseable; a card's "
                    "presence cannot be ruled out, so the stop is blocked. "
                    "Fix the hook wiring (see adapt/README.md).")
    cwd = payload.get("cwd") or os.getcwd()  # spike: payload carries cwd

    def run_git(repo, args, ok_codes=(0,), binary=False, input_bytes=None):
        try:
            r = subprocess.run(
                ["git", "-C", str(repo)] + args,
                capture_output=True, text=not binary, input=input_bytes,
                **({} if binary else {"encoding": "utf-8", "errors": "replace"}))
        except FileNotFoundError:
            raise GitError("git is not available on PATH")
        if r.returncode not in ok_codes:
            err = r.stderr if not binary else r.stderr.decode("utf-8", "replace")
            raise GitError(f"git {args[0]} exited {r.returncode}: {err.strip()[:300]}")
        return r.returncode, (r.stdout if not binary else r.stdout)

    def toplevel(path):
        try:
            _, out = run_git(path, ["rev-parse", "--show-toplevel"])
            return Path(out.strip())
        except (GitError, OSError):
            return None

    # ------------------------------------------------------ card resolution
    env_card = os.environ.get("OMAMA_CARD", "").strip()
    if env_card:
        card = Path(env_card)
        if not card.exists():
            raise Block("CARD-CONFIGURED-BUT-MISSING",
                        f"OMAMA_CARD points at {card} which does not exist. "
                        "Fix the path or unset OMAMA_CARD.")
    else:
        top = toplevel(cwd) or Path(cwd)
        card = top / "CARD.yaml"
        if not card.exists():
            orphan = top / "CARD.close"
            extra = (f" NOTE: an orphaned CARD.close exists at {orphan} -- it "
                     "will fire a close attempt against any future card here; "
                     "delete it if stale." if orphan.exists() else "")
            print(f"NO-CARD: stop permitted, nothing verified "
                  f"(no CARD.yaml at {top}).{extra}")
            return 0

    card_dir = card.parent
    close_path = card_dir / "CARD.close"
    review_path = card_dir / "CARD.review.md"
    receipt_path = card_dir / "CARD.receipt.json"
    card_repo = toplevel(card_dir)  # None => non-git card dir (degraded honest)

    session_top = toplevel(cwd)
    if card_repo and session_top and card_repo != session_top:
        print(f"WARNING: card repo ({card_repo}) is not the session repo "
              f"({session_top}); a VERIFIED close attests the card's repo, "
              "the session's own repo stops unbound.")

    # ------------------------------------------------------- hash material
    PIN = ["-c", "core.quotepath=false", "-c", "diff.noprefix=false",
           "-c", "diff.mnemonicPrefix=false", "-c", "diff.interHunkContext=0"]

    def sha(b):
        return hashlib.sha256(b).hexdigest()

    def receipt_rel(repo):
        try:
            return receipt_path.resolve().relative_to(
                Path(repo).resolve()).as_posix()
        except (ValueError, OSError):
            return None

    def pinned_diff(repo):
        """The single-sourced diff command (hash material AND diff_sha).
        The receipt path is pathspec-EXCLUDED so the gate's own write --
        including a git-TRACKED receipt's delete/recreate cycle -- never
        enters the diff, keeping diff_sha recomputable post-close."""
        args = PIN + ["diff", "--no-ext-diff", "--no-color", "--no-textconv",
                      "-U3", "HEAD"]
        rel = receipt_rel(repo)
        if rel:
            args += ["--", ".", f":(exclude){rel}"]
        _, out = run_git(repo, args, binary=True)
        return out

    def read_family(p):
        """('sha', hexdigest, bytes) | ('absent',) | ('unreadable', typename).
        Never raises: an unreadable family file is a named sentinel, so an
        honest close can always complete (its H-mismatch consequences land
        in UNEXPECTED-CHANGE on VERIFIED-intent, never in a crash)."""
        try:
            b = p.read_bytes()
            return ("sha", sha(b), b)
        except FileNotFoundError:
            return ("absent", None, None)
        except OSError as e:
            return ("unreadable:" + type(e).__name__, None, None)

    def family_token(entry):
        kind = entry[0]
        return entry[1] if kind == "sha" else kind

    def material(repo, preread=None):
        """(digest, comps, diff_bytes). Any git failure raises GitError.
        preread maps family labels to read_family() entries captured at
        attempt start -- H1 hashes the exact bytes decisions were made on;
        H2 (no preread) re-reads fresh so mid-attempt swaps are caught."""
        comps = {}
        _, rev = run_git(repo, ["rev-parse", "HEAD"])
        comps["rev"] = rev.strip()
        diff_bytes = pinned_diff(repo)
        comps["diff_sha"] = sha(diff_bytes)
        _, status = run_git(repo, ["status", "--porcelain",
                                   "--untracked-files=all"])
        rel = receipt_rel(repo)
        untracked = []
        for ln in status.splitlines():
            if not ln.startswith("??"):
                continue
            name = ln[3:].strip().strip('"')
            if rel and name == rel:
                continue  # the gate's own output: excluded entirely
            untracked.append(name)
        comps["untracked"] = "\n".join(sorted(untracked))
        _, reflog = run_git(repo, ["reflog", "--format=%H %gs"])
        if not reflog.strip():
            print("WARNING: empty HEAD reflog -- the stash/checkout tripwire "
                  "is degraded on this repo (core.logAllRefUpdates off?).")
        comps["reflog"] = reflog
        rc, stash = run_git(repo, ["rev-parse", "--verify", "refs/stash"],
                            ok_codes=(0, 1, 128))
        comps["stash"] = stash.strip() if rc == 0 else "none"
        _, lsf = run_git(repo, ["ls-files", "-v"])
        comps["index_flags"] = "\n".join(
            sorted(ln for ln in lsf.splitlines() if not ln.startswith("H ")))
        for label, p in (("card", card), ("close", close_path),
                         ("review", review_path)):
            if preread and label in preread:
                comps[f"file:{label}"] = family_token(preread[label])
            else:
                comps[f"file:{label}"] = family_token(read_family(p))
        digest = sha(json.dumps(comps, sort_keys=True).encode("utf-8"))
        return digest, comps, diff_bytes

    # ----------------------------------------------------------- verify run
    def run_verify(cmd, repo, timeout):
        kw = {}
        if os.name != "nt":
            kw["start_new_session"] = True  # own process group => killpg
        proc = subprocess.Popen(cmd, shell=True, cwd=str(repo),
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace",
                                **kw)
        try:
            out, _ = proc.communicate(timeout=timeout)
            return proc.returncode, out or ""
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                taskkill = os.path.join(os.environ.get("SystemRoot",
                                                       r"C:\Windows"),
                                        "System32", "taskkill.exe")
                subprocess.run([taskkill, "/T", "/F", "/PID", str(proc.pid)],
                               capture_output=True)
            else:
                import signal
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError, OSError):
                    proc.kill()
            try:
                out, _ = proc.communicate(timeout=10)
            except Exception:
                out = ""
            raise VerifyTimeout(out or "")

    def get_timeout():
        """(seconds, error_note|None). Malformed OMAMA_VERIFY_TIMEOUT must
        never crash an honest close; VERIFIED-intent blocks on it, NAMED."""
        val = os.environ.get("OMAMA_VERIFY_TIMEOUT", "").strip()
        if not val:
            return 600.0, None
        try:
            return float(val), None
        except ValueError:
            return 600.0, (f"OMAMA_VERIFY_TIMEOUT={val!r} is not a number "
                           "(seconds); using/requiring the 600s default")

    # -------------------------------------------------------------- helpers
    HERE = Path(__file__).resolve().parent

    def validator_check():
        """(ok: bool, note: str, output: str) -- schema state of the card."""
        vpath = os.environ.get("OMAMA_VALIDATOR", "").strip() or str(
            HERE.parent / "work-order" / "validate_work_order.py")
        if not Path(vpath).exists():
            return False, (f"schema: validator unrunnable (missing at {vpath}"
                           " -- set OMAMA_VALIDATOR; see adapt/README.md)"), ""
        try:
            r = subprocess.run([sys.executable, vpath, str(card)],
                               capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=60)
        except Exception as e:  # noqa: BLE001 -- unrunnable is a named state
            return False, f"schema: validator unrunnable ({type(e).__name__})", ""
        out = (r.stdout or "") + (r.stderr or "")
        if r.returncode == 0:
            return True, "schema: ok", out
        return False, f"schema: red (validator exit {r.returncode})", out

    def parse_card(card_entry):
        """(doc|None, note|None) from the PREREAD card bytes -- decisions and
        H1 see the same bytes. Never raises for card-shaped problems."""
        kind = card_entry[0]
        if kind == "absent":
            return None, "card: vanished before the close attempt"
        if kind != "sha":
            return None, f"card: {kind}"
        try:
            text = card_entry[2].decode("utf-8")
        except UnicodeDecodeError:
            return None, "card: undecodable (not UTF-8)"
        try:
            import yaml
            doc = yaml.safe_load(text)
        except ImportError:
            raise  # dependency failure is a GATE-ERROR, not a card shape
        except Exception as e:  # noqa: BLE001 -- any parse failure is a shape
            return None, f"card: unparseable YAML ({type(e).__name__})"
        if not isinstance(doc, dict):
            return None, f"card: root is {type(doc).__name__}, not a mapping"
        return doc, None

    def extract_verify(doc, parse_note):
        """Positive extraction rule: verify is extractable iff the parsed
        root is a mapping and root['verify'] is a non-empty-stripped string;
        EVERY other outcome -> (None, note)."""
        if doc is None:
            return None, parse_note
        v = doc.get("verify")
        if not (isinstance(v, str) and v.strip()):
            return None, f"card: verify absent or not a non-empty string ({v!r})"
        return v.strip(), None

    def compute_patch_id(diff_bytes, strict):
        """patch_id from the SAME diff bytes the material hashed (no
        re-read). strict (VERIFIED): any failure raises Block -- the gate
        never writes a VERIFIED whose recomputable fields it could not
        actually compute. Lenient (honest): failure -> None."""
        if diff_bytes is None:
            if strict:
                raise Block("GATE-ERROR",
                            "no diff bytes available for patch_id on a "
                            "VERIFIED close (fail-closed)")
            return None
        if diff_bytes == b"":
            return "empty-diff"
        try:
            r = subprocess.run(["git", "-C", str(card_repo), "patch-id",
                                "--stable"], input=diff_bytes,
                               capture_output=True, timeout=60)
        except Exception as e:  # noqa: BLE001 -- named handling below
            if strict:
                raise Block("GATE-ERROR",
                            f"git patch-id failed on a VERIFIED close "
                            f"({type(e).__name__}) -- fail-closed")
            return None
        out = r.stdout.decode("utf-8", "replace").strip()
        if r.returncode != 0 or not out:
            if strict:
                raise Block("GATE-ERROR",
                            f"git patch-id exited {r.returncode} with "
                            f"{'no' if not out else 'some'} output on a "
                            "non-empty diff -- fail-closed on VERIFIED")
            return None
        return out.split()[0]

    def write_receipt(command, exit_code, verdict, reason, comps, diff_bytes):
        strict = verdict == "VERIFIED"
        rec = {"command": command, "exit": exit_code, "verdict": verdict}
        if reason is not None:
            rec["reason"] = reason
        rec["rev"] = comps["rev"] if comps else None
        rec["patch_id"] = compute_patch_id(diff_bytes, strict) if comps else None
        rec["diff_sha"] = comps["diff_sha"] if comps else None
        rec["diff_hash"] = state.get("h2_digest")
        rec["timestamp"] = datetime.now(timezone.utc).isoformat()
        receipt_path.write_text(json.dumps(rec, indent=1), encoding="utf-8")
        print(json.dumps({"gate": "receipt-gate", "verdict": verdict,
                          "card": str(card), "exit": exit_code,
                          "rev": rec["rev"]}))
        return rec

    HATCH = ('fix and re-close, or declare an honest FAILED in CARD.close '
             '("FAILED: <reason>")')

    # -------------------------------------------------------------- WIP turn
    if not close_path.exists():
        echo = ""
        try:
            rec = json.loads(receipt_path.read_text(encoding="utf-8"))
            echo = (f' receipt: {rec.get("verdict")} @ {rec.get("rev")} '
                    f'{rec.get("timestamp")}')
            if card_repo:
                try:
                    _, cur_rev = run_git(card_repo, ["rev-parse", "HEAD"])
                    cur_diff_sha = sha(pinned_diff(card_repo))
                    if (cur_rev.strip() != rec.get("rev")
                            or cur_diff_sha != rec.get("diff_sha")):
                        echo += ", tree has moved since"
                except GitError:
                    pass
        except FileNotFoundError:
            pass
        except Exception:  # noqa: BLE001 -- echo is optional, never blocks
            echo = " receipt: present but unreadable"
        print(f"WIP: card active ({card}), no close declared -- nothing "
              f"verified this turn.{echo}")
        return 0

    # ------------------------------------------------- close attempt begins
    state["close_in_progress"] = True
    state["receipt_path"] = str(receipt_path)
    if receipt_path.exists():
        receipt_path.unlink()  # failure -> guard -> exit 2 (fail-closed)

    # Single-read discipline: capture the family bytes every decision and H1
    # will use. H2 re-reads fresh; a mid-attempt swap => UNEXPECTED-CHANGE.
    preread = {"card": read_family(card),
               "close": read_family(close_path),
               "review": read_family(review_path)}

    close_entry = preread["close"]
    if close_entry[0] != "sha":
        raise Block("CLOSE-TOKEN",
                    f"CARD.close is {close_entry[0]}; prior receipt (if any) "
                    "was superseded and deleted.")
    try:
        token = close_entry[2].decode("utf-8").strip()
    except UnicodeDecodeError:
        raise Block("CLOSE-TOKEN",
                    "CARD.close is undecodable (not UTF-8); prior receipt "
                    "(if any) was superseded and deleted.")

    honest_verdict = reason = None
    if token == "CLOSE":
        pass
    else:
        for word in ("FAILED", "UNVERIFIED"):
            if token.upper().startswith(word + ":"):
                candidate = token[len(word) + 1:].strip()
                if candidate:
                    honest_verdict, reason = word, candidate
                break
        if honest_verdict is None:
            raise Block("CLOSE-TOKEN",
                        f"CARD.close contains {token[:80]!r}; expected CLOSE, "
                        '"FAILED: <reason>" or "UNVERIFIED: <reason>" -- the '
                        "reason is required (audit trail for the ratifying "
                        "operator). Prior receipt, if any, was superseded and "
                        "deleted.")

    timeout, timeout_note = get_timeout()
    doc, parse_note = parse_card(preread["card"])
    command, shape_note = extract_verify(doc, parse_note)

    # ------------------------------------------------------------ honest close
    if honest_verdict:
        notes = [reason]
        ok_schema, schema_note, _ = validator_check()
        if not ok_schema:
            notes.append(schema_note)
        if shape_note:
            notes.append(shape_note)
        if timeout_note:
            notes.append(timeout_note)
        v_exit = None
        if command:
            run_dir = card_repo or card_dir
            try:
                v_exit, _ = run_verify(command, run_dir, timeout)
            except VerifyTimeout:
                v_exit = -1
                notes.append(f"verify: TIMEOUT after {timeout}s (exit is a "
                             "sentinel; the named reason is authoritative)")
        comps = diff_bytes = None
        if card_repo:
            try:
                digest, comps, diff_bytes = material(card_repo)
                state["h2_digest"] = digest
            except GitError as e:
                notes.append(f"git: degraded, hash fields null ({e})")
        else:
            notes.append("git: degraded, hash fields null (card dir is not "
                         "a git repo)")
        write_receipt(command, v_exit, honest_verdict, "; ".join(notes),
                      comps, diff_bytes)
        close_path.unlink()
        print(f"CLOSE: {honest_verdict} (honest) -- receipt written, "
              "CARD.close consumed. Not a VERIFIED close.")
        return 0

    # --------------------------------------------------------- VERIFIED intent
    if timeout_note:
        raise Block("GATE-ERROR",
                    f"{timeout_note} -- close intends VERIFIED, so a broken "
                    "timeout knob blocks (fix or unset OMAMA_VERIFY_TIMEOUT). "
                    f"{HATCH}")
    ok_schema, schema_note, schema_out = validator_check()
    if not ok_schema:
        raise Block("SCHEMA",
                    f"close intends VERIFIED but the card is not trustable "
                    f"({schema_note}).\n{schema_out.strip()[:1500]}\n{HATCH}")
    if not card_repo:
        raise Block("GIT-ERROR",
                    "close intends VERIFIED but the card's directory is not "
                    f"inside a git repo ({card_dir}); the binding the receipt "
                    f"exists for is impossible. {HATCH}")
    if command is None:
        raise Block("SCHEMA", f"verify not extractable ({shape_note}). {HATCH}")

    try:
        h1_digest, h1, _ = material(card_repo, preread=preread)
    except GitError as e:
        raise Block("GIT-ERROR", f"hash material failed before verify: {e}. "
                                 f"{HATCH}")
    if h1["index_flags"]:
        raise Block("INDEX-FLAGS",
                    "close intends VERIFIED but these paths carry "
                    "assume-unchanged/skip-worktree flags, which hide "
                    "mutations from the binding:\n"
                    f"{h1['index_flags']}\n"
                    "Clear them (git update-index --no-assume-unchanged / "
                    f"--no-skip-worktree <path>) and re-close. {HATCH}")

    try:
        v_exit, v_out = run_verify(command, card_repo, timeout)
    except VerifyTimeout as t:
        tail = t.output.strip()[-800:]
        raise Block("TIMEOUT",
                    f"verify did not finish within {timeout}s (process tree "
                    f"killed; sentinel exit -1).\n{tail}\n{HATCH}")

    try:
        h2_digest, h2, h2_diff = material(card_repo)
    except GitError as e:
        raise Block("GIT-ERROR", f"hash material failed after verify: {e}. "
                                 f"{HATCH}")
    state["h2_digest"] = h2_digest

    if h1_digest != h2_digest:
        changed = sorted(k for k in h1 if h1.get(k) != h2.get(k))
        detail = []
        if "untracked" in changed:
            before = set(h1["untracked"].splitlines())
            after = set(h2["untracked"].splitlines())
            added, removed = sorted(after - before), sorted(before - after)
            if added:
                detail.append("new untracked names: " + ", ".join(added))
            if removed:
                detail.append("removed untracked names: " + ", ".join(removed))
            detail.append("remediation: gitignore run-unique artifacts and "
                          "re-close (a .gitignore edit between attempts "
                          "exits the loop in one edit, no commit needed)")
        raise Block("UNEXPECTED-CHANGE",
                    "the tree changed while verify ran; the green (if any) "
                    "applies to a tree that no longer exists. Changed "
                    f"material: {', '.join(changed)}.\n"
                    + "\n".join(detail) + f"\n{HATCH}")

    if v_exit != 0:
        tail = v_out.strip()[-1200:]
        raise Block("VERIFY-RED",
                    f"verify exited {v_exit} on the current tree.\n"
                    f"--- verify output tail ---\n{tail}\n{HATCH}")

    # S3 routing invariant: review pass before a VERIFIED close. Tier and
    # verdict come from the PREREAD bytes (the bytes H1 attested).
    if doc.get("tier") == "S3":
        review_entry = preread["review"]
        if review_entry[0] != "sha":
            raise Block("S3-REVIEW",
                        f"tier S3 requires a review pass before a VERIFIED "
                        f"close: {review_path} is {review_entry[0]}. {HATCH}")
        cpath = os.environ.get("OMAMA_CHECK_ARTIFACT", "").strip() or str(
            HERE.parent / "output-discipline" / "scripts"
            / "check_artifact.py")
        try:
            # CARD-03: 09's line budgets are advisory, not structural --
            # structure violations (missing/buried verdict, missing
            # sections) still fail the checker; over-budget alone must only
            # warn, never block an otherwise-valid S3 close.
            r = subprocess.run([sys.executable, cpath, "--budgets-advisory",
                                str(review_path)],
                               capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=60)
            checker_rc = r.returncode
        except Exception as e:  # noqa: BLE001 -- unlaunchable checker blocks
            raise Block("S3-REVIEW", f"output-discipline checker unlaunchable "
                                     f"({type(e).__name__}) -- set "
                                     f"OMAMA_CHECK_ARTIFACT. {HATCH}")
        if checker_rc != 0:
            raise Block("S3-REVIEW",
                        f"output-discipline checker exited {checker_rc} on "
                        f"the review artifact (0 required).\n"
                        f"{(r.stdout + r.stderr).strip()[:800]}\n{HATCH}")
        # --budgets-advisory demotes over-budget to a WARNING line on stdout
        # and still exits 0 -- do not let a VERIFIED close swallow it, the
        # operator should still see the advisory.
        for ln in r.stdout.splitlines():
            if ln.startswith("WARNING:"):
                print(ln)
        # Verbatim from output-discipline/scripts/check_artifact.py
        # (VERDICT_RE): the \*{0,2} bold handling and trailing \b are
        # load-bearing (killed a "PASSING" false match in 09's history).
        VERDICT_RE = re.compile(
            r"\bVerdict:\*{0,2}\s*(PASS-with-issues|PASS|BLOCK)\b",
            re.IGNORECASE)
        text = review_entry[2].decode("utf-8", "replace")
        no_comments = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
        first3 = [ln for ln in no_comments.splitlines() if ln.strip()][:3]
        verdicts = [m.group(1).upper() for ln in first3
                    for m in VERDICT_RE.finditer(ln)]
        if not verdicts:
            raise Block("S3-REVIEW",
                        "review artifact carries NO verdict in its first 3 "
                        "content lines (a plan-typed artifact passes the "
                        f"checker verdict-free; the gate does not). {HATCH}")
        if len(set(verdicts)) > 1 or verdicts[0] == "BLOCK":
            raise Block("S3-REVIEW",
                        f"review verdict is {verdicts} -- BLOCK or "
                        f"contradictory verdicts do not back a VERIFIED "
                        f"close. {HATCH}")
        # The checker subprocess read the file itself; make sure what it and
        # the regex adjudicated is still the bytes H2 attested.
        post = read_family(review_path)
        if family_token(post) != family_token(review_entry):
            raise Block("UNEXPECTED-CHANGE",
                        "CARD.review.md changed during the S3 checks -- the "
                        f"adjudicated bytes are not the attested bytes. {HATCH}")

    write_receipt(command, v_exit, "VERIFIED", None, h2, h2_diff)
    close_path.unlink()
    print(f"VERIFIED: verify green and fresh on {h2['rev'][:12]} -- receipt "
          "written, CARD.close consumed.")
    return 0


def _cleanup_receipt(state):
    """Best-effort deletion on block exits. Returns True when no receipt
    remains; False means a straggler is holding it open -- the caller warns
    LOUDLY (a silently-surviving plant was a counter-found forgery route)."""
    if not (state.get("close_in_progress") and state.get("receipt_path")):
        return True
    import os
    try:
        if os.path.exists(state["receipt_path"]):
            os.remove(state["receipt_path"])
        return not os.path.exists(state["receipt_path"])
    except Exception:  # noqa: BLE001 -- exit stays 2 either way
        try:
            return not os.path.exists(state["receipt_path"])
        except Exception:  # noqa: BLE001
            return False


def _emit_block(state, name, msg):
    ok = _cleanup_receipt(state)
    warn = ("" if ok else
            "\nWARNING: could not delete CARD.receipt.json (held open by a "
            "straggler?) -- treat any standing receipt as UNTRUSTED until a "
            "close completes.")
    print(f"RECEIPT-GATE BLOCK[{name}]: {msg}{warn}", file=sys.stderr)


if __name__ == "__main__":
    _ascii_safe()
    _state = {"close_in_progress": False, "receipt_path": None,
              "h2_digest": None}
    try:
        sys.exit(main(_state))
    except Block as b:
        _emit_block(_state, b.name, b.msg)
        sys.exit(2)
    except SystemExit:
        raise
    except BaseException as e:  # noqa: BLE001 -- fail closed, never exit 1
        _emit_block(_state, "GATE-ERROR",
                    f"uncaught {type(e).__name__}: {e} (fail-closed)")
        sys.exit(2)
