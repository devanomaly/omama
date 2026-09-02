#!/usr/bin/env python3
"""check_wiring.py -- mechanical "gate presence" check for the Stop hook.

The failure this closes: a registered Stop hook whose command exits 127/9009
(missing interpreter, wrong script path, Windows-Store python3 stub) does NOT
block in Claude Code, so the gate is silently absent forever while
settings.json looks installed. This script turns that state into an exit
code the adopting repo (or its CI) can re-check at any time.

    python3 check_wiring.py [repo-root] [--static-only]
        # repo-root defaults to the cwd's `git rev-parse --show-toplevel`

WHAT IS CERTIFIED -- one hook form, the one adapt/README prescribes:
  a SYNCHRONOUS Stop hook of type "command", written as ONE shell-form
  command string (no `args`), run by the default hook shell (`shell`
  absent or "bash" -- sh-like on every platform, Git Bash on Windows),
  with an absolute interpreter path and the gate script as an argument.
  Every other form Claude Code accepts is a NAMED VIOLATION here, not a
  silently accepted configuration: an async hook cannot block a close,
  an exec-form (`command` + `args`) hook is not modeled, a PowerShell
  hook is not modeled, and `disableAllHooks: true` in either project
  settings file turns every hook off. Narrow on purpose -- a check that
  guessed at forms it does not model would certify gates it cannot see.

SECURITY: by default this check EXECUTES the registered command string it
finds in the settings files (the dry run is what proves the gate answers).
Never run the default mode against a checkout you do not trust -- e.g. CI
building fork PRs, where the PR can rewrite .claude/settings.json to any
command. Use `--static-only` there: it resolves the interpreter and script
paths WITHOUT executing anything, exits 0 with `WIRING-STATIC-OK` (the
gate's answer is NOT proven), and keeps every VIOLATION below.

Exit contract (tri-state, fail closed, never a traceback):
  0  gate PRESENT: at least one certified-form Stop hook in
     <repo-root>/.claude/settings.json or settings.local.json resolves
     AND, dry-invoked with EMPTY stdin, answers with the gate's own named
     block -- "RECEIPT-GATE BLOCK[BAD-INPUT]" on exit 2. The block NAME is
     matched, not just the exit code: any stub can exit 2, only the gate
     answers. Broken SIBLING Stop hooks do not flip the exit (documented
     at-least-one contract) but each of their failures is printed as a
     "WARNING: sibling Stop hook not certified: ..." line on stderr.
  1  one "VIOLATION: ..." line per failure on stderr -- ALL failures of a
     command are reported, not just the first (missing interpreter AND
     missing script are two lines).
  2  NOT-RUN: neither settings file is readable, or no repo root could be
     resolved -- presence could not be evaluated either way.

Both <repo-root>/.claude/settings.json and settings.local.json are read
(Claude Code merges them; the machine-specific absolute interpreter path
this piece mandates naturally lands in the untracked local file).
`disableAllHooks: true` in EITHER file is a VIOLATION (fail closed -- a
`false` in the other file is not assumed to win). NOT read, and therefore
named residuals in the README: user-level ~/.claude settings (a gate wired
there, or a `disableAllHooks` there), managed policy settings, and a
`claude --settings` override on the command line.

Resolution steps per handler (hooks.Stop[*].hooks[*], type "command"):
  1. Handler fields: `async` / `asyncRewake` true, `args` present, or
     `shell` other than "bash" -> named VIOLATION (see above).
  2. The CLAUDE_PROJECT_DIR spellings the hook shell expands --
     `$CLAUDE_PROJECT_DIR` / `${CLAUDE_PROJECT_DIR}` -- are replaced with
     the repo root (forward slashes, as the live hook environment carries
     it) the way sh does it: NOT inside single quotes, NOT after a
     backslash; an occurrence sh would leave literal is a named
     VIOLATION (the hook could never find its script). The hook shell is
     sh-like on EVERY platform (Git Bash on Windows) -- verified
     empirically 2026-08-24: a live Stop hook received CLAUDE_PROJECT_DIR
     in its environment, both sh spellings expanded to the repo root, and
     `%CLAUDE_PROJECT_DIR%` reached the hook as a literal. The cmd-style
     spelling is therefore dead wiring on every platform and a named
     VIOLATION -- expanding it here would certify a hook that can never
     run.
  3. Shell operators (`| & ; < >` backtick, newline) are named
     VIOLATIONs: the command is exec'd as plain argv both here and
     conceptually by the gate contract, and `|| true` would swallow the
     gate's blocking exit. Quoting (single or double) is fine -- sh and
     shlex(posix=True) tokenize both the same way.
  4. The command is parsed with shlex.split(posix=True). Double-quoted
     Windows paths with SINGLE backslashes survive this (inside double
     quotes only `\\\\` and `\\"` are escapes) -- pinned by a fixture case.
     A path that itself contains `\\\\` or ends its quoted form with `\\"`
     would be mangled; don't write those.
  5. argv[0]: absolute -> must exist; bare launcher name (py, python3,
     python) -> shutil.which; anything else -> which OR repo-relative file.
  6. The script path (first arg ending in receipt_gate.py, else the first
     path-looking arg) must exist (absolute, or relative to the repo root).
  7. Only if 1-6 are clean AND --static-only was not given: the exact
     parsed command is dry-run with empty stdin (time-boxed), and must
     answer the BAD-INPUT block on exit 2.

What this does NOT do: it DETECTS dead wiring at the moment it runs --
nothing prevents the interpreter from vanishing afterwards; re-run it after
interpreter upgrades and on fresh clones (it is cheap enough for CI, but
see the SECURITY note above before wiring the default mode into CI that
checks out untrusted PRs). It models the hook shell as sh: on a Windows
host WITHOUT Git Bash, Claude Code falls back to PowerShell, where the
sh-form command string is not what runs -- the check does not verify Git
Bash's presence (residual, named in the README).
"""
import os
import sys

DRY_RUN_TIMEOUT = 30.0
BAD_INPUT_MARKER = "RECEIPT-GATE BLOCK[BAD-INPUT]"
BARE_LAUNCHERS = ("py", "python3", "python")

# The hook shell is sh-like on EVERY platform -- Git Bash on Windows --
# so only the sh spellings are substituted. Verified empirically
# (2026-08-24, Windows 11 host): a live Stop hook received
# CLAUDE_PROJECT_DIR in env; "$CLAUDE_PROJECT_DIR" and
# "${CLAUDE_PROJECT_DIR}" expanded to the repo root,
# "%CLAUDE_PROJECT_DIR%" reached the hook as a literal.
HOST_SHELL = "sh (Git Bash on Windows)"
HOST_FORMS = ("${CLAUDE_PROJECT_DIR}", "$CLAUDE_PROJECT_DIR")  # longest first
ALIEN_FORMS = ("%CLAUDE_PROJECT_DIR%",)
MODELED_SHELLS = ("bash",)          # the `shell` values this check models
ASYNC_FIELDS = ("async", "asyncRewake")

# Rejected outright: exec'd as argv they would be certified while meaning
# something else (or nothing) to the real hook shell. `(` `)` are NOT here
# on purpose -- "Program Files (x86)" is a legitimate quoted path.
SHELL_METAS = ("|", "&", ";", "<", ">", "`", "\n")


def _not_run(msg):
    sys.stderr.write("NOT-RUN: " + msg + "\n")
    return 2


def _emit(violations):
    for v in violations:
        sys.stderr.write("VIOLATION: " + v + "\n")
    return 1


def _resolve_root(argv):
    """(root|None, not_run_reason|None)."""
    import os
    import subprocess
    if len(argv) > 1 and argv[1].strip():
        root = argv[1]
        if not os.path.isdir(root):
            return None, "repo root {0} is not a directory".format(root)
        return os.path.abspath(root), None
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None, ("no repo root given and `git rev-parse "
                      "--show-toplevel` could not run")
    if r.returncode != 0 or not r.stdout.strip():
        return None, ("no repo root given and the cwd is not inside a git "
                      "repo (pass the root as argv[1])")
    return os.path.abspath(r.stdout.strip()), None


def _stop_handlers(doc):
    """Every hooks.Stop[*].hooks[*] handler object of type "command" with
    a non-empty command string -- the WHOLE object, so async/args/shell
    are judged, not dropped."""
    handlers = []
    hooks = doc.get("hooks") if isinstance(doc, dict) else None
    stop = hooks.get("Stop") if isinstance(hooks, dict) else None
    if isinstance(stop, list):
        for matcher in stop:
            if not isinstance(matcher, dict):
                continue
            inner = matcher.get("hooks")
            if not isinstance(inner, list):
                continue
            for h in inner:
                if (isinstance(h, dict) and h.get("type") == "command"
                        and isinstance(h.get("command"), str)
                        and h["command"].strip()):
                    handlers.append(h)
    return handlers


def _handler_violations(h):
    """Fields that take the handler outside the one certified form."""
    command = h["command"]
    violations = []
    for field in ASYNC_FIELDS:
        if h.get(field):
            violations.append(
                "async Stop hook cannot block: `{0}: true` runs the gate in "
                "the background, so its exit 2 never blocks the close -- "
                "the gate is absent; remove the field: {1!r}".format(
                    field, command))
    if "args" in h:
        violations.append(
            "exec-form hook (`command` + `args`) is not the form this check "
            "certifies: it models the shell-form command string only -- "
            "write the absolute interpreter and the script as ONE quoted "
            "command string (see adapt/README): {0!r}".format(command))
    shell = h.get("shell")
    if shell is not None and shell not in MODELED_SHELLS:
        violations.append(
            "hook shell {0!r} is not the modeled hook shell ({1}): this "
            "check certifies sh-form command strings only -- remove `shell` "
            "or set it to \"bash\": {2!r}".format(shell, HOST_SHELL, command))
    return violations


def _expand_host_forms(command, root):
    """Substitute the sh spellings of CLAUDE_PROJECT_DIR the way sh does:
    everywhere EXCEPT inside single quotes and right after a backslash.
    Returns (expanded, literal_forms) where literal_forms lists every
    occurrence sh would have left as text -- dead wiring, the caller's
    VIOLATION. The root is substituted with forward slashes, the value the
    live hook environment carries on every platform."""
    root_sh = root.replace("\\", "/")
    out = []
    literal = []
    in_single = False
    in_double = False
    i = 0
    n = len(command)
    while i < n:
        c = command[i]
        if not in_single and c == "\\" and i + 1 < n:
            # sh: backslash escapes the next character (outside quotes, and
            # `\$` inside double quotes) -- no expansion happens on it.
            nxt = command[i + 1:]
            for form in HOST_FORMS:
                if nxt.startswith(form):
                    literal.append("\\" + form)
                    break
            out.append(command[i:i + 2])
            i += 2
            continue
        if c == "'" and not in_double:
            in_single = not in_single
            out.append(c)
            i += 1
            continue
        if c == '"' and not in_single:
            in_double = not in_double
            out.append(c)
            i += 1
            continue
        matched = None
        for form in HOST_FORMS:
            if command.startswith(form, i):
                end = i + len(form)
                # `$CLAUDE_PROJECT_DIRX` names a longer variable to sh.
                if (form == "$CLAUDE_PROJECT_DIR" and end < n
                        and (command[end].isalnum() or command[end] == "_")):
                    continue
                matched = form
                break
        if matched:
            if in_single:
                literal.append("'" + matched + "'")
                out.append(matched)
            else:
                out.append(root_sh)
            i += len(matched)
            continue
        out.append(c)
        i += 1
    return "".join(out), literal


def _find_script_arg(args):
    """First arg ending in receipt_gate.py, else the first path-looking
    arg (contains a separator or ends in .py, and is not an option)."""
    for a in args:
        if a.lower().endswith("receipt_gate.py"):
            return a
    for a in args:
        if a.startswith("-"):
            continue
        if "/" in a or "\\" in a or a.lower().endswith(".py"):
            return a
    return None


def _check_command(command, root, static_only=False):
    """List of violation strings for one Stop hook command; [] == present."""
    import os
    import shlex
    import shutil
    import subprocess

    pre_violations = []
    for form in ALIEN_FORMS:
        if form in command:
            pre_violations.append(
                "CLAUDE_PROJECT_DIR spelled for the wrong shell: this "
                "host's hook shell ({0}) leaves {1} LITERAL, so the hook "
                "can never run here -- use {2}: {3!r}".format(
                    HOST_SHELL, form, HOST_FORMS[0], command))
    for meta in SHELL_METAS:
        if meta in command:
            pre_violations.append(
                "shell operator {0!r} in hook command -- the wiring check "
                "certifies a plain argv command only (operators like || "
                "would swallow the gate's blocking exit): "
                "{1!r}".format(meta, command))
    expanded, literal = _expand_host_forms(command, root)
    for site in literal:
        pre_violations.append(
            "CLAUDE_PROJECT_DIR left LITERAL by the hook shell ({0}): {1} "
            "is inside single quotes or escaped, so sh does not expand it "
            "and the hook can never find its script -- use double quotes "
            "or none: {2!r}".format(HOST_SHELL, site, command))
    if pre_violations:
        return pre_violations  # parsing a shell-ism as argv proves nothing

    try:
        argv = shlex.split(expanded, posix=True)
    except ValueError as e:
        return ["hook command unparseable ({0}): {1!r}".format(e, command)]
    if not argv:
        return ["hook command is empty after parsing: {0!r}".format(command)]

    violations = []
    interp = argv[0]
    if os.path.isabs(interp):
        if not os.path.isfile(interp):
            violations.append("interpreter not found: {0}".format(interp))
    elif interp in BARE_LAUNCHERS:
        if shutil.which(interp) is None:
            violations.append("interpreter not on PATH: {0}".format(interp))
    else:
        if (shutil.which(interp) is None
                and not os.path.isfile(os.path.join(root, interp))):
            violations.append(
                "interpreter not resolvable (not absolute, not on PATH, "
                "not a file under the repo root): {0}".format(interp))

    script = _find_script_arg(argv[1:])
    if script is not None:
        spath = script if os.path.isabs(script) \
            else os.path.join(root, script)
        if not os.path.isfile(spath):
            violations.append("hook script not found: {0}".format(script))
    if violations:
        return violations  # a dry run of a dead path proves nothing new
    if static_only:
        return []  # paths resolve; the gate's answer is NOT proven

    try:
        r = subprocess.run(argv, input="", capture_output=True, text=True,
                           encoding="utf-8", errors="replace", cwd=root,
                           timeout=DRY_RUN_TIMEOUT)
    except subprocess.TimeoutExpired:
        return ["dry run timed out after {0:.0f}s (the gate answers "
                "BAD-INPUT instantly on empty stdin): {1!r}"
                .format(DRY_RUN_TIMEOUT, command)]
    except (OSError, subprocess.SubprocessError) as e:
        return ["dry run could not launch ({0}): {1!r}"
                .format(type(e).__name__, command)]
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 2 or BAD_INPUT_MARKER not in out:
        return ["gate did not answer: dry run on empty stdin exited {0} "
                "without the {1} block (an exit code alone is not the gate "
                "answering -- a Windows-Store python3 stub also exits "
                "non-zero): {2!r}"
                .format(r.returncode, BAD_INPUT_MARKER, command)]
    return []


def _check_handler(h, root, static_only=False):
    """Handler-level form violations first; only a handler in the certified
    form gets its command string resolved and dry-run."""
    violations = _handler_violations(h)
    if violations:
        return violations
    return _check_command(h["command"], root, static_only)


def main(argv):
    import json
    import os

    static_only = "--static-only" in argv[1:]
    argv = [a for a in argv if a != "--static-only"]

    root, reason = _resolve_root(argv)
    if root is None:
        return _not_run(reason)
    # Claude Code merges settings.json with the untracked
    # settings.local.json -- the machine-specific absolute interpreter
    # path this piece mandates naturally lands in the local file, so a
    # gate wired there is live and must be seen.
    candidates = [os.path.join(root, ".claude", "settings.json"),
                  os.path.join(root, ".claude", "settings.local.json")]
    parse_violations = []
    handlers = []
    readable = []
    unreadable = []
    for settings in candidates:
        try:
            with open(settings, "r", encoding="utf-8") as fh:
                raw = fh.read()
        except OSError as e:
            unreadable.append("{0} ({1})".format(settings,
                                                 type(e).__name__))
            continue
        readable.append(settings)
        try:
            doc = json.loads(raw)
        except ValueError as e:
            # A settings file Claude Code cannot parse wires NO hooks at
            # all: that is dead wiring, not a coverage hole -- fail closed.
            parse_violations.append(
                "settings not valid JSON ({0}) -- no hook can be wired "
                "from {1}".format(e, settings))
            continue
        if isinstance(doc, dict) and doc.get("disableAllHooks") is True:
            # Claude Code runs NO hook while this is set; a gate registered
            # next to it (or in the other file) is absent. Fail closed: a
            # `false` in the other file is not assumed to win.
            parse_violations.append(
                "disableAllHooks: true in {0} -- Claude Code runs no hook "
                "while it is set, so the gate is absent whatever the Stop "
                "entries say; remove it (or set it to false)".format(
                    settings))
        handlers.extend(_stop_handlers(doc))
    if not readable:
        return _not_run("cannot read any settings file ({0}) -- gate "
                        "presence not evaluated".format(
                            "; ".join(unreadable)))
    if parse_violations:
        return _emit(parse_violations)
    if not handlers:
        return _emit(['gate absent -- no Stop hook of type "command" with '
                      "a non-empty command in {0}".format(
                          " or ".join(readable))])

    results = [(h["command"], _check_handler(h, root, static_only))
               for h in handlers]
    clean = [command for command, violations in results if not violations]
    if clean:
        if static_only:
            print("WIRING-STATIC-OK: Stop hook command resolves "
                  "(interpreter and script exist; dry run SKIPPED -- the "
                  "gate's {0} answer is NOT proven): {1!r}".format(
                      BAD_INPUT_MARKER, clean[0]))
        else:
            print("WIRING-OK: Stop hook answers {0} (exit 2) on empty "
                  "stdin: {1!r}".format(BAD_INPUT_MARKER, clean[0]))
        # At-least-one contract: a broken SIBLING does not flip the exit,
        # but discarding its failures would hide a hook that blocks or
        # errors every close -- print them as non-fatal warnings.
        for command, violations in results:
            for v in violations:
                sys.stderr.write(
                    "WARNING: sibling Stop hook not certified: "
                    + v + "\n")
        return 0
    all_violations = []
    for _command, violations in results:
        all_violations.extend(violations)
    return _emit(all_violations)


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except SystemExit:
        raise
    except BaseException as e:  # noqa: BLE001 -- fail closed, no traceback
        sys.stderr.write(
            "VIOLATION: check_wiring internal error (fail-closed): "
            "{0}: {1}\n".format(type(e).__name__, e))
        sys.exit(1)
