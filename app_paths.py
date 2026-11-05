"""Read-only application resources and writable user files, in source and frozen builds."""
from pathlib import Path
import os
import sys


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    return Path(sys._MEIPASS) if is_frozen() else Path(__file__).resolve().parent


def runtime_home() -> Path:
    configured = os.environ.get("SHOGI_ANALYZER_HOME", "").strip()
    base = Path(sys.executable).resolve().parent if is_frozen() else resource_root()
    if configured:
        path = Path(configured).expanduser()
        return (path if path.is_absolute() else base / path).resolve()
    return base
