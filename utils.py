"""Shared utility functions for file I/O and helpers."""

from __future__ import annotations

import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")


def load_json(path: Path, default: T) -> T:
    """
    Load JSON file or return default if missing/invalid.

    Args:
        path: Path to JSON file.
        default: Value returned when file cannot be read.

    Returns:
        Parsed JSON data or default.
    """
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def save_json(path: Path, data: Any) -> None:
    """
    Write data to JSON file with pretty formatting.

    Args:
        path: Destination path.
        data: Serializable Python object.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def random_delay(min_sec: float, max_sec: float) -> None:
    """Sleep for a random duration between min and max seconds."""
    time.sleep(random.uniform(min_sec, max_sec))


def ensure_directories(*paths: Path) -> None:
    """Create directories if they do not exist."""
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)
