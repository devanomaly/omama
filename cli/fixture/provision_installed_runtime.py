"""Provision one synthetic target using only the installed omama package."""

import argparse
import json

from omama_cli.bundle import load_bundle
from omama_cli.install import preflight_bundle, run_asset_transaction
from omama_cli.runtime import prepare_receipt_runtime
from omama_cli.target import resolve_target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--base-python", required=True)
    args = parser.parse_args()
    target = resolve_target(args.target)
    bundle = load_bundle()
    plan = preflight_bundle(target, bundle)
    run_asset_transaction(
        plan,
        prepare=lambda transaction: prepare_receipt_runtime(
            transaction, base_python=args.base_python
        ),
        status="prepared",
    )
    print(json.dumps({
        "bundle_id": bundle.manifest["bundle_id"],
        "target": target.root.as_posix(),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
