"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Project root directory
BASE_DIR = Path(__file__).resolve().parent

# Load .env from project root
load_dotenv(BASE_DIR / ".env")


def _env_bool(key: str, default: bool = False) -> bool:
    """Parse boolean environment variable."""
    value = os.getenv(key, str(default)).strip().lower()
    return value in ("1", "true", "yes", "on")


def _env_float(key: str, default: float) -> float:
    """Parse float environment variable."""
    try:
        return float(os.getenv(key, str(default)))
    except ValueError:
        return default


def _env_int(key: str, default: int) -> int:
    """Parse integer environment variable."""
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Config:
    """Immutable application settings."""

    target_contact_name: str
    send_time: str
    headless: bool
    chrome_profile_path: Path
    wait_timeout: int
    retry_attempts: int
    type_delay_min: float
    type_delay_max: float

    # Paths
    base_dir: Path
    how_are_you_answers_path: Path
    data_dir: Path
    adjectives_path: Path
    used_adjectives_path: Path
    message_history_path: Path
    logs_dir: Path
    screenshots_dir: Path
    errors_dir: Path

    @classmethod
    def from_env(cls) -> Config:
        """Build configuration from environment variables."""
        base = BASE_DIR
        chrome_profile = Path(
            os.getenv("CHROME_PROFILE_PATH", "./chrome_profile")
        )
        if not chrome_profile.is_absolute():
            chrome_profile = base / chrome_profile

        return cls(
            target_contact_name=os.getenv("TARGET_CONTACT_NAME", "").strip(),
            send_time=os.getenv("SEND_TIME", "09:00").strip(),
            headless=_env_bool("HEADLESS", False),
            chrome_profile_path=chrome_profile,
            wait_timeout=_env_int("WAIT_TIMEOUT", 30),
            retry_attempts=_env_int("RETRY_ATTEMPTS", 3),
            type_delay_min=_env_float("TYPE_DELAY_MIN", 0.05),
            type_delay_max=_env_float("TYPE_DELAY_MAX", 0.15),
            base_dir=base,
            data_dir=base / "data",
            how_are_you_answers_path=base / "data" / "how_are_you_answers.json",
            adjectives_path=base / "data" / "adjectives.json",
            used_adjectives_path=base / "data" / "used_adjectives.json",
            message_history_path=base / "data" / "message_history.json",
            logs_dir=base / "logs",
            screenshots_dir=base / "screenshots",
            errors_dir=base / "errors",
        )

    def validate(self) -> None:
        """Raise ValueError if required settings are missing or invalid."""
        if not self.target_contact_name:
            raise ValueError(
                "TARGET_CONTACT_NAME is required. Copy .env.example to .env and set it."
            )
        parts = self.send_time.split(":")
        if len(parts) != 2:
            raise ValueError(f"Invalid SEND_TIME format: {self.send_time}. Use HH:MM.")
        hour, minute = int(parts[0]), int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f"Invalid SEND_TIME: {self.send_time}")
        if self.type_delay_min > self.type_delay_max:
            raise ValueError("TYPE_DELAY_MIN must be <= TYPE_DELAY_MAX")


def get_config() -> Config:
    """Return validated application configuration."""
    config = Config.from_env()
    config.validate()
    return config
