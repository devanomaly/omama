"""The single explicit mapping from authoritative source files to payload paths."""

PACKAGE_VERSION = "0.1.0"
UPSTREAM_URL = "https://github.com/devanomaly/omama"
LICENSE_EXPRESSION = "MIT"

SOURCE_INVENTORY = (
    ("receipt-gate/receipt_gate.py", "tools/omama/receipt-gate/receipt_gate.py", "immutable"),
    ("receipt-gate/adapt/check_wiring.py", "tools/omama/receipt-gate/adapt/check_wiring.py", "immutable"),
    ("work-order/validate_work_order.py", "tools/omama/work-order/validate_work_order.py", "immutable"),
    ("output-discipline/scripts/check_artifact.py", "tools/omama/output-discipline/scripts/check_artifact.py", "immutable"),
    ("privacy-hook/scan_staged.py", "tools/omama/privacy-hook/scan_staged.py", "immutable"),
    ("privacy-hook/pre-commit", ".githooks/privacy-pre-commit", "immutable"),
    ("cli/build_support/chainer.sh", ".githooks/pre-commit", "generated-wiring"),
    ("cli/build_support/chainer.sh", ".githooks/pre-merge-commit", "generated-wiring"),
    ("privacy-hook/privacy-deny.json", "privacy-deny.json", "editable-bootstrap"),
    ("work-order/work-order.template.yaml", "work-order.template.yaml", "editable-bootstrap"),
    ("starter-claude-md/CLAUDE.starter.md", "docs/templates/omama/CLAUDE.starter.md", "editable-bootstrap"),
    ("output-discipline/templates/PLAN.md", "docs/templates/omama/PLAN.md", "editable-bootstrap"),
    ("output-discipline/templates/REVIEW.md", "docs/templates/omama/REVIEW.md", "editable-bootstrap"),
    ("LICENSE", "tools/omama/LICENSE", "immutable"),
)

GENERATED_LOCAL_INVENTORY = (
    {"destination": ".claude/settings.local.json", "kind": "owned-json-entry", "phase": "T7"},
    {"destination": ".omama/state.json", "kind": "generated-state", "phase": "T5"},
    {"destination": ".omama/install-journal.json", "kind": "generated-state", "phase": "T5"},
    {"destination": ".omama/install.lock", "kind": "generated-state", "phase": "T5"},
    {"destination": ".omama/runtime/", "kind": "generated-runtime", "phase": "T6"},
    {"destination": ".omama/cache/", "kind": "generated-cache", "phase": "T6"},
    {"destination": "core.hooksPath", "kind": "local-git-config", "phase": "T7"},
)

IDENTITY_INPUTS = (
    "pyproject.toml",
    "MANIFEST.in",
    "build_backend/backend.py",
    "build_backend/inventory.py",
    "cli/omama_cli/__init__.py",
    "cli/omama_cli/__main__.py",
    "cli/omama_cli/command.py",
    "cli/omama_cli/bundle.py",
    "cli/omama_cli/identity.py",
    "cli/omama_cli/target.py",
    "cli/omama_cli/install.py",
    "cli/omama_cli/runtime.py",
    "cli/omama_cli/wiring.py",
    "cli/omama_cli/doctor.py",
    "cli/omama_cli/selftest.py",
    "cli/README.md",
) + tuple(sorted({row[0] for row in SOURCE_INVENTORY}))
