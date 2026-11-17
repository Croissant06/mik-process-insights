"""Application settings, read from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import URL

BASE_DIR = Path(__file__).resolve().parent.parent
DEV_ENVS = {"dev", "development", "test"}


class ConfigError(RuntimeError):
    """Raised at startup when the configuration is unsafe or incomplete."""


def _parse_backdate(raw: str | None) -> int | None:
    """Empty / unset / 'unlimited' means no limit; otherwise a number of days (0 = today only)."""
    if raw is None or raw.strip().lower() in ("", "unlimited", "none"):
        return None
    return max(0, int(raw))


def database_url_from_env(env: dict[str, str] | None = None) -> str:
    """Resolve the database URL.

    1. DATABASE_URL, if set (full SQLAlchemy URL; takes precedence).
    2. Otherwise built from POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB (+ POSTGRES_HOST, POSTGRES_PORT).
       The URL is built with SQLAlchemy so special characters in the password are escaped correctly.
    3. Otherwise a local SQLite file, but ONLY when APP_ENV is dev/development/test.
       Anywhere else the app refuses to start: a silent SQLite fallback inside a container
       would lose all data on rebuild.
    """
    env = os.environ if env is None else env
    url = env.get("DATABASE_URL", "").strip()
    if url:
        return url
    user, password, db = env.get("POSTGRES_USER"), env.get("POSTGRES_PASSWORD"), env.get("POSTGRES_DB")
    if user and password and db:
        return URL.create(
            "postgresql+psycopg",
            username=user,
            password=password,
            host=env.get("POSTGRES_HOST", "db"),
            port=int(env.get("POSTGRES_PORT", "5432")),
            database=db,
        ).render_as_string(hide_password=False)
    if env.get("APP_ENV", "").strip().lower() in DEV_ENVS:
        return f"sqlite:///{BASE_DIR / 'local-dev.db'}"
    raise ConfigError(
        "No database configured. Set DATABASE_URL, or POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB "
        "(see .env.example). For throw-away local development without PostgreSQL set APP_ENV=dev "
        "to use a local SQLite file."
    )


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
            database_url=database_url_from_env(),
            active_questionnaire_version=int(active) if active else None,
            max_backdate_days=_parse_backdate(os.environ.get("MAX_BACKDATE_DAYS")),
        )
