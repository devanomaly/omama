"""Create named reds by temporarily corrupting only a disposable installed bundle."""

import argparse
import json
from pathlib import Path

import omama_cli
from omama_cli.bundle import BundleError, load_bundle


def challenge(name, path, mutate, expected):
    original = path.read_bytes()
    try:
        mutate(path, original)
        try:
            load_bundle()
        except BundleError as exc:
            message = str(exc)
            if expected not in message:
                raise AssertionError("{0}: expected {1!r}, got {2!r}".format(name, expected, message))
            print("RED {0}: {1}".format(name, message))
        else:
            raise AssertionError(name + ": corrupted installed bundle was accepted")
    finally:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(original)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    args = parser.parse_args()
    payload = Path(omama_cli.__file__).resolve().parent / "_payload"
    manifest_path = payload / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    resources = {entry["destination"]: payload / entry["resource"] for entry in manifest["files"]}

    challenge(
        "missing-resource",
        resources["tools/omama/work-order/validate_work_order.py"],
        lambda path, original: path.unlink(),
        "missing-resource: tools/omama/work-order/validate_work_order.py",
    )
    challenge(
        "missing-license",
        resources["tools/omama/LICENSE"],
        lambda path, original: path.unlink(),
        "missing-license: tools/omama/LICENSE",
    )
    challenge(
        "wrong-hash",
        resources["tools/omama/receipt-gate/receipt_gate.py"],
        lambda path, original: path.write_bytes(original + b"\n# synthetic drift\n"),
        "wrong-hash: tools/omama/receipt-gate/receipt_gate.py",
    )

    def missing_identity(path, original):
        value = json.loads(original.decode("utf-8"))
        del value["source"]["revision"]
        path.write_text(json.dumps(value), encoding="utf-8")

    challenge("missing-source-identity", manifest_path, missing_identity, "missing-source-identity")

    def omitted_checker(path, original):
        value = json.loads(original.decode("utf-8"))
        value["files"] = [
            entry for entry in value["files"]
            if entry["destination"] != "tools/omama/output-discipline/scripts/check_artifact.py"
        ]
        path.write_text(json.dumps(value), encoding="utf-8")

    challenge("omitted-checker", manifest_path, omitted_checker, "incomplete-resource-inventory")
    if not (args.source / "work-order" / "validate_work_order.py").is_file():
        raise AssertionError("healthy source control is absent")
    print("GREEN restored-installed-bundle: " + load_bundle().manifest["bundle_id"])
    print("CONTROL healthy-source-beside-test=true; installed loader did not fall back")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
