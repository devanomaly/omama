import argparse
import sys

from . import __version__


def _parser():
    parser = argparse.ArgumentParser(prog="omama")
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="prepare the Omama bundle in a repository")
    init.add_argument("path", nargs="?", default=".")
    init.add_argument("--python", dest="python", metavar="ABSOLUTE_PATH")
    init.add_argument("--no-git-config", action="store_true")
    doctor = commands.add_parser("doctor", help="inspect an Omama installation")
    doctor.add_argument("path", nargs="?", default=".")
    doctor.add_argument("--static-only", action="store_true")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    print(
        "NOT-RUN: omama {0} is reserved by the phase-1 interface; implementation belongs to a later checkpoint".format(args.command),
        file=sys.stderr,
    )
    return 2
