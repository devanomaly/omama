import argparse
import sys

from . import __version__
from .bundle import BundleError, load_bundle
from .doctor import doctor
from .install import InstallError, preflight_bundle, run_asset_transaction
from .runtime import managed_runtime_interpreter, prepare_receipt_runtime, qualify_explicit
from .target import TargetError, resolve_target
from .wiring import attach_wiring, finish_wiring, preflight_wiring


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
    if args.command == "init":
        try:
            target = resolve_target(args.path)
            bundle = load_bundle()
            plan = preflight_bundle(target, bundle)
            explicit_info = qualify_explicit(args.python, target) if args.python else None
            interpreter = explicit_info["receipt_interpreter"] if explicit_info else managed_runtime_interpreter(target).as_posix()
            wiring = preflight_wiring(plan, interpreter, args.no_git_config)
            attach_wiring(plan, wiring)

            def prepare(transaction):
                return explicit_info or prepare_receipt_runtime(transaction)

            run_asset_transaction(
                plan, status="prepared", prepare=prepare,
                after_publication=lambda transaction: finish_wiring(transaction, wiring),
                state_extra=wiring.state_extra,
            )
        except (TargetError, InstallError, BundleError) as exc:
            reason = getattr(exc, "reason", "invalid-bundle")
            print("VIOLATION[{0}]: {1}".format(reason, exc), file=sys.stderr)
            return 1
        if wiring.activation_required and args.no_git_config:
            print("PREPARED: activation required; run exactly: {0}".format(wiring.activation_remedy))
            print("NOT-RUN: hooks are not active; mandatory admission was not attempted", file=sys.stderr)
            return 2
        print(
            "NOT-RUN: assets/runtime/settings/privacy are prepared and active, but doctor and mandatory admission are not integrated",
            file=sys.stderr,
        )
        return 2
    try:
        target = resolve_target(args.path)
        bundle = load_bundle()
        return doctor(target, bundle, static_only=args.static_only).emit()
    except (TargetError, InstallError, BundleError) as exc:
        reason = getattr(exc, "reason", "invalid-bundle")
        print("VIOLATION[{0}]: {1}".format(reason, exc), file=sys.stderr)
        return 1
