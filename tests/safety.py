"""Guard for the destructive PostgreSQL test mode.

The PostgreSQL tests DROP and recreate the `public` schema of TEST_DATABASE_URL for every test, so the target
must be provably disposable. All three conditions must hold:

1. the database name is exactly `mik_test`;
2. the host is one of the local/throw-away hosts below (never a remote server);
3. the operator opted in explicitly with ALLOW_DESTRUCTIVE_TESTS=1.

The check is a pure function so it is itself unit-tested (tests/test_test_safety.py).
"""
from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

APPROVED_DB_NAME = "mik_test"
APPROVED_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "db-test"})
OPT_IN_VAR = "ALLOW_DESTRUCTIVE_TESTS"


_LOCAL = {"localhost", "127.0.0.1", "::1"}


def _target(u) -> tuple[str, int, str]:
    """(host, port, database) with the local aliases and the default port normalised."""
    host = "localhost" if (u.host or "localhost") in _LOCAL else u.host
    return (host, u.port or 5432, u.database or "")


def destructive_target_problem(url: str, env: Mapping[str, str]) -> str | None:
    """Return why `url` must NOT be wiped, or None if it is an approved disposable test database."""
    try:
        u = make_url(url)
    except ArgumentError:
        return "TEST_DATABASE_URL is not a valid database URL."
    if not u.drivername.startswith("postgresql"):
        return "TEST_DATABASE_URL must be a PostgreSQL URL."
    if u.database != APPROVED_DB_NAME:
        return f"database name must be exactly {APPROVED_DB_NAME!r}, got {u.database!r}."
    if (u.host or "") not in APPROVED_HOSTS:
        return f"host must be one of {sorted(APPROVED_HOSTS)}, got {u.host!r}."
    # libpq lets query parameters (host=, hostaddr=, dbname=, service=, options=...) override the URL's host and
    # database, which would defeat the checks above. The approved target needs none, so none are allowed.
    if u.query:
        return f"connection-string parameters are not allowed, got {sorted(u.query)}."
    # Never wipe the database the app itself is configured to use: compare the effective target, not the text.
    app_url = env.get("DATABASE_URL", "").strip()
    if app_url:
        try:
            a = make_url(app_url)
        except ArgumentError:
            return "DATABASE_URL is set but is not a valid URL; refusing to guess."
        if a.drivername.startswith("postgresql") and _target(a) == _target(u):
            return "TEST_DATABASE_URL points at the same database as DATABASE_URL (the application database)."
    if env.get(OPT_IN_VAR) != "1":
        return f"set {OPT_IN_VAR}=1 to confirm that this database may be wiped on every test."
    return None
