"""The installed distribution version."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("dpm-synth")
except PackageNotFoundError:  # pragma: no cover - not installed
    __version__ = "0+unknown"
