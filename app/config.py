"""Application settings, read from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _parse_backdate(raw: str | None) -> int | None:
    """Empty / unset / 'unlimited' means no limit; otherwise a number of days (0 = today only)."""
    if raw is None or raw.strip().lower() in ("", "unlimited", "none"):
        return None
    return max(0, int(raw))


@dataclass(frozen=True)
class Settings:
    database_url: str
    questionnaire_dir: Path = BASE_DIR / "questionnaire"
    active_questionnaire_version: int | None = None
    timezone: str = "Europe/Sofia"  # local "work date" zone; DB timestamps are always UTC
    max_backdate_days: int | None = None  # None = any past date (down to EARLIEST_WORK_DATE)

    @classmethod
    def from_env(cls) -> "Settings":
        active = os.environ.get("ACTIVE_QUESTIONNAIRE_VERSION")
        return cls(
            database_url=os.environ.get(
                "DATABASE_URL", f"sqlite:///{BASE_DIR / 'local-dev.db'}"
            ),
            active_questionnaire_version=int(active) if active else None,
            max_backdate_days=_parse_backdate(os.environ.get("MAX_BACKDATE_DAYS")),
        )
