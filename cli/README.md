# Omama CLI packaging surface

The package exposes `omama init [PATH] [--python ABSOLUTE_PATH] [--no-git-config]`
and `omama doctor [PATH] [--static-only]`, plus help and version. During the T3/T4
packaging boundary the two operational commands deliberately report `NOT-RUN` and
exit 2; installation, runtime provisioning, wiring, doctor checks, and admission are
owned by later checkpoints.

Builds generate the packaged payload from the authoritative repository files listed in
`build_backend/inventory.py`. `omama_cli.bundle.load_bundle()` reads only installed
package resources and verifies every recorded SHA-256 before exposing bytes. The manifest
distinguishes immutable vendored files, editable bootstrap material, generated wiring,
and later local state. `omama_cli.identity` supplies read-only conservative classifications;
it performs no installer writes.

Python 3.8+ and `PyYAML>=6.0.2,<7` are the runtime contract. The build-only backend is
constrained to `setuptools>=68,<76`. Local Python 3.11 execution remains a CI requirement;
this development host has no Python 3.11 interpreter.
