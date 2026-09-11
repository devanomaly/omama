"""Omama command-line package."""

# One authoritative version. At runtime the installed distribution's own
# metadata is the authority, so the CLI can never report a version the
# installed artifact does not carry. The literal below is the fallback for
# running from a source checkout that was never installed; build and test
# equality assertions keep it equal to pyproject.toml, the build inventory and
# the generated manifest.
_SOURCE_VERSION = "0.1.0"


def _resolve_version():
    try:
        from importlib import metadata
    except ImportError:  # pragma: no cover - Python < 3.8 is below the floor
        return _SOURCE_VERSION
    try:
        return metadata.version("omama")
    except Exception:
        return _SOURCE_VERSION


__version__ = _resolve_version()
