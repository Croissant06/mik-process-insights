"""Application settings, read from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

BASE_DIR = Path(__file__).resolve().parent.parent
DEV_ENVS = {"dev", "development", "test"}
HOSTED_ENVS = {"staging", "production"}


class ConfigError(RuntimeError):
    """Raised at startup when the configuration is unsafe or incomplete."""


def _parse_backdate(raw: str | None) -> int | None:
    """Empty / unset / 'unlimited' means no limit; otherwise a number of days (0 = today only)."""
    if raw is None or raw.strip().lower() in ("", "unlimited", "none"):
        return None
    return max(0, int(raw))


def _parse_retention(raw: str | None) -> int:
    if raw is None or raw.strip() == "":
        return 90
    try:
        days = int(raw)
    except ValueError:
        raise ConfigError("RETENTION_DAYS must be a whole number of days.") from None
    if days < 7:
        raise ConfigError("RETENTION_DAYS must be at least 7.")
    return days


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
    environment: str = "development"
    public_origin: str | None = None
    attachment_scan_host: str | None = None
    attachment_scan_port: int = 3310
    # PROVISIONAL pilot retention (days from submission) for named reports and their attachments. Only used by the
    # owner-run review script scripts/retention_review.py; nothing is ever deleted automatically.
    retention_days: int = 90
    # Request header that carries the visitor's real IP, set ONLY by a proxy we trust (e.g. "CF-Connecting-IP" behind
    # the Cloudflare tunnel). Empty = use the TCP peer address. Without it, every visitor behind the tunnel shares one
    # address, so five wrong admin logins would lock out every admin. Only enable it when the app port is reachable
    # solely through that proxy (hosted compose binds it to 127.0.0.1), or the header could be forged.
    client_ip_header: str | None = None

    def __post_init__(self):
        if self.environment not in HOSTED_ENVS:
            return
        try:
            backend = make_url(self.database_url).get_backend_name()
        except ArgumentError:
            raise ConfigError("Hosted mode needs a valid PostgreSQL database URL.") from None
        if backend != "postgresql":
            raise ConfigError("Hosted mode requires PostgreSQL.")
        if not self.cookie_secure:
            raise ConfigError("Hosted mode requires COOKIE_SECURE=1 and HTTPS.")
        try:
            origin = urlsplit(self.public_origin or "")
            origin.port  # Validate an explicitly configured port.
        except ValueError:
            raise ConfigError("Set PUBLIC_ORIGIN to the application's HTTPS origin.") from None
        if (origin.scheme != "https" or not origin.hostname or origin.username is not None
                or origin.path or origin.query or origin.fragment
                or any(char.isspace() for char in self.public_origin or "")):
            raise ConfigError("Set PUBLIC_ORIGIN to the application's HTTPS origin.")

    @classmethod
    def from_env(cls, *, web: bool = True) -> "Settings":
        """`web=False` is for command-line scripts, which do not serve requests (no origin/cookie checks)."""
        active = os.environ.get("ACTIVE_QUESTIONNAIRE_VERSION")
        environment = os.environ.get("APP_ENV", "").strip().lower()
        settings = cls(
            database_url=database_url_from_env(),
            active_questionnaire_version=int(active) if active else None,
            max_backdate_days=_parse_backdate(os.environ.get("MAX_BACKDATE_DAYS")),
            cookie_secure=_parse_bool(os.environ.get("COOKIE_SECURE"), default=environment not in DEV_ENVS),
            allowed_origins=tuple(o.strip().rstrip("/") for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()),
            environment=environment,
            public_origin=os.environ.get("PUBLIC_ORIGIN", "").strip().rstrip("/") or None,
            attachment_scan_host=os.environ.get("ATTACHMENT_SCAN_HOST", "").strip() or None,
            attachment_scan_port=int(os.environ.get("ATTACHMENT_SCAN_PORT", "3310")),
            retention_days=_parse_retention(os.environ.get("RETENTION_DAYS")),
            client_ip_header=os.environ.get("CLIENT_IP_HEADER", "").strip() or None,
        )
        if web and environment not in DEV_ENVS:
            # Anything that is not local development is treated as real use: HTTPS only, exact trusted origins.
            if not settings.cookie_secure:
                raise ConfigError("COOKIE_SECURE must not be disabled outside APP_ENV=dev: admin sessions need HTTPS.")
            origins = (*settings.allowed_origins, *([settings.public_origin] if settings.public_origin else []))
            if not origins or any(not o.lower().startswith("https://") for o in origins):
                raise ConfigError(
                    "Outside APP_ENV=dev, PUBLIC_ORIGIN (or ALLOWED_ORIGINS) must give the exact public https:// origin, "
                    "e.g. PUBLIC_ORIGIN=https://reports.example.com"
                )
        return settings
