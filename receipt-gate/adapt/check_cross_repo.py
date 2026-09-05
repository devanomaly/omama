#!/usr/bin/env python3
"""check_cross_repo.py -- per-machine proof that a vendored receipt gate
REFUSES to close another repository's card.

The gate resolves OMAMA_CARD BEFORE cwd. A stray OMAMA_CARD (exported by a
dispatching session, or left over from another task) therefore points the
Stop hook at a card that lives somewhere else entirely -- and a close attempt
unlinks THAT repository's standing receipt and consumes its CARD.close before
anything else happens. The gate must instead raise a named block,
BLOCK[CROSS-REPO], at card resolution: before the receipt is touched.

    python3 check_cross_repo.py    # py -3 on Windows; no arguments

What it does: builds two throwaway git repos in a temp dir -- a CARD repo
carrying a valid card, a declared close and a planted sentinel receipt, and an
unrelated SESSION repo -- then runs this checkout's own receipt_gate.py with
synthetic Stop-hook stdin, cwd in the session repo and OMAMA_CARD pointing at
the card repo. OMAMA_* is scrubbed from the environment every subprocess here
is given (an adopting repo exports its own), and only OMAMA_CARD is set back;
git's repository-routing variables (GIT_DIR, GIT_INDEX_FILE, GIT_CONFIG_* and
the rest) are scrubbed too, so this check can never touch a repository outside
its scratch dir even when the shell that runs it carries them.

Assertions, in order:
  1  cross-repo CLOSE intent -> exit 2, BLOCK[CROSS-REPO] naming BOTH
     toplevels and the remedy (unset OMAMA_CARD), the card repo's CARD.close
     still there, its receipt byte-identical, and no receipt written into the
     session repo.
  2  cross-repo honest `FAILED: <reason>` close -> the same. Every close
     intent writes a receipt into the card's repository, so the honest ones
     are refused too.
  3  a `git worktree add` of the CARD repo used as the session cwd -> the
     same. A worktree's toplevel differs from its main checkout's, so
     "OMAMA_CARD pinned at the main checkout, close run in the worktree" is
     this same hazard and is refused by name.
  4  a same-repo close (cwd = the card repo, OMAMA_CARD = its own card) still
     exits 0 with verdict VERIFIED -- the block is not over-broad.

A non-git card directory (no toplevel at all) is NOT refused: it keeps the
gate's degraded-honest behavior, and is out of scope here.

Exit contract:
  0  every assertion held; each printed one line naming what it observed.
  1  FAIL: the FIRST failed assertion, named on stderr, with the gate's last
     output lines.
  2  NOT-RUN: the proof could not be attempted here (no git, this checkout's
     gate or validator missing, or this interpreter lacks PyYAML). A hole is
     reported as a hole, never as a pass.

Costs no Claude Code session -- it drives the gate directly -- so unlike
selftest_orchestrator_close.py it is cheap to re-run. The scratch dirs are
removed on every exit path; if removal loses (Windows keeps git's loose
objects read-only) the leftover is NAMED on stdout, never left silent.
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATE = HERE.parent / "receipt_gate.py"
VALIDATOR = HERE.parent.parent / "work-order" / "validate_work_order.py"

# Quoted the way the gate's own fixture quotes a verify: the gate runs it with
# Popen(shell=True), so it must survive both cmd.exe and sh.
VERIFY = '"%s" -c "import sys; sys.exit(0)"' % Path(sys.executable).as_posix()

# Planted in the CARD repo before every refused attempt. The gate unlinks a
# standing receipt at the start of EVERY close attempt, so these exact bytes
# surviving is positive evidence that no close attempt began at all.
SENTINEL = json.dumps({"sentinel": "cross-repo-check"}).encode("utf-8")
CLOSE_BYTES = b"CLOSE"

TIMEOUT = 300

# Git's repository-ROUTING variables. `git -C <scratch>` does not neutralize
# them: GIT_DIR/GIT_INDEX_FILE win, so a shell carrying them (a hook, a
# wrapper, an interrupted rebase) would send this check's own `git add` and
# `git commit` into THAT repository instead of its scratch dir. Dropped, along
# with the config-injection trio, so nothing outside the scratch dir is
# reachable. Other GIT_* (GIT_EXEC_PATH, GIT_SSH, GIT_ASKPASS, ...) are KEPT:
# git may need them to run at all.
GIT_ROUTING = (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR", "GIT_NAMESPACE",
    "GIT_CEILING_DIRECTORIES", "GIT_DISCOVERY_ACROSS_FILESYSTEM",
    "GIT_CONFIG", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT")
GIT_CONFIG_PREFIXES = ("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")


def _scrubbed_env():
    """The one environment every subprocess of this check is given: this
    process's, minus OMAMA_* (an adopting repo exports its own card) and minus
    git's repository-routing variables."""
    return {k: v for k, v in os.environ.items()
            if not k.startswith("OMAMA_")
            and k not in GIT_ROUTING
            and not k.startswith(GIT_CONFIG_PREFIXES)}


ENV = _scrubbed_env()


class NotRun(Exception):
    pass


class Fail(Exception):
    pass


def tail(result, n=5):
    text = (result.stdout or "") + (result.stderr or "")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return "    (the gate produced no output)"
    return "\n".join("    | " + ln for ln in lines[-n:])


def rmtree(root):
    """Remove a scratch repo, or SAY it survived: on Windows git writes loose
    objects read-only and unlink fails with EACCES."""
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
        print("WARNING: the scratch dir survived at %s -- delete it by hand"
              % root)


def git(root, *args):
    r = subprocess.run(["git", "-C", str(root)] + list(args),
                       capture_output=True, text=True, env=ENV,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise Fail("git %s exited %d in the scratch repo: %s"
                   % (args[0], r.returncode, (r.stderr or "").strip()[:300]))
    return r.stdout


def toplevel(root):
    """The toplevel exactly as the gate renders it (Path of rev-parse)."""
    return str(Path(git(root, "rev-parse", "--show-toplevel").strip()))


def preconditions():
    if shutil.which("git") is None:
        raise NotRun("git is not on PATH; the scratch repos cannot be built")
    if not GATE.exists():
        raise NotRun("this checkout's gate is missing at %s -- there is "
                     "nothing to check" % GATE)
    if not VALIDATOR.exists():
        raise NotRun("this checkout's validator is missing at %s -- the "
                     "scratch card cannot be validated before use, and the "
                     "same-repo assertion would block on SCHEMA" % VALIDATOR)
    r = subprocess.run([sys.executable, "-c", "import yaml"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=ENV, timeout=60)
    if r.returncode != 0:
        raise NotRun("this interpreter lacks PyYAML (%s -c 'import yaml' "
                     "exited %d); it is the interpreter that would run the "
                     "gate here, and the gate cannot parse a card without it "
                     "-- the same-repo assertion would fail as if a valid "
                     "close were broken" % (sys.executable, r.returncode))


def build_repo(root, name):
    """One committed file and a valid card whose verify is a real command."""
    repo = Path(root) / name
    repo.mkdir(parents=True)
    git(repo, "init", "-q")
    (repo / "app.txt").write_text("hello\n", encoding="utf-8")
    git(repo, "add", "app.txt")
    git(repo,
        "-c", "user.email=check@omama.invalid",
        "-c", "user.name=omama check",
        "-c", "commit.gpgsign=false",
        "commit", "-q", "-m", "scratch: one committed file")
    card = ("goal: the scratch repo's card is closable\n"
            "non_goals:\n"
            "  - anything outside this scratch repo\n"
            "tier: S1\n"
            "task_type: implementation\n"
            "done_when:\n"
            "  - the gate answers\n"
            # json.dumps is a valid YAML double-quoted scalar and escapes the
            # inner quotes for us -- no hand-rolled YAML quoting.
            "verify: " + json.dumps(VERIFY) + "\n")
    card_path = repo / "CARD.yaml"
    card_path.write_text(card, encoding="utf-8")
    r = subprocess.run([sys.executable, str(VALIDATOR), str(card_path)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=ENV, timeout=60)
    if r.returncode != 0 or not (r.stdout or "").startswith("OK"):
        raise Fail("the in-tree validator rejected the scratch card (exit %d) "
                   "-- this check's own fixture is broken, not the gate:\n%s"
                   % (r.returncode,
                      ((r.stdout or "") + (r.stderr or "")).strip()[:600]))
    return repo


def run_gate(cwd, card_path):
    """The gate as a Stop hook would run it: synthetic stdin, cwd, and the
    scrubbed environment plus the one OMAMA_CARD this check is about."""
    env = dict(ENV)
    env["OMAMA_CARD"] = str(card_path)
    payload = json.dumps({"cwd": str(cwd), "stop_hook_active": False,
                          "hook_event_name": "Stop"})
    return subprocess.run([sys.executable, str(GATE)], input=payload,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env, cwd=str(cwd),
                          timeout=TIMEOUT)


def refused(label, card_repo, session_dir, r, close_body=CLOSE_BYTES):
    """The four evidence-preservation facts, in the order that explains a
    failure best: the refusal, its name, both toplevels, then the files."""
    if r.returncode != 2:
        raise Fail("%s: the gate exited %d, expected 2 -- a close whose card "
                   "lives in another repository was NOT refused  [%s]\n%s"
                   % (label, r.returncode, session_dir, tail(r)))
    if "CROSS-REPO" not in r.stderr:
        raise Fail("%s: the gate blocked but did not name CROSS-REPO on "
                   "stderr  [%s]\n%s" % (label, session_dir, tail(r)))
    for what, path in (("card", toplevel(card_repo)),
                       ("session", toplevel(session_dir))):
        if path not in r.stderr:
            raise Fail("%s: the block message does not name the %s repo's "
                       "toplevel (%s) -- the operator cannot see which two "
                       "repositories disagree\n%s" % (label, what, path,
                                                      tail(r)))
    if "OMAMA_CARD" not in r.stderr:
        raise Fail("%s: the remedy (unset OMAMA_CARD) is not named in the "
                   "block message -- the session is told no and not told how "
                   "to proceed\n%s" % (label, tail(r)))
    close_now = (card_repo / "CARD.close").read_bytes() \
        if (card_repo / "CARD.close").exists() else None
    if close_now != close_body:
        raise Fail("%s: the card repo's CARD.close was %s by a refused "
                   "cross-repo attempt -- the close intent of another "
                   "repository was consumed\n%s"
                   % (label, "consumed" if close_now is None else "rewritten",
                      tail(r)))
    receipt = card_repo / "CARD.receipt.json"
    receipt_now = receipt.read_bytes() if receipt.exists() else None
    if receipt_now != SENTINEL:
        raise Fail("%s: the card repo's standing receipt %s -- a refused "
                   "attempt destroyed another repository's durable evidence\n%s"
                   % (label,
                      "is gone" if receipt_now is None else "was rewritten",
                      tail(r)))
    if (Path(session_dir) / "CARD.receipt.json").exists():
        raise Fail("%s: a receipt was written into the SESSION repo at %s "
                   "although the close was refused\n%s"
                   % (label, session_dir, tail(r)))
    print("OK %s: exit 2, BLOCK[CROSS-REPO] naming both toplevels; the card "
          "repo's CARD.close and receipt are intact, and no receipt was "
          "written in the session repo" % label)


def plant(card_repo, close_body):
    (card_repo / "CARD.close").write_bytes(close_body)
    (card_repo / "CARD.receipt.json").write_bytes(SENTINEL)


def main():
    preconditions()
    root = Path(tempfile.mkdtemp(prefix="omama-crossrepo-")).resolve()
    try:
        card_repo = build_repo(root, "card")
        session_repo = build_repo(root, "session")
        card_path = card_repo / "CARD.yaml"

        # 1: the VERIFIED-intent close.
        plant(card_repo, CLOSE_BYTES)
        refused("cross-repo CLOSE", card_repo, session_repo,
                run_gate(session_repo, card_path))

        # 2: the honest close, which also writes a receipt into the card's
        # repository and is therefore refused too.
        honest = b"FAILED: probe"
        plant(card_repo, honest)
        refused("cross-repo honest FAILED close", card_repo, session_repo,
                run_gate(session_repo, card_path), close_body=honest)

        # 3: a worktree of the CARD repo is a DIFFERENT toplevel.
        plant(card_repo, CLOSE_BYTES)
        wt = root / "wt"
        git(card_repo, "worktree", "add", "-q", str(wt), "-b", "wt")
        refused("worktree of the card's repo as cwd", card_repo, wt,
                run_gate(wt, card_path))

        # 4: the same repo still closes -- the block is not over-broad.
        same_repo_close(card_repo, card_path)
    finally:
        rmtree(root)
    return 0


def same_repo_close(card_repo, card_path):
    plant(card_repo, CLOSE_BYTES)
    r = run_gate(card_repo, card_path)
    if r.returncode != 0:
        raise Fail("same-repo close: the gate exited %d, expected 0 -- the "
                   "CROSS-REPO block is over-broad and now refuses a card in "
                   "the session's OWN repository\n%s" % (r.returncode, tail(r)))
    receipt = card_repo / "CARD.receipt.json"
    if not receipt.exists():
        raise Fail("same-repo close: the gate allowed the stop but wrote no "
                   "CARD.receipt.json\n%s" % tail(r))
    try:
        rec = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Fail("same-repo close: CARD.receipt.json is unreadable or "
                   "unparseable (%s)" % type(e).__name__)
    if rec.get("verdict") != "VERIFIED":
        raise Fail("same-repo close: receipt verdict is %r, expected "
                   "'VERIFIED'\n%s" % (rec.get("verdict"), tail(r)))
    print("OK same-repo close: exit 0, receipt verdict VERIFIED -- the block "
          "does not fire when the card lives in the session's own repo")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except NotRun as e:
        sys.stderr.write("NOT-RUN: %s\n" % e)
        sys.exit(2)
    except Fail as e:
        sys.stderr.write("FAIL: %s\n" % e)
        sys.exit(1)
