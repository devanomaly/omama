"""Read and validate bundle resources strictly from the installed package."""

import hashlib
import json
import pkgutil
from dataclasses import dataclass
from pathlib import Path


class BundleError(ValueError):
    pass


@dataclass(frozen=True)
class Bundle:
    manifest: dict
    files: dict
    manifest_bytes: bytes


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _validate_manifest(manifest, read_resource, manifest_bytes):
    source = manifest.get("source")
    required_source = (
        "url", "revision", "dirty", "exact_revision", "dirty_digest",
        "identity_inputs_digest", "modified_after_identity_capture", "dirty_digest_policy",
    )
    if not isinstance(source, dict) or any(key not in source for key in required_source):
        raise BundleError("missing-source-identity: manifest source identity is incomplete")
    if source["dirty"] and (source.get("exact_revision") is not None or not source.get("dirty_digest")):
        raise BundleError("invalid-source-identity: dirty source cannot claim an exact revision")
    if source["dirty"] and source["dirty_digest"] != source["identity_inputs_digest"]:
        raise BundleError("invalid-source-identity: dirty digest does not bind current identity inputs")
    if not isinstance(manifest.get("package_version"), str):
        raise BundleError("missing-package-identity: package version is absent")
    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise BundleError("missing-resource-inventory: manifest files must be a list")
    required = manifest.get("required_destinations")
    if not isinstance(required, list) or not required:
        raise BundleError("missing-resource-inventory: required destinations are absent")
    if len(required) != len(set(required)):
        raise BundleError("invalid-resource-inventory: duplicate required destination")
    destinations = [entry.get("destination") for entry in entries if isinstance(entry, dict)]
    if len(destinations) != len(set(destinations)):
        raise BundleError("invalid-resource-inventory: duplicate destination")
    if set(destinations) != set(required):
        missing = sorted(set(required) - set(destinations))
        extra = sorted(set(destinations) - set(required))
        detail = missing[0] if missing else extra[0] if extra else "unknown"
        raise BundleError("incomplete-resource-inventory: {0}".format(detail))
    files = {}
    for entry in entries:
        resource = entry.get("resource", "")
        destination = entry.get("destination", "")
        data = read_resource(resource)
        if data is None:
            reason = "missing-license" if destination == "tools/omama/LICENSE" else "missing-resource"
            raise BundleError("{0}: {1}".format(reason, destination or resource))
        actual = hashlib.sha256(data).hexdigest()
        if actual != entry.get("sha256"):
            raise BundleError("wrong-hash: {0}".format(destination or resource))
        files[resource] = data
    license_identity = manifest.get("license")
    if license_identity != {"destination": "tools/omama/LICENSE", "expression": "MIT"}:
        raise BundleError("missing-license: manifest has no MIT license destination")
    identity_basis = {
        "package_version": manifest["package_version"],
        "source": source,
        "license": license_identity,
        "files": [
            {key: entry[key] for key in ("destination", "ownership", "sha256")}
            for entry in entries
        ],
        "generated_local": manifest.get("generated_local"),
        "ownership_policy": manifest.get("ownership_policy"),
    }
    actual_bundle_id = hashlib.sha256(_canonical(identity_basis)).hexdigest()
    if manifest.get("bundle_id") != actual_bundle_id:
        raise BundleError("wrong-bundle-identity: manifest semantics do not match bundle_id")
    installed_identity = manifest.get("installed_identity")
    if not isinstance(installed_identity, dict) or installed_identity.get("destination") != "tools/omama/manifest.json":
        raise BundleError("missing-installed-identity: manifest installation contract is absent")
    return Bundle(manifest=manifest, files=files, manifest_bytes=manifest_bytes)


def load_bundle():
    raw = pkgutil.get_data("omama_cli", "_payload/manifest.json")
    if raw is None:
        raise BundleError("missing-resource: manifest.json")
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise BundleError("invalid-manifest: {0}".format(exc))

    def read_resource(relative):
        if not relative or relative.startswith(("/", "\\")) or ".." in Path(relative).parts:
            return None
        try:
            return pkgutil.get_data("omama_cli", "_payload/" + relative.replace("\\", "/"))
        except OSError:
            return None

    return _validate_manifest(manifest, read_resource, raw)


def validate_bundle_directory(root):
    root = Path(root)
    try:
        raw = (root / "manifest.json").read_bytes()
        text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        manifest = json.loads(text)
    except FileNotFoundError:
        raise BundleError("missing-resource: manifest.json")
    except (UnicodeDecodeError, ValueError) as exc:
        raise BundleError("invalid-manifest: {0}".format(exc))

    def read_resource(relative):
        path = root / relative
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError:
            return None
        try:
            return path.read_bytes()
        except (FileNotFoundError, IsADirectoryError):
            return None

    return _validate_manifest(manifest, read_resource, raw)
