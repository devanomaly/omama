#!/usr/bin/env python3
"""selftest_orchestrator_close.py -- per-machine proof of the orchestrator's
close path: a NON-INTERACTIVE Claude Code session opened in a repo fires THAT
repo's Stop hook (the receipt gate), and a session whose hooks are disabled
does not.

This closes the gap between "the gate works when I close by hand" and "the
gate works when a dispatching session closes a worktree it is not itself
running in". adapt/README's steps 2-3 prove the gate blocks and verifies;
this is the step after them -- it proves the SESSION reaches the gate at all.

    python3 selftest_orchestrator_close.py    # py -3 on Windows; no arguments

What it does: builds a throwaway git repo in a temp dir with one committed
file, a valid card whose `verify` is a real check on that file, and a
`.claude/settings.json` registering this checkout's own receipt_gate.py as a
Stop hook. Then it opens two print-mode Claude Code sessions in that repo
with the same one-line close instruction and reads what the gate did.

  RED    hooks disabled via `--settings '{"disableAllHooks":true}'`:
         a sentinel CARD.receipt.json is planted first, and must survive
         BYTE-IDENTICAL -- the gate unlinks any standing receipt at the
         start of every close attempt, so surviving bytes prove no hook
         ran, where a merely absent receipt would also be what a hook that
         fired and BLOCKED leaves behind. The session must also write
         CARD.close; one that did not is a broken HARNESS (no login, no
         model access), named as such -- never a pass.
  GREEN  the same command with no override: CARD.close must be CONSUMED
         and CARD.receipt.json must carry verdict VERIFIED, exit 0, and
         the scratch repo's HEAD as `rev`.

`--bare` is NOT the lever, though its --help line says it skips hooks: it
also never reads OAuth or the keychain, so on a subscription-login machine
it answers "Not logged in - Please run /login" and exits before any hook
point -- no session, and nothing to observe. Measured on Claude Code 2.1.260,
2026-09-04. `disableAllHooks` keeps the normal auth path; it is the same
switch adapt/check_wiring.py names as a VIOLATION when it appears in a
repo's committed settings.

Exit contract:
  0  both halves held; each printed one line naming what it observed and
     the exact claude command it ran.
  1  FAIL: a named violation on stderr (the observed state, plus the last
     output lines of the session that produced it).
  2  NOT-RUN: the proof could not be attempted here (no `claude` on PATH,
     `claude --version` unspawnable, no git, or this checkout's gate /
     validator missing). A hole is reported as a hole, never as a pass.

Costs two Claude Code sessions and depends on a working login, which is why
this is a developer-machine self-test and NOT wired into verify_all.py or CI.
Each session is bounded by a fixed 180 s timeout; a timeout is a named FAIL.
The scratch repo is removed on every exit path -- and if the removal loses
(Windows keeps git's loose objects read-only), the leftover is NAMED on
stdout, never left silent.
"""
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATE = HERE.parent / "receipt_gate.py"
VALIDATOR = HERE.parent.parent / "work-order" / "validate_work_order.py"

# The whole dispatch instruction, verbatim -- the close protocol the starter
# file gives an agent, reduced to one line a print-mode session can obey.
CLOSE_LINE = ("Write the single word CLOSE to the file CARD.close at the "
              "repository root, then stop. Do not touch any other file.")

# The RED lever: hooks off, auth untouched. Passed as one argv element, so
# no shell ever sees these quotes.
DISABLE_HOOKS = '{"disableAllHooks":true}'

TIMEOUT = 180

# The scratch card's proof: a real check that can actually go red (it exits 1
# the moment app.txt stops saying hello), quoted so cmd.exe survives it --
# the gate runs `verify` with Popen(shell=True).
VERIFY_BODY = ("import sys; sys.exit(0 if "
               "open('app.txt').read().strip()=='hello' else 1)")

# Planted before the red session. The gate unlinks a standing receipt at the
# start of EVERY close attempt, so these bytes surviving is positive evidence
# that no hook ran at all -- not merely that no close succeeded.
SENTINEL = {"sentinel": "orchestrator-selftest"}

_PLAIN = re.compile(r"^[A-Za-z0-9._:/\\-]+$")


class NotRun(Exception):
    pass


class Fail(Exception):
    pass


def shown(argv):
    """The command as a human would retype it in a shell."""
    return " ".join(a if _PLAIN.match(a) else "'" + a + "'" for a in argv)


def tail(result, n=5):
    text = (result.stdout or "") + (result.stderr or "")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return "    (the session produced no output)"
    return "\n".join("    | " + ln for ln in lines[-n:])


def read_bytes(p):
    try:
        return p.read_bytes()
    except OSError:
        return None


def rmtree(root):
    """Remove the scratch repo, or SAY it survived.

    ignore_errors=True is not enough on Windows: git writes loose objects
    read-only, unlink fails with EACCES, and the scratch repo silently
    accumulates in %TEMP% one per run. Clear the read-only bit and retry.
    """
    def retry(func, path, _exc):
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except OSError:
            pass

    if sys.version_info >= (3, 12):
        shutil.rmtree(str(root), onexc=retry)
    else:
        shutil.rmtree(str(root), onerror=retry)
    if root.exists():
        print("WARNING: the scratch repo survived at %s -- delete it by hand"
              % root)


def git(root, *args):
    r = subprocess.run(["git", "-C", str(root)] + list(args),
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise Fail("git %s exited %d in the scratch repo: %s"
                   % (args[0], r.returncode, (r.stderr or "").strip()[:300]))
    return r.stdout


def preconditions():
    """Return the resolved `claude` launcher, or raise a named NotRun."""
    claude = shutil.which("claude")
    if claude is None:
        raise NotRun("`claude` is not on PATH -- this self-test drives real "
                     "Claude Code sessions, there is nothing to substitute")
    try:
        r = subprocess.run([claude, "--version"], capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        raise NotRun("`claude --version` could not be spawned from %s (%s) -- "
                     "on Windows the launcher is often a .cmd shim; if it "
                     "cannot be run from a list argv, nothing below can run "
                     "either" % (claude, type(e).__name__))
    if r.returncode != 0:
        raise NotRun("`claude --version` exited %d (%s): %s"
                     % (r.returncode, claude,
                        ((r.stdout or "") + (r.stderr or "")).strip()[:200]))
    if shutil.which("git") is None:
        raise NotRun("git is not on PATH; the scratch repo cannot be built")
    if not GATE.exists():
        raise NotRun("this checkout's gate is missing at %s -- the scratch "
                     "repo has no hook to register" % GATE)
    if not VALIDATOR.exists():
        raise NotRun("this checkout's validator is missing at %s -- the "
                     "scratch card cannot be validated before use, and the "
                     "gate would block every close on SCHEMA" % VALIDATOR)
    # This interpreter is the one the scratch settings register as the hook.
    # Without PyYAML the gate exits GATE-ERROR on every close, and GREEN would
    # read as "print-mode sessions do not fire hooks" -- the exact opposite of
    # the fact this self-test exists to certify.
    r = subprocess.run([sys.executable, "-c", "import yaml"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=60)
    if r.returncode != 0:
        raise NotRun("this interpreter lacks PyYAML (%s -c 'import yaml' "
                     "exited %d); it is the interpreter the scratch repo would "
                     "register as its Stop hook, and the gate cannot parse a "
                     "card without it -- GREEN would fail as if print-mode "
                     "sessions did not fire hooks at all"
                     % (sys.executable, r.returncode))
    return claude


def build_scratch(root):
    """A throwaway repo carrying the whole loop: one committed file, a valid
    card proving something about it, and this checkout's gate as Stop hook."""
    interpreter = Path(sys.executable).as_posix()

    git(root, "init", "-q")
    (root / "app.txt").write_text("hello\n", encoding="utf-8")
    git(root, "add", "app.txt")
    git(root,
        "-c", "user.email=selftest@omama.invalid",
        "-c", "user.name=omama selftest",
        "-c", "commit.gpgsign=false",
        "commit", "-q", "-m", "scratch: one committed file")

    verify = '"%s" -c "%s"' % (interpreter, VERIFY_BODY)
    card = ("goal: the scratch repo's app.txt still reads hello\n"
            "non_goals:\n"
            "  - anything outside this scratch repo\n"
            "tier: S1\n"
            "task_type: implementation\n"
            "done_when:\n"
            "  - app.txt reads hello\n"
            # json.dumps is a valid YAML double-quoted scalar and escapes the
            # inner quotes for us -- no hand-rolled YAML quoting.
            "verify: " + json.dumps(verify) + "\n")
    card_path = root / "CARD.yaml"
    card_path.write_text(card, encoding="utf-8")

    r = subprocess.run([sys.executable, str(VALIDATOR), str(card_path)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=60)
    if r.returncode != 0 or not (r.stdout or "").startswith("OK"):
        raise Fail("the in-tree validator rejected the scratch card (exit %d) "
                   "-- this self-test's own fixture is broken, not the gate:\n"
                   "%s" % (r.returncode,
                           ((r.stdout or "") + (r.stderr or "")).strip()[:600]))

    # The certified form: absolute interpreter, absolute gate, forward slashes
    # (the hook shell on Windows is Git Bash), one shell-form command string.
    settings = {"hooks": {"Stop": [{"hooks": [{
        "type": "command",
        "command": '"%s" "%s"' % (interpreter, GATE.as_posix())}]}]}}
    (root / ".claude").mkdir()
    (root / ".claude" / "settings.json").write_text(
        json.dumps(settings, indent=1), encoding="utf-8")


def session(claude, root, disable_hooks):
    argv = [claude, "-p", CLOSE_LINE, "--allowedTools", "Write",
            "--max-turns", "3"]
    if disable_hooks:
        argv += ["--settings", DISABLE_HOOKS]
    try:
        r = subprocess.run(argv, cwd=str(root), timeout=TIMEOUT,
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        raise Fail("the claude session did not finish within %d s  [%s]"
                   % (TIMEOUT, shown(argv)))
    return argv, r


def red(claude, root):
    close = root / "CARD.close"
    receipt = root / "CARD.receipt.json"

    # "No receipt appeared" is an ABSENCE, and a hook that fired and BLOCKED
    # leaves that same absence: the gate deletes any standing receipt at the
    # start of every close attempt and does not consume CARD.close on a block.
    # So the red half asserts a POSITIVE fact instead -- these exact bytes are
    # still here -- which no close attempt of any outcome can leave true.
    planted = json.dumps(SENTINEL).encode("utf-8")
    receipt.write_bytes(planted)

    argv, r = session(claude, root, disable_hooks=True)

    # The hook-fired check comes FIRST: a dead lever consumes CARD.close, and
    # a missing CARD.close read as "harness" would blame the wrong thing.
    current = read_bytes(receipt)
    if current is None:
        observed = "is gone (or unreadable)"
    elif current != planted:
        observed = ("was replaced by: "
                    + current.decode("utf-8", "replace").strip()[:300])
    else:
        observed = None
    if observed is not None:
        raise Fail("RED: hooks were disabled and the Stop hook fired anyway "
                   "-- the planted sentinel receipt %s, and CARD.close was %s "
                   " [%s]\n%s"
                   % (observed,
                      "consumed" if not close.exists() else "left in place",
                      shown(argv), tail(r)))

    if not close.exists():
        raise Fail("RED: the session did not write CARD.close -- harness, not "
                   "the hook (no login? no model access? exit %d)  [%s]\n%s"
                   % (r.returncode, shown(argv), tail(r)))
    body = close.read_text(encoding="utf-8", errors="replace").strip()
    if body != "CLOSE":
        raise Fail("RED: CARD.close reads %r, expected 'CLOSE' -- harness, "
                   "not the hook  [%s]\n%s" % (body[:80], shown(argv), tail(r)))
    close.unlink()
    receipt.unlink()
    print("RED OK: hooks disabled -- session wrote CARD.close, the planted "
          "sentinel receipt survived byte-identical, no hook ran  [%s]"
          % shown(argv))


def green(claude, root):
    close = root / "CARD.close"
    receipt = root / "CARD.receipt.json"
    argv, r = session(claude, root, disable_hooks=False)

    if not receipt.exists():
        raise Fail("GREEN: no CARD.receipt.json after the plain session -- "
                   "the Stop hook did not fire, or it blocked the close "
                   "(CARD.close %s; session exit %d)  [%s]\n%s"
                   % ("survived" if close.exists() else "is gone",
                      r.returncode, shown(argv), tail(r)))
    if close.exists():
        raise Fail("GREEN: a receipt was written but CARD.close survived -- "
                   "the gate did not consume the close  [%s]\n%s"
                   % (shown(argv), tail(r)))
    try:
        rec = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Fail("GREEN: CARD.receipt.json is unreadable or unparseable "
                   "(%s)  [%s]" % (type(e).__name__, shown(argv)))

    head = git(root, "rev-parse", "HEAD").strip()
    observed = (rec.get("verdict"), rec.get("exit"), rec.get("rev"))
    if observed != ("VERIFIED", 0, head):
        raise Fail("GREEN: receipt is verdict=%r exit=%r rev=%r, expected "
                   "verdict='VERIFIED' exit=0 rev=%r  [%s]\n%s"
                   % (observed[0], observed[1], observed[2], head,
                      shown(argv), tail(r)))
    print("GREEN OK: Stop hook fired, receipt VERIFIED on %s  [%s]"
          % (head[:12], shown(argv)))


def main():
    claude = preconditions()
    root = Path(tempfile.mkdtemp(prefix="omama-close-")).resolve()
    try:
        build_scratch(root)
        red(claude, root)
        green(claude, root)
    finally:
        rmtree(root)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except NotRun as e:
        sys.stderr.write("NOT-RUN: %s\n" % e)
        sys.exit(2)
    except Fail as e:
        sys.stderr.write("FAIL: %s\n" % e)
        sys.exit(1)
