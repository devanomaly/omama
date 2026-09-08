#!/usr/bin/env python3
"""Acceptance cases for configured token-file states.

Every scanner invocation goes through the shipped wrapper against a real
staged Git index. Test payload literals are assembled from pieces so this
fixture remains committable through the shipped privacy configuration.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lib  # noqa: E402


MISSING = (
    "BLOCKED hook-error missing-tokens-file privacy-tokens.txt "
    "(create this gitignored file; it may start comment-only, then "
    "distribute the real literal list out of band)\n"
)
ZERO = (
    "notice privacy-hook: tokens file privacy-tokens.txt has zero literals; "
    "literal layer inactive (fill the file or set tokens_file=null explicitly)\n"
)


def configure(repo, state):
    path = os.path.join(repo, "privacy-deny.json")
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    if state == "omitted":
        cfg.pop("tokens_file", None)
    else:
        cfg["tokens_file"] = state
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")


def stage(repo, content=b"ordinary staged content\n"):
    lib.write_file(repo, "notes.txt", content)
    r = lib.git(repo, "add", "notes.txt")
    if r.returncode != 0:
        raise RuntimeError("git add failed: %s%s" % (r.stdout, r.stderr))


def run_scanner(repo):
    scanner = os.path.join(repo, "scan_staged.py")
    return subprocess.run([sys.executable, scanner], cwd=repo,
                          capture_output=True, text=True, env=lib.hook_env())


def one_case(name, prepare, expected_rc, expected_stdout, expected_stderr,
             forbidden=()):
    repo = lib.make_repo()
    try:
        prepare(repo)
        result = run_scanner(repo)
        actual = "rc=%d stdout=%r stderr=%r" % (
            result.returncode, result.stdout, result.stderr)
        problems = []
        if result.returncode != expected_rc:
            problems.append("expected rc=%d" % expected_rc)
        if result.stdout != expected_stdout:
            problems.append("unexpected stdout")
        if result.stderr != expected_stderr:
            problems.append("unexpected stderr")
        combined = result.stdout + result.stderr
        for value in forbidden:
            if value in combined:
                problems.append("output disclosed planted literal")

        # Git for Windows invokes the installed shell wrapper even when `sh`
        # is not directly on PATH. This is the adopter-facing decision path;
        # Git folds hook stdout into its stderr, so stream placement is charged
        # by the direct scanner call above and occurrence/decision here.
        wrapped = lib.git(repo, "commit", "-q", "-m", "token-state case")
        wrapped_output = wrapped.stdout + wrapped.stderr
        if wrapped.returncode != expected_rc:
            problems.append("wrapper expected rc=%d, got rc=%d" %
                            (expected_rc, wrapped.returncode))
        if expected_stdout and expected_stdout not in wrapped_output:
            problems.append("wrapper omitted scanner verdict")
        if expected_stderr and expected_stderr not in wrapped_output:
            problems.append("wrapper omitted scanner diagnostic/notice")
        expected_notice_count = 1 if expected_stderr == ZERO else 0
        if wrapped_output.count(ZERO) != expected_notice_count:
            problems.append("wrapper notice count expected %d, got %d" %
                            (expected_notice_count, wrapped_output.count(ZERO)))
        for value in forbidden:
            if value in wrapped_output:
                problems.append("wrapper output disclosed planted literal")
        if problems:
            print("FAIL %s: %s; direct %s; wrapper rc=%d output=%r" %
                  (name, ", ".join(problems), actual, wrapped.returncode,
                   wrapped_output))
            return False
        print("PASS %s: direct %s; wrapper rc=%d output=%r" %
              (name, actual, wrapped.returncode, wrapped_output))
        return True
    finally:
        parent = os.path.dirname(repo)
        if not lib.rmtree(parent):
            print("WARN: scratch tree not removed: fixture/.tmp/%s" %
                  os.path.basename(parent), file=sys.stderr)


def missing(repo):
    os.remove(os.path.join(repo, "privacy-tokens.txt"))
    stage(repo)


def empty(repo):
    lib.write_file(repo, "privacy-tokens.txt", b"")
    stage(repo)


def comment_only(repo):
    lib.write_file(repo, "privacy-tokens.txt", b"# bootstrap only\n  # still a comment\n\n")
    stage(repo)


def zero_with_block(repo):
    lib.write_file(repo, "privacy-tokens.txt", b"# no team literals yet\n")
    planted = b"AK" + b"IA" + b"T2SYNTHETIC000000"
    stage(repo, b"credential=" + planted + b"\n")


def null_tokens(repo):
    configure(repo, None)
    stage(repo)


def omitted_tokens(repo):
    configure(repo, "omitted")
    stage(repo)


def populated(repo):
    planted = "T2-" + "PLANTED-LITERAL"
    lib.write_file(repo, "privacy-tokens.txt", planted.encode("ascii") + b"\n")
    stage(repo, ("reference=" + planted + "\n").encode("ascii"))


def main():
    planted = "T2-" + "PLANTED-LITERAL"
    cases = [
        ("missing-configured-file-remedy", missing, 1, "", MISSING, ()),
        ("empty-file-one-notice", empty, 0, "", ZERO, ()),
        ("comment-only-one-notice", comment_only, 0, "", ZERO, ()),
        ("zero-literal-notice-does-not-mask-block", zero_with_block, 1,
         "BLOCKED aws-access-key notes.txt\n", ZERO, ()),
        ("explicit-null-silent", null_tokens, 0, "", "", ()),
        ("omitted-silent", omitted_tokens, 0, "", "", ()),
        ("populated-literal-enforced-without-value-output", populated, 1,
         "BLOCKED deny-token notes.txt\n", "", (planted,)),
    ]
    ok = True
    for args in cases:
        ok = one_case(*args) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
