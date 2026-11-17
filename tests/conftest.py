"""Test fixtures.

By default tests run on a temporary SQLite file. Set TEST_DATABASE_URL to a PostgreSQL URL to run the SAME
tests on PostgreSQL, with the schema created by the real Alembic migration (so the migration is tested too):

    ALLOW_DESTRUCTIVE_TESTS=1 TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/mik_test python -m pytest

The target database is WIPED for every test. Safety (tests/safety.py): the name must be exactly `mik_test`, the host
must be local/throw-away (localhost, 127.0.0.1, ::1, db-test), and ALLOW_DESTRUCTIVE_TESTS=1 must be set.
"""
import copy
import os
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.safety import destructive_target_problem

ROOT = Path(__file__).resolve().parent.parent
REAL_DIR = ROOT / "questionnaire"
TEST_DB = os.environ.get("TEST_DATABASE_URL", "").strip() or None


def reset_postgres(url: str) -> None:
    """Drop everything in the test database and rebuild it with `alembic upgrade head`."""
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    problem = destructive_target_problem(url, os.environ)
    if problem:
        pytest.exit(f"Refusing to wipe the TEST_DATABASE_URL database: {problem}", 2)
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    old = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        command.upgrade(cfg, "head")
    finally:
        if old is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old


def pytest_configure(config):
    """Fail fast, before any test runs, if the PostgreSQL target is not an approved disposable database."""
    if TEST_DB:
        problem = destructive_target_problem(TEST_DB, os.environ)
        if problem:
            raise pytest.UsageError(f"Refusing to run against TEST_DATABASE_URL: {problem}")


@pytest.fixture
def qdir(tmp_path):
    d = tmp_path / "q"
    d.mkdir()
    (d / "daily_report.v1.yaml").write_text((REAL_DIR / "daily_report.v1.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    return d


@pytest.fixture
def db_url(tmp_path):
    if TEST_DB:
        reset_postgres(TEST_DB)
        return TEST_DB
    return f"sqlite:///{tmp_path / 't.db'}"


@pytest.fixture
def make_client(db_url, qdir):
    clients = []

    def _make(**overrides):
        settings = Settings(database_url=db_url, questionnaire_dir=qdir, **overrides)
        c = TestClient(create_app(settings, create_tables=not TEST_DB))
        c.__enter__()
        clients.append(c)
        return c

    yield _make
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def client(make_client):
    return make_client()


def write_version(qdir, version, mutate):
    d = yaml.safe_load((REAL_DIR / "daily_report.v1.yaml").read_text(encoding="utf-8"))
    d = copy.deepcopy(d)
    d["version"] = version
    mutate(d)
    (qdir / f"daily_report.v{version}.yaml").write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")


@pytest.fixture
def valid_payload():
    from app.validation import today_local

    return lambda client: {
        "questionnaire_version": 1,
        "respondent_name": "Тест Потребител",
        "department": "dept_1",
        "work_date": today_local("Europe/Sofia").isoformat(),
        "answers": {
            "tasks": "Синтетична задача",
            "recurring": "Синтетична повтаряща се дейност, 30 мин.",
            "obstacles": {"selected": ["waiting"], "texts": {}},
            "obstacles_detail": "",
            "suggestions": "",
        },
    }
