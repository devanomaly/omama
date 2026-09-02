#!/usr/bin/env python3
"""Scanner-location override case (issue #15).

The wrapper used to hardcode `<repo-root>/scan_staged.py`. An adopter who
vendors the scanner somewhere else (`tools/`, to keep the root clean) had
to edit the wrapper body -- and an edited wrapper is no longer
byte-identical with upstream, which is what makes "update" a copy instead
of a merge. The wrapper now reads ONE knob, `PRIVACY_HOOK_SCANNER`,
defaulting to `<repo-root>/scan_staged.py`.

Five assertions, one throwaway repo:

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

  4. announced -- the knob is read from the AMBIENT environment, so an
     exported value (shell profile, direnv, CI job env, a stale launcher
     from another repo) lives in no diff and no reviewer ever sees it.
     Existence is validated, identity is not: an override aimed at any
     readable file makes the hook a no-op. That residual is accepted;
     doing it SILENTLY is not. With the knob set, the wrapper must say so.
     Red when the wrapper only defaults quietly: an override pointing at
     an empty script commits the planted violation with rc=0 and zero
     output.

  5. stream discipline -- the notice goes to STDERR and the scanner's
     verdict lines stay on STDOUT. Through `git commit` that split is
     invisible: git folds a hook's stdout into its own stderr, so a
     review mutation that dropped the notice's `>&2` left assertion 4
     green and would have left an `r.stderr` check green too (measured
     2026-09-02). So the wrapper is invoked DIRECTLY here, as a combined
     hook's `exec sh .githooks/privacy-pre-commit` does, with the two
     streams captured apart. Red with the `>&2` dropped: the notice
     lands on stdout among the verdicts.

Assertion 3 also charges the pasteable-output promise on the new
diagnostic: no traceback, and no absolute path in the message.

Exits 0 when all five hold, 1 otherwise, 2 if the fixture itself could
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


def find_sh():
    """A POSIX shell to run the wrapper with, for the one assertion that
    must see the wrapper's own streams. PATH first; on Windows, Git for
    Windows ships one next to git (`<Git>/bin/sh.exe`)."""
    sh = shutil.which("sh")
    if sh:
        return sh
    git = shutil.which("git")
    if git:
        root = os.path.dirname(os.path.dirname(git))
        for cand in (("bin", "sh.exe"), ("usr", "bin", "sh.exe")):
            p = os.path.join(root, *cand)
            if os.path.exists(p):
                return p
    return None


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

    # --- 4. an override that IS honoured must announce itself -----------
    # `innocuous.py` exists and is readable, so the existence check passes
    # and the wrapper runs it: an empty script scans nothing and exits 0.
    # The commit going through is the documented residual (existence is
    # validated, identity is not). What is charged here is that the
    # redirection is OBSERVABLE -- the value came from the ambient
    # environment and appears in no diff.
    lib.write_file(repo, "innocuous.py", b"")
    lib.write_file(repo, VIOLATING_PATH, VIOLATION)
    lib.git(repo, "add", VIOLATING_PATH)
    r = commit(repo, "override honoured: must be announced",
               scanner="innocuous.py")
    # Through `git commit` this can only charge that the line EXISTS: git
    # folds a hook's stdout into its own stderr, so everything the hook
    # printed arrives on r.stderr whatever stream the wrapper chose
    # (measured 2026-09-02: `>&2` removed, r.stderr unchanged). Which
    # stream the wrapper itself writes to is assertion 5.
    if "privacy-hook: scanner =" not in r.stderr:
        sys.stderr.write(
            "FAIL: PRIVACY_HOOK_SCANNER was honoured SILENTLY -- an ambient "
            "override redirected the scan and nothing in the hook output "
            "said so (rc=%d)\n%s\n"
            % (r.returncode, (r.stdout + r.stderr).strip() or "<no output>"))
        ok = False
    elif "innocuous.py" not in r.stderr:
        sys.stderr.write(
            "FAIL: the override notice does not name the value the scan was "
            "redirected to:\n%s\n" % r.stderr)
        ok = False
    else:
        print("PASS: an honoured PRIVACY_HOOK_SCANNER announces itself in "
              "the hook output")

    # --- 5. stream discipline: notice on stderr, verdict on stdout ------
    # README and EVIDENCE promise the notice on STDERR, and the scanner's
    # `BLOCKED <rule> <path>` verdict lines go to STDOUT -- the split a
    # chained hook, a CI step or a human piping the output relies on. git
    # hides it (see above), so the wrapper is invoked DIRECTLY here, the
    # way a combined hook's `exec sh .githooks/privacy-pre-commit` does,
    # with the two streams captured apart. Red with the notice's `>&2`
    # dropped: the notice lands on stdout among the verdicts.
    sh = find_sh()
    if sh is None:
        sys.stderr.write("FIXTURE BUG: no `sh` to invoke the wrapper directly "
                         "(looked on PATH and next to git)\n")
        return 2
    lib.write_file(repo, "config/other.env", VIOLATION)
    lib.git(repo, "add", "config/other.env")
    env = lib.hook_env()
    env["PRIVACY_HOOK_SCANNER"] = "scan_staged.py"
    d = subprocess.run([sh, os.path.join(".git", "hooks", "pre-commit")],
                       cwd=repo, capture_output=True, text=True, env=env)
    verdict = "BLOCKED aws-access-key config/other.env"
    if d.returncode != 1 or verdict not in d.stdout + d.stderr:
        sys.stderr.write(
            "FIXTURE BUG: direct wrapper run did not produce the expected "
            "verdict (rc=%d)\n  stdout: %s\n  stderr: %s\n"
            % (d.returncode, d.stdout.strip(), d.stderr.strip()))
        return 2
    if "privacy-hook: scanner =" not in d.stderr:
        sys.stderr.write(
            "FAIL: the override notice is not on the wrapper's STDERR -- "
            "wrapper invoked directly:\n  stdout: %s\n  stderr: %s\n"
            % (d.stdout.strip(), d.stderr.strip()))
        ok = False
    elif "privacy-hook: scanner =" in d.stdout:
        sys.stderr.write(
            "FAIL: the override notice is on the wrapper's STDOUT, among the "
            "verdict lines:\n%s\n" % d.stdout)
        ok = False
    elif verdict not in d.stdout or "BLOCKED " in d.stderr:
        sys.stderr.write(
            "FAIL: the scanner's verdict is not on STDOUT alone -- wrapper "
            "invoked directly:\n  stdout: %s\n  stderr: %s\n"
            % (d.stdout.strip(), d.stderr.strip()))
        ok = False
    else:
        print("PASS: wrapper invoked directly keeps the notice on stderr and "
              "the verdict on stdout")

    if ok:
        lib.rmtree(os.path.dirname(repo))
    else:
        sys.stderr.write("repo kept for post-mortem: %s\n" % repo)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
