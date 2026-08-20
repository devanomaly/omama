#!/usr/bin/env python3
"""verify_all.py -- one command that runs every piece's own fixture.

This exists because a release once shipped with a broken artifact (CRLF in
privacy-hook's pre-commit) that any full fixture pass would have caught. Run
this before packaging anything:

    py -3 verify_all.py            # Windows;  python3 verify_all.py on POSIX
    py -3 verify_all.py --fast     # skip privacy-hook's slow real-git corpus

Tri-state, composed honestly:

  VERIFIED -- the runner executed and everything it checks held.
  FAILED   -- the runner executed and found a violation (or crashed:
              a crash is a defect, not an excuse).
  NOT-RUN  -- the runner could not execute the proof here (missing
              interpreter, wrong platform, missing symlink privilege,
              child exit 2). A coverage failure is never a pass -- and
              never a failure either: it is a hole, reported as one.

Per piece: child exit 0 -> VERIFIED, exit 1 -> FAILED, exit 2 -> NOT-RUN.
Exception: protect-tests' runner uses exit 2 for "hook behaved other than
expected", which is a genuine defect, so its exit 2 stays FAILED (its
cannot-execute case -- node missing -- is already caught by the `needs`
probe before the runner starts).

Release hygiene is also an entry: a LICENSE file must exist at the root
(a requirement without an executable check is invisible to a
fixture-driven remediation loop, so here is its executable check).

Exit: 0 only if every entry is VERIFIED; 2 if anything was NOT-RUN (and
nothing failed); 1 if anything FAILED.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable

# (piece, cwd, argv, needs, timeout_s, rc2)
# rc2 is what a child exit code of 2 MEANS for that runner: "notrun" when
# the runner documents 2 as cannot-execute, "failed" when it overloads 2 as
# a real defect (only protect-tests does).
PIECES = [
    ("privacy-hook (real-git corpus, slow)", "privacy-hook/fixture",
     [PY, "check.py"], ["git"], 900, "notrun"),
    ("work-order", "work-order",
     [PY, "fixture/run_fixture.py"], [], 120, "notrun"),
    ("validator", "validator",
     [PY, "fixture/run_fixture.py"], [], 120, "notrun"),
    ("protect-tests", "protect-tests",
     [PY, "fixture/run_fixture.py", "all"], ["node"], 120, "failed"),
    ("starter-claude-md", "starter-claude-md",
     [PY, "fixture/run_fixture.py"], [], 120, "notrun"),
    ("output-discipline", "output-discipline",
     [PY, "fixture/run_fixture.py"], [], 120, "notrun"),
    ("receipt-gate", "receipt-gate",
     [PY, "fixture/run_fixture.py"], ["git"], 600, "notrun"),
    ("release hygiene: LICENSE at root", ".",
     "LICENSE_CHECK", [], 10, "notrun"),  # sentinel, handled below
]


def run(cwd, argv, timeout):
    # encoding pinned: child output may carry emoji (protect-tests' hook);
    # Windows' default cp1252 decoder crashes the reader thread otherwise.
    return subprocess.run(argv, cwd=str(ROOT / cwd), capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=timeout)


def check_license():
    """LICENSE must exist at the root and be non-trivial (an empty file is
    a checkbox, not a license)."""
    path = ROOT / "LICENSE"
    if not path.is_file():
        return 1, ("no LICENSE file at repo root -- the project grants "
                   "adopters no permission to copy, modify or redistribute")
    if len(path.read_text(encoding="utf-8", errors="replace").strip()) < 100:
        return 1, "LICENSE exists but is (near-)empty"
    return 0, "LICENSE present"


def main(argv):
    parser = argparse.ArgumentParser(
        description="Run every piece's own fixture; see module docstring.")
    parser.add_argument("--fast", action="store_true",
                        help="skip privacy-hook's slow real-git corpus")
    args = parser.parse_args(argv)  # unknown options error out (exit 2)
    fast = args.fast
    failed, notrun = [], []

    def report(name, rc, detail, rc2_meaning):
        if rc == 0:
            print(f"OK       {name}")
            return
        if rc == 2 and rc2_meaning == "notrun":
            reason = "\n".join(detail.strip().splitlines()[-3:]) or "exit 2"
            notrun.append((name, reason))
            print(f"NOT-RUN  {name}")
            print("         " + reason.replace("\n", "\n         "))
            return
        failed.append(name)
        print(f"FAILED   {name} (exit={rc})")
        tail = "\n".join(detail.strip().splitlines()[-6:])
        print("         " + tail.replace("\n", "\n         "))

    for name, cwd, cmd, needs, timeout, rc2 in PIECES:
        if fast and name.startswith("privacy-hook"):
            notrun.append((name, "skipped by --fast"))
            print(f"NOT-RUN  {name} (--fast)")
            continue
        missing = [n for n in needs if shutil.which(n) is None]
        if missing:
            notrun.append((name, f"missing: {', '.join(missing)}"))
            print(f"NOT-RUN  {name} (missing: {', '.join(missing)})")
            continue
        try:
            if cmd == "LICENSE_CHECK":
                rc, detail = check_license()
            else:
                proc = run(cwd, cmd, timeout)
                rc = proc.returncode
                detail = (proc.stdout or "") + (proc.stderr or "")
        except subprocess.TimeoutExpired:
            notrun.append((name, "timeout"))
            print(f"NOT-RUN  {name} (timeout after {timeout}s)")
            continue
        report(name, rc, detail, rc2)
    print()
    print(f"verify_all: {len(PIECES) - len(failed) - len(notrun)} ok, "
          f"{len(failed)} failed, {len(notrun)} not-run")
    if failed:
        return 1
    if notrun:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
