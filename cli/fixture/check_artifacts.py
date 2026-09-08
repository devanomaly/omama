"""Inspect wheel/sdist structure without importing from the source checkout."""

import argparse
import hashlib
import json
import re
import tarfile
import zipfile
from pathlib import Path


def fail(reason):
    raise SystemExit("FAILED: " + reason)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sdist", required=True, type=Path)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--direct-wheel", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    args = parser.parse_args()

    with tarfile.open(str(args.sdist), "r:gz") as archive:
        members = {item.name: item for item in archive.getmembers() if item.isfile()}
        sdist_contents = []
        roots = {name.split("/", 1)[0] for name in members}
        if len(roots) != 1:
            fail("sdist-root")
        prefix = roots.pop() + "/"

        def sdist_read(relative):
            member = members.get(prefix + relative)
            return archive.extractfile(member).read() if member else None

        for member in members.values():
            sdist_contents.append(archive.extractfile(member).read())

        sdist_manifest_bytes = sdist_read("cli/omama_cli/_payload/manifest.json")
        if sdist_manifest_bytes is None:
            fail("sdist-missing-payload-manifest")
        if sdist_read("_build_identity.json") is None:
            fail("sdist-missing-source-identity")
        manifest = json.loads(sdist_manifest_bytes.decode("utf-8"))
        for entry in manifest["files"]:
            resource = sdist_read("cli/omama_cli/_payload/" + entry["resource"])
            if resource is None:
                fail("sdist-missing-resource:" + entry["destination"])
            if hashlib.sha256(resource).hexdigest() != entry["sha256"]:
                fail("sdist-wrong-resource-hash:" + entry["destination"])
            source_name = entry.get("source")
            if source_name:
                source_bytes = sdist_read(source_name)
                if source_bytes is None:
                    fail("sdist-missing-authoritative-source:" + source_name)
                if source_bytes != resource:
                    fail("sdist-source-payload-mismatch:" + source_name)
                if (args.source / source_name).read_bytes() != resource:
                    fail("checkout-source-payload-mismatch:" + source_name)

    def wheel_data(path):
        with zipfile.ZipFile(str(path)) as archive:
            names = set(archive.namelist())
            manifest_name = "omama_cli/_payload/manifest.json"
            if manifest_name not in names:
                fail("wheel-missing-payload-manifest")
            raw_manifest = archive.read(manifest_name)
            parsed = json.loads(raw_manifest.decode("utf-8"))
            for entry in parsed["files"]:
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
            return raw_manifest, [archive.read(name) for name in sorted(names)]

    rebuilt_manifest, rebuilt_bytes = wheel_data(args.wheel)
    direct_manifest, direct_bytes = wheel_data(args.direct_wheel)
    if rebuilt_manifest != sdist_manifest_bytes or direct_manifest != sdist_manifest_bytes:
        fail("manifest-identity-disagrees-across-artifacts")
    private = str(Path.home()).encode("utf-8")
    private_alt = str(Path.home()).replace("\\", "/").encode("utf-8")
    artifact_members = sdist_contents + rebuilt_bytes + direct_bytes
    if any(private in data or private_alt in data for data in artifact_members):
        fail("private-home-path-in-artifact")
    source = manifest["source"]
    if source["dirty"] and source["exact_revision"] is not None:
        fail("dirty-build-claims-exact-revision")
    if manifest["license"] != {"destination": "tools/omama/LICENSE", "expression": "MIT"}:
        fail("license-identity")
    print("OK: wheel/sdist payload, source identity, hashes, constraints, and private-path scan")
    print("bundle_id=" + manifest["bundle_id"])
    print("revision=" + source["revision"])
    print("dirty=" + str(source["dirty"]).lower())
    print("files=" + str(len(manifest["files"])))
    return 0


if __name__ == "__main__":
    main()
