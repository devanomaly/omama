"""Assert source static-only launches no installed interpreter/artifact probe."""

import argparse
import json
import sys
import zipfile
from pathlib import Path
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--wheel", required=True)
    args = parser.parse_args()
    cli_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(cli_root))
    from omama_cli import doctor as doctor_module
    from omama_cli.bundle import _validate_manifest
    from omama_cli.target import resolve_target

    with zipfile.ZipFile(args.wheel) as archive:
        raw = archive.read("omama_cli/_payload/manifest.json")
        bundle = _validate_manifest(
            json.loads(raw.decode("utf-8")),
            lambda name: archive.read("omama_cli/_payload/" + name), raw,
        )
    with patch.object(doctor_module, "_probe", wraps=doctor_module._probe) as interpreter_probe:
        with patch.object(doctor_module, "_run", wraps=doctor_module._run) as artifact_probe:
            report = doctor_module.doctor(resolve_target(args.target), bundle, static_only=True)
    result = {
        "exit": report.exit_code,
        "interpreter_probe_calls": interpreter_probe.call_count,
        "artifact_probe_calls": artifact_probe.call_count,
    }
    print(json.dumps(result, sort_keys=True))
    return 0 if result == {"exit": 2, "interpreter_probe_calls": 0, "artifact_probe_calls": 0} else 1


if __name__ == "__main__":
    raise SystemExit(main())
