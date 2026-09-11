"""Exercise the private init-owner doctor context from an installed package."""

import argparse
import json

from omama_cli.bundle import load_bundle
from omama_cli.doctor import InternalDoctorContext, doctor
from omama_cli.target import resolve_target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--static-only", action="store_true")
    args = parser.parse_args()
    state = json.loads(args.state)
    report = doctor(
        resolve_target(args.target), load_bundle(), static_only=args.static_only,
        context=InternalDoctorContext(args.owner, state),
    )
    return report.emit()


if __name__ == "__main__":
    raise SystemExit(main())
