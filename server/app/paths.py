from __future__ import annotations

from pathlib import Path


def data_dir() -> Path:
    """server/data: DB, logs and other files the app creates (ignored by git)."""
    return Path(__file__).resolve().parents[1] / "data"
