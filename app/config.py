"""Application settings, read from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    database_url: str
    questionnaire_dir: Path = BASE_DIR / "questionnaire"
    active_questionnaire_version: int | None = None
    timezone: str = "Europe/Sofia"  # local "work date" zone; DB timestamps are always UTC
    max_backdate_days: int = 7

    @classmethod
    def from_env(cls) -> "Settings":
        active = os.environ.get("ACTIVE_QUESTIONNAIRE_VERSION")
        return cls(
            database_url=os.environ.get(
                "DATABASE_URL", f"sqlite:///{BASE_DIR / 'local-dev.db'}"
            ),
            active_questionnaire_version=int(active) if active else None,
            max_backdate_days=int(os.environ.get("MAX_BACKDATE_DAYS", "7")),
        )
