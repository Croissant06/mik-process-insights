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


def _parse_bool(raw: str | None, *, default: bool) -> bool:
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


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
    # Exact browser origins allowed to POST (e.g. "https://reports.example.com"). When set, ONLY these are accepted;
    # when empty (local development) the request's own Host is accepted.
    allowed_origins: tuple[str, ...] = ()
    max_json_body_bytes: int = 256 * 1024
    # Admin session cookie "Secure" flag. Must be true whenever the site is served over HTTPS.
    cookie_secure: bool = False

    @classmethod
    def from_env(cls, *, web: bool = True) -> "Settings":
        """`web=False` is for command-line scripts, which do not serve requests (no origin/cookie checks)."""
        active = os.environ.get("ACTIVE_QUESTIONNAIRE_VERSION")
        settings = cls(
            database_url=database_url_from_env(),
            active_questionnaire_version=int(active) if active else None,
            max_backdate_days=_parse_backdate(os.environ.get("MAX_BACKDATE_DAYS")),
            cookie_secure=_parse_bool(os.environ.get("COOKIE_SECURE"), default=os.environ.get("APP_ENV", "").strip().lower() not in DEV_ENVS),
            allowed_origins=tuple(o.strip().rstrip("/") for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()),
        )
        if web and os.environ.get("APP_ENV", "").strip().lower() not in DEV_ENVS:
            # Anything that is not local development is treated as real use: HTTPS only, exact trusted origins.
            if not settings.cookie_secure:
                raise ConfigError("COOKIE_SECURE must not be disabled outside APP_ENV=dev: admin sessions need HTTPS.")
            if not settings.allowed_origins or any(not o.lower().startswith("https://") for o in settings.allowed_origins):
                raise ConfigError(
                    "Outside APP_ENV=dev, ALLOWED_ORIGINS must list the exact public https:// origin(s), "
                    "e.g. ALLOWED_ORIGINS=https://reports.example.com"
                )
        return settings
