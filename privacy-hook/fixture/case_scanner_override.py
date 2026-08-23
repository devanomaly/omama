#!/usr/bin/env python3
"""Scanner-location override case (issue #15).

The wrapper used to hardcode `<repo-root>/scan_staged.py`. An adopter who
vendors the scanner somewhere else (`tools/`, to keep the root clean) had
to edit the wrapper body -- and an edited wrapper is no longer
byte-identical with upstream, which is what makes "update" a copy instead
of a merge. The wrapper now reads ONE knob, `PRIVACY_HOOK_SCANNER`,
defaulting to `<repo-root>/scan_staged.py`.

Three assertions, one throwaway repo:

  1. baseline -- scanner at the default location, planted AWS-shaped key,
     commit BLOCKED. The `BLOCKED ...` lines are captured and become the
     charge for assertion 2.
  2. relocated -- the SAME violation, the scanner moved to
     `tools/scan_staged.py` and pointed at through PRIVACY_HOOK_SCANNER,
     must produce the SAME BLOCKED lines. Red when the override is
     ignored: the wrapper then runs the interpreter against a path that
     no longer exists, the commit still fails (rc != 0) but the output is
     an interpreter error and not the hook's verdict -- which is why this
     case charges the OUTPUT, not merely the polarity.
  3. missing override -- PRIVACY_HOOK_SCANNER pointing at a file that
     does not exist must FAIL CLOSED with a named `BLOCKED hook-error
     missing-scanner` (exit 1), never fall back to the default path. Red
     when the override is ignored: the default scanner is present and
     healthy, so the commit sails through with rc=0.

Assertion 3 also charges the pasteable-output promise on the new
diagnostic: no traceback, and no absolute path in the message.

Exits 0 when all three hold, 1 otherwise, 2 if the fixture itself could
not be set up.
"""
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

# Fake AWS-style access key -- shape-valid, not a real credential.
VIOLATION = b"AWS_ACCESS_KEY_ID=AKIAABCDEFGHIJKLMNOP\n"
VIOLATING_PATH = "config/deploy.env"


def commit(repo, message, scanner=None):
    """Commit WITHOUT staging anything first, optionally with the
    scanner-location override exported into the hook's environment (git
    passes its own environment down to the hook)."""
    env = os.environ.copy()
    if scanner is not None:
        env["PRIVACY_HOOK_SCANNER"] = scanner
    else:
        env.pop("PRIVACY_HOOK_SCANNER", None)
    return subprocess.run(["git", "commit", "-m", message], cwd=repo,
                          capture_output=True, text=True, env=env)


def blocked_lines(r):
    """The hook's verdict lines, in order. Findings go to stdout and
    hook-error diagnostics to stderr, so both streams are read."""
    out = []
    for line in (r.stdout + r.stderr).splitlines():
        if line.startswith("BLOCKED "):
            out.append(line.strip())
    return out


def main():
    repo = lib.make_repo()
    ok = True

    # --- 1. baseline: scanner at the default location -------------------
    lib.write_file(repo, VIOLATING_PATH, VIOLATION)
    lib.git(repo, "add", VIOLATING_PATH)
    r = commit(repo, "baseline: should be blocked")
    baseline = blocked_lines(r)
    if r.returncode == 0 or not baseline:
        sys.stderr.write(
            "FIXTURE BUG: baseline violation was not blocked by the hook at "
            "the default scanner location (rc=%d)\n%s%s\n"
            % (r.returncode, r.stdout, r.stderr))
        return 2
    print("PASS: default scanner location blocks -> %s" % baseline)

    # Un-stage the violation; the file stays on disk, untracked, so the
    # next stage is byte-identical to the one just charged.
    lib.git(repo, "rm", "--cached", "-q", VIOLATING_PATH)

    # --- 2. relocated scanner reached through the override --------------
    tools = os.path.join(repo, "tools")
    os.makedirs(tools, exist_ok=True)
    shutil.move(os.path.join(repo, "scan_staged.py"),
                os.path.join(tools, "scan_staged.py"))

    lib.git(repo, "add", VIOLATING_PATH)
    r = commit(repo, "relocated scanner: should be blocked the same way",
               scanner="tools/scan_staged.py")
    relocated = blocked_lines(r)
    if r.returncode == 0:
        sys.stderr.write("FAIL: relocated scanner did not block the "
                         "violation (rc=0)\n")
        ok = False
    elif relocated != baseline:
        sys.stderr.write(
            "FAIL: PRIVACY_HOOK_SCANNER ignored -- the relocated scanner did "
            "not produce the default location's verdict.\n"
            "  expected: %s\n  actual:   %s\n  raw output:\n%s%s\n"
            % (baseline, relocated, r.stdout, r.stderr))
        ok = False
    else:
        print("PASS: scanner reached via PRIVACY_HOOK_SCANNER gives the same "
              "verdict (red proven)")

    lib.git(repo, "rm", "--cached", "-q", VIOLATING_PATH)
    os.remove(os.path.join(repo, VIOLATING_PATH))
    # Put the scanner back at the default location, so assertion 3 charges
    # the override alone: with a healthy default present, a wrapper that
    # ignores the override lets the clean commit through (rc=0) instead of
    # failing closed.
    shutil.move(os.path.join(tools, "scan_staged.py"),
                os.path.join(repo, "scan_staged.py"))

    # --- 3. override pointing at a missing file: fail CLOSED ------------
    lib.write_file(repo, "src/hello.py",
                   b"def greet(name):\n    return 'hello, ' + name\n")
    lib.git(repo, "add", "src/hello.py")
    r = commit(repo, "clean content, broken scanner override",
               scanner="tools/scan_staged.py")
    out = r.stdout + r.stderr
    if r.returncode == 0:
        sys.stderr.write(
            "FAIL: PRIVACY_HOOK_SCANNER pointing at a missing file did not "
            "fail closed -- the commit went through (rc=0)\n%s\n" % out)
        ok = False
    elif "BLOCKED hook-error missing-scanner" not in out:
        sys.stderr.write(
            "FAIL: missing scanner override blocked, but without the named "
            "hook-error diagnostic:\n%s\n" % out)
        ok = False
    elif "Traceback" in out:
        sys.stderr.write("FAIL: missing scanner override produced a "
                         "traceback:\n%s\n" % out)
        ok = False
    elif repo in out or repo.replace("\\", "/") in out:
        sys.stderr.write("FAIL: hook-error output echoed an absolute "
                         "path:\n%s\n" % out)
        ok = False
    else:
        print("PASS: missing scanner override fails closed with "
              "`BLOCKED hook-error missing-scanner`")

    if ok:
        lib.rmtree(os.path.dirname(repo))
    else:
        sys.stderr.write("repo kept for post-mortem: %s\n" % repo)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
