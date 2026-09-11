import argparse
import os
import shutil
import stat
import sys

from . import __version__
from .bundle import BundleError, load_bundle
from .doctor import InternalDoctorContext, doctor
from .install import InstallError, preflight_bundle, recover, run_asset_transaction
from .runtime import managed_runtime_interpreter, prepare_receipt_runtime, qualify_explicit
from .selftest import admission
from .target import TargetError, resolve_target
from .wiring import activate_wiring, attach_wiring, finish_wiring, preflight_wiring


def _remove_admission_tree(path):
    if not path.exists():
        return

    def make_writable(function, value, _error):
        os.chmod(value, stat.S_IWRITE)
        function(value)

    shutil.rmtree(str(path), onerror=make_writable)


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
            # One bounded recovery mode, inside init.  It reconciles only
            # demonstrably unambiguous state; anything that may be an external
            # edit is preserved and stops the run.
            recovery = recover(target)
            if recovery is not None:
                print("RECOVERED: reconciled an interrupted installation (journal status {0}); {1} file, {2} configuration and {3} runtime entry/entries were classified against their recorded before/after images.".format(
                    recovery["journal_status"], len(recovery["files"]), len(recovery["config"]), len(recovery["trees"])))
                print("RECOVERED: entries that had taken effect were rolled back to their recorded before-images; the interrupted installation was NOT completed. This init run installs from the beginning. The reconciled journal is kept at {0}.".format(
                    recovery.get("reconciled_journal", "(not retained)")))
            plan = preflight_bundle(target, bundle)
            # An empty --python is an explicit invalid value, not a silent
            # fall-through to the managed route.
            explicit_info = qualify_explicit(args.python, target) if args.python is not None else None
            interpreter = explicit_info["receipt_interpreter"] if explicit_info else managed_runtime_interpreter(target).as_posix()
            wiring = preflight_wiring(plan, interpreter, args.no_git_config)
            attach_wiring(plan, wiring)

            def prepare(transaction):
                return explicit_info or prepare_receipt_runtime(transaction)

            manual_activation = wiring.activation_required and args.no_git_config

            def _run_doctor(transaction, scratch, pre_activation):
                context = InternalDoctorContext(
                    transaction.owner, transaction.current_state,
                    scratch_root=scratch, pre_activation=pre_activation,
                )
                code = doctor(target, bundle, context=context).emit()
                if code != 0:
                    reason = "doctor-not-run" if code == 2 else "doctor-failed"
                    label = "pre-activation" if pre_activation else "activation-aware"
                    raise InstallError(reason, "mandatory internal {0} doctor returned {1}".format(label, code))

            def admit(transaction):
                # Ordering is the guarantee: every non-activation inventory
                # check and the complete installed adopter-specific admission
                # run privately first, activation happens only after they pass,
                # and the activation-aware doctor must then pass before the
                # installation may be marked complete.
                scratch = target.root / ".omama" / (".admission-" + transaction.owner)
                if scratch.exists():
                    raise InstallError("admission-scratch", "private admission scratch already exists")
                try:
                    scratch.mkdir()
                except OSError as exc:
                    raise InstallError(
                        "admission-scratch",
                        "private target-owned admission scratch could not be created: {0}: {1}".format(type(exc).__name__, exc),
                    )
                failure = None
                try:
                    _run_doctor(transaction, scratch, pre_activation=True)
                    admission_report = admission(target, transaction.current_state, scratch)
                    admission_code = admission_report.emit(sys.stdout, sys.stderr)
                    if admission_code != 0:
                        reason = "admission-not-run" if admission_code == 2 else "admission-failed"
                        raise InstallError(reason, "mandatory installed-command admission returned {0}".format(admission_code))
                    if activate_wiring(transaction, wiring):
                        print("ACTIVATED: repository-local core.hooksPath=.githooks was set after private admission passed")
                    _run_doctor(transaction, scratch, pre_activation=False)
                except Exception as exc:
                    failure = exc
                try:
                    _remove_admission_tree(scratch)
                except OSError as exc:
                    raise InstallError(
                        "admission-cleanup",
                        "private admission scratch could not be removed: {0}: {1}".format(type(exc).__name__, exc),
                        incomplete=True,
                    )
                if failure is not None:
                    raise failure

            run_asset_transaction(
                plan, status="prepared" if manual_activation else "complete", prepare=prepare,
                after_publication=lambda transaction: finish_wiring(transaction, wiring),
                before_finish=None if manual_activation else admit,
                state_extra=wiring.state_extra,
            )
        except (TargetError, InstallError, BundleError) as exc:
            reason = getattr(exc, "reason", "invalid-bundle")
            print("VIOLATION[{0}]: {1}".format(reason, exc), file=sys.stderr)
            return 1
        if manual_activation:
            print("PREPARED: activation required; run exactly: {0}".format(wiring.activation_remedy))
            print("NOT-RUN: hooks are not active; mandatory admission was not attempted", file=sys.stderr)
            return 2
        print("INSTALLED: doctor and every mandatory installed-command admission check passed")
        print("ADOPT STARTER: copy docs/templates/omama/CLAUDE.starter.md to CLAUDE.md, remove its header comment, adjust every <ADJUST: ...> field, then validate the adjusted copy before committing.")
        print("PER-OPERATOR OUTPUT-DISCIPLINE BLOCK (copy deliberately to your global CLAUDE.md; omama did not write global configuration):")
        print("> **Output form.** Plans and reviews follow the templates in docs/templates/omama/: structure is mandatory -- severity tier declared; reviews open with the verdict within the first 3 non-empty lines, followed by Findings/Non-findings. Line budgets (XS <=5; S <=15; M <=40; L no ceiling) are advisory -- the checker warns, it does not fail. XS floor: one line in chat (`Plan (XS): goal; done when X; verify: cmd`). Spot-check: `<receipt-python> tools/omama/output-discipline/scripts/check_artifact.py --budgets-advisory <file>`.")
        return 0
    try:
        target = resolve_target(args.path)
        bundle = load_bundle()
        return doctor(target, bundle, static_only=args.static_only).emit()
    except (TargetError, InstallError, BundleError) as exc:
        reason = getattr(exc, "reason", "invalid-bundle")
        print("VIOLATION[{0}]: {1}".format(reason, exc), file=sys.stderr)
        return 1
