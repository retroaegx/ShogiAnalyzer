from __future__ import annotations

from pathlib import Path
from app_paths import runtime_home


def data_dir() -> Path:
    """server/data: DB, logs and other files the app creates (ignored by git)."""
    return runtime_home() / "server" / "data"
