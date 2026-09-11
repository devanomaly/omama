"""Abruptly terminate a real installation at a chosen durable boundary.

Used by ``test_recovery``.  The termination must happen in a child process that
genuinely dies: an in-process simulation leaves the simulating process as the
live lock owner, and a live owner is never recovered.

Usage: interrupt_child.py <repository> <post-replace|post-activation|post-activation-wired>
"""

import os
import sys

import test_install as install_fixture

from omama_cli import install
from omama_cli.install import preflight_bundle, run_asset_transaction
from omama_cli.target import resolve_target
from omama_cli.wiring import activate_wiring, attach_wiring, finish_wiring, preflight_wiring


def _die(message):
    sys.stderr.write(message + "\n")
    sys.stderr.flush()
    # No unwinding, no atexit, no finally: this is an abrupt termination.
    os._exit(137)


def main():
    root, window = sys.argv[1], sys.argv[2]
    helper = install_fixture.InstallerContractTests(
        "test_inherited_git_routing_refuses_before_target_writes")
    bundle = helper.bundle()
    target = resolve_target(root, environ={})
    plan = preflight_bundle(target, bundle)
    runtime = {"runtime_mode": "explicit", "receipt_interpreter": sys.executable}

    if window == "post-replace":
        original = install.InstallationTransaction._atomic_write
        seen = {"count": 0}

        def fault(self, path, data, mode):
            original(self, path, data, mode)
            if path.name != "install-journal.json" and seen["count"] == 0:
                seen["count"] += 1
                # The replacement is durable; the journal has not recorded it.
                _die("KILLED-AFTER-REPLACE " + str(path))

        install.InstallationTransaction._atomic_write = fault
        run_asset_transaction(plan, status="prepared", prepare=lambda transaction: runtime)
    elif window in ("post-activation", "post-activation-wired"):
        after_publication = None
        state_extra = None
        wiring = None
        if window == "post-activation-wired":
            wiring = preflight_wiring(plan, sys.executable, False)
            attach_wiring(plan, wiring)
            after_publication = lambda transaction: finish_wiring(transaction, wiring)
            state_extra = wiring.state_extra

        def die_after_activation(transaction):
            if wiring is not None:
                # Activation now happens after private admission; the window
                # this reproduces is death with hooks live and state still
                # incomplete.
                activate_wiring(transaction, wiring)
            _die("KILLED-AFTER-STATE-WRITTEN")

        run_asset_transaction(
            plan, status="complete", prepare=lambda transaction: runtime,
            after_publication=after_publication, state_extra=state_extra,
            before_finish=die_after_activation,
        )
    else:
        raise SystemExit("unknown window: " + window)
    raise SystemExit(0)


if __name__ == "__main__":
    main()
