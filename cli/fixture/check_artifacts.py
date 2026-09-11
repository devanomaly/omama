"""Inspect the phase-1 wheel without importing from the source checkout.

Phase-1 delivery is wheel-only.  No source distribution is built or inspected,
and no wheel-to-sdist equivalence is claimed; whether a public release requires
a source distribution is a separate, later decision.
"""

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path


def fail(reason):
    raise SystemExit("FAILED: " + reason)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    args = parser.parse_args()

    def wheel_data(path):
        with zipfile.ZipFile(str(path)) as archive:
            names = set(archive.namelist())
            manifest_name = "omama_cli/_payload/manifest.json"
            if manifest_name not in names:
                fail("wheel-missing-payload-manifest")
            raw_manifest = archive.read(manifest_name)
            parsed = json.loads(raw_manifest.decode("utf-8"))
            if not isinstance(parsed.get("files"), list):
                fail("wheel-manifest-shape")
            for entry in parsed["files"]:
                if not isinstance(entry, dict) or not isinstance(entry.get("resource"), str) \
                        or not isinstance(entry.get("destination"), str) \
                        or not re.match(r"^[0-9a-f]{64}$", str(entry.get("sha256", ""))):
                    fail("wheel-manifest-entry-shape")
                name = "omama_cli/_payload/" + entry["resource"]
                if name not in names:
                    fail("wheel-missing-resource:" + entry["destination"])
                if hashlib.sha256(archive.read(name)).hexdigest() != entry["sha256"]:
                    fail("wheel-wrong-resource-hash:" + entry["destination"])
            metadata_name = next((name for name in names if name.endswith(".dist-info/METADATA")), None)
            metadata = archive.read(metadata_name).decode("utf-8") if metadata_name else ""
            if "Requires-Python: >=3.8" not in metadata:
                fail("wheel-python-floor")
            if not re.search(r"Requires-Dist: PyYAML\s*<7,>=6\.0\.2", metadata):
                fail("wheel-pyyaml-constraint")
            return parsed, raw_manifest, [archive.read(name) for name in sorted(names)]

    manifest, _raw, wheel_bytes = wheel_data(args.wheel)

    # Every payload resource that names an authoritative source file must equal
    # that file in the checkout the wheel was built from.
    for entry in manifest["files"]:
        source_name = entry.get("source")
        if not source_name:
            continue
        candidate = args.source / source_name
        if not candidate.is_file():
            fail("checkout-missing-authoritative-source:" + source_name)
        if hashlib.sha256(candidate.read_bytes()).hexdigest() != entry["sha256"]:
            fail("checkout-source-payload-mismatch:" + source_name)

    private = str(Path.home()).encode("utf-8")
    private_alt = str(Path.home()).replace("\\", "/").encode("utf-8")
    if any(private in data or private_alt in data for data in wheel_bytes):
        fail("private-home-path-in-artifact")
    source = manifest["source"]
    if source["dirty"] and source["exact_revision"] is not None:
        fail("dirty-build-claims-exact-revision")
    if manifest["license"] != {"destination": "tools/omama/LICENSE", "expression": "MIT"}:
        fail("license-identity")
    print("OK: wheel payload, source identity, hashes, constraints, and private-path scan")
    print("bundle_id=" + manifest["bundle_id"])
    print("revision=" + source["revision"])
    print("dirty=" + str(source["dirty"]).lower())
    print("files=" + str(len(manifest["files"])))
    return 0


if __name__ == "__main__":
    main()
