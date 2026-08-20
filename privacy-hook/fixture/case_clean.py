#!/usr/bin/env python3
"""Clean case.

Builds a temp repo with the hook installed, stages an unremarkable file,
attempts a commit. Exit code mirrors `git commit`'s own exit code: this
script exits ZERO when the commit succeeds, proving the hook does not
false-positive on ordinary content.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402


def main():
    repo = lib.make_repo()

    lib.write_file(repo, "src/hello.py",
                    b"def greet(name):\n    return 'hello, ' + name\n")

    r = lib.attempt_commit(repo, "clean commit")
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)

    if r.returncode != 0:
        sys.stderr.write(
            "FIXTURE BUG: clean commit was blocked (returncode %d)\n" % r.returncode)

    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
