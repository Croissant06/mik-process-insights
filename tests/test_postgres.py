"""PostgreSQL-only checks. Skipped unless TEST_DATABASE_URL points at a PostgreSQL test database."""
from datetime import timezone

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.db import Base
import app.models  # noqa: F401
from tests.conftest import TEST_DB

pytestmark = pytest.mark.skipif(
    not (TEST_DB and TEST_DB.startswith("postgresql")), reason="needs TEST_DATABASE_URL (PostgreSQL)"
)


@pytest.fixture
def engine(db_url):
    e = create_engine(db_url)
    yield e
    e.dispose()


def test_migration_matches_models(engine):
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def test_column_types(engine):
    cols = {c["name"]: str(c["type"]) for c in inspect(engine).get_columns("submissions")}
    assert cols["answers"] == "JSONB"
    with engine.connect() as conn:
        row = conn.execute(text(
            "select data_type from information_schema.columns "
            "where table_name='submissions' and column_name='submitted_at'")).scalar()
    assert row == "timestamp with time zone"


def test_department_is_not_null_in_database(engine):
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text(
                "insert into questionnaire_versions(version, definition, checksum, created_at) "
                "values (1, '{}', 'x', now())"))
            conn.execute(text(
                "insert into submissions(id, questionnaire_version, work_date, submitted_at, department_code, answers) "
                "values ('a', 1, current_date, now(), NULL, '{}')"))


def test_roundtrip_utc_and_jsonb_query(make_client, valid_payload, engine):
    c = make_client()
    r = c.post("/api/submissions", json=valid_payload(c))
    assert r.status_code in (200, 201), r.text
    with engine.connect() as conn:
        ts = conn.execute(text("select submitted_at from submissions")).scalar()
        n = conn.execute(text("select count(*) from submissions where answers ? 'tasks'")).scalar()
        enc = conn.execute(text("show server_encoding")).scalar()
    assert ts.tzinfo is not None and ts.utcoffset() == timezone.utc.utcoffset(None)
    assert n == 1
    assert enc == "UTF8"
