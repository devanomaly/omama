"""Read-only ownership decisions for the finite installer implemented after T4."""

import hashlib
from enum import Enum


class ExistingState(str, Enum):
    MISSING = "missing"
    ADOPTABLE_IDENTICAL = "adoptable-identical"
    SAME_BUNDLE = "same-bundle"
    PACKAGE_UPDATE = "package-update"
    IMMUTABLE_DRIFT = "immutable-drift"
    EDITABLE_PRESERVE = "editable-preserve"
    GENERATED_DRIFT = "generated-drift"


def classify_existing(bundle, entry, existing_bytes, recorded_bundle_id):
    if entry not in bundle.manifest["files"]:
        raise ValueError("entry is not from the validated bundle")
    packaged = bundle.files.get(entry["resource"])
    if packaged is None or hashlib.sha256(packaged).hexdigest() != entry["sha256"]:
        raise ValueError("bundle entry is no longer validated")
    if existing_bytes is None:
        return ExistingState.MISSING
    expected = entry["sha256"]
    identical = hashlib.sha256(existing_bytes).hexdigest() == expected
    current_bundle_id = bundle.manifest["bundle_id"]
    if recorded_bundle_id is None:
        return ExistingState.ADOPTABLE_IDENTICAL if identical else (
            ExistingState.EDITABLE_PRESERVE if entry["ownership"] == "editable-bootstrap" else ExistingState.IMMUTABLE_DRIFT
        )
    if recorded_bundle_id != current_bundle_id:
        return ExistingState.PACKAGE_UPDATE
    if identical:
        return ExistingState.SAME_BUNDLE
    if entry["ownership"] == "editable-bootstrap":
        return ExistingState.EDITABLE_PRESERVE
    if entry["ownership"] == "generated-wiring":
        return ExistingState.GENERATED_DRIFT
    return ExistingState.IMMUTABLE_DRIFT
