"""Regression tests for the technical audit findings H1, H3, H4, H5 and M6 (run on SQLite and PostgreSQL)."""
import json
import re
import unicodedata

import pytest
from sqlalchemy.engine import make_url

from app import questionnaire
from app.config import ConfigError, database_url_from_env
from app.models import Submission
from app.validation import validate_submission
from tests.conftest import ROOT, write_version

HEADERS = {"Content-Type": "application/json"}


def post(client, payload):
    return client.post("/api/submissions", json=payload)


# ---------------------------------------------------------------- H1: configuration must fit the database
@pytest.mark.parametrize(
    "mutate, expected",
    [
        (lambda d: d["respondent"]["name"].update(max_length=200), "max_length"),
        (lambda d: d["respondent"]["name"].update(max_length=0), "max_length"),
        (lambda d: d["respondent"]["name"].update(max_length=True), "max_length"),
        (lambda d: d["respondent"]["department"].update(required=False), "department.required"),
        (lambda d: d["questions"][0].update(max_length=10**9), "max_length"),
        (lambda d: d["questions"][0].update(max_length="abc"), "max_length"),
    ],
)
def test_check_definition_rejects_settings_the_database_cannot_store(make_client, qdir, mutate, expected):
    write_version(qdir, 2, mutate)
    with pytest.raises(questionnaire.QuestionnaireError, match=expected):
        make_client()


def test_name_limit_cannot_exceed_column_even_if_definition_is_bypassed():
    from datetime import date

    d = {"respondent": {"name": {"label": "n", "required": True, "max_length": 500}, "department": {"label": "d"}},
         "departments": {"options": [{"code": "dept_1", "label": "x"}]}, "questions": []}
    clean, errors = validate_submission(
        d, {"respondent_name": "я" * 121, "department": "dept_1", "work_date": "2026-11-17", "answers": {}},
        today=date(2026, 11, 17), max_backdate_days=None)
    assert clean is None and "respondent_name" in errors


def test_name_of_exactly_120_characters_is_stored(client, valid_payload):
    p = valid_payload(client)
    p["respondent_name"] = "Я" * 120
    r = post(client, p)
    assert r.status_code == 201
    with client.app.state.session_factory() as s:
        assert len(s.get(Submission, r.json()["id"]).respondent_name) == 120


# ---------------------------------------------------------------- H3: malformed Unicode
@pytest.mark.parametrize("field", ["respondent_name", "tasks", "other_text"])
def test_lone_surrogate_is_a_validation_error_not_a_500(client, valid_payload, field):
    p = valid_payload(client)
    bad = "abc\ud800def"
    if field == "respondent_name":
        p["respondent_name"] = bad
    elif field == "tasks":
        p["answers"]["tasks"] = bad
    else:
        p["answers"]["obstacles"] = {"selected": ["other"], "texts": {"other": bad}}
    r = client.post("/api/submissions", content=json.dumps(p).encode("utf-8"), headers=HEADERS)
    assert r.status_code == 422, r.text
    assert "ud800" not in r.text and "abc" not in r.text  # the value is never echoed back


def test_surrogate_in_department_and_date_is_rejected(client, valid_payload):
    p = valid_payload(client)
    p["department"] = "\ud800"
    p["work_date"] = "2026-11-\ud800"
    errs = client.post("/api/submissions", content=json.dumps(p).encode(), headers=HEADERS).json()["errors"]
    assert "department" in errs and "work_date" in errs


def test_nul_is_stripped_and_text_is_normalised_to_nfc(client, valid_payload):
    p = valid_payload(client)
    decomposed = unicodedata.normalize("NFD", "Йордан")  # И + combining breve
    assert decomposed != "Йордан"
    p["respondent_name"] = decomposed
    p["answers"]["tasks"] = "ab\x00cd"
    r = post(client, p)
    assert r.status_code == 201
    with client.app.state.session_factory() as s:
        row = s.get(Submission, r.json()["id"])
        assert row.respondent_name == "Йордан" and row.answers["tasks"] == "abcd"


# ---------------------------------------------------------------- H4: no silent SQLite, DB-aware health check
def test_missing_database_configuration_is_an_error():
    with pytest.raises(ConfigError, match="No database configured"):
        database_url_from_env({})
    with pytest.raises(ConfigError):
        database_url_from_env({"APP_ENV": "production"})
    with pytest.raises(ConfigError):  # incomplete POSTGRES_* values are not enough
        database_url_from_env({"POSTGRES_USER": "u", "POSTGRES_DB": "d"})


def test_sqlite_only_with_explicit_dev_mode():
    for env in ("dev", "development", "test", "Development"):
        assert database_url_from_env({"APP_ENV": env}).startswith("sqlite:///")


def test_healthz_checks_the_database(client, monkeypatch):
    assert client.get("/healthz").json() == {"status": "ok"}

    class Broken:
        def connect(self):
            raise RuntimeError("connection to server at 10.0.0.5 password=secret failed")

    monkeypatch.setattr(client.app.state, "engine", Broken())
    r = client.get("/healthz")
    assert r.status_code == 503 and r.json() == {"status": "error"}
    assert "secret" not in r.text and "10.0.0.5" not in r.text


# ---------------------------------------------------------------- M6: credentials
def test_database_url_takes_precedence():
    env = {"DATABASE_URL": "postgresql+psycopg://a:b@h:1/d", "POSTGRES_USER": "u", "POSTGRES_PASSWORD": "p", "POSTGRES_DB": "x"}
    assert database_url_from_env(env) == "postgresql+psycopg://a:b@h:1/d"


def test_url_is_built_from_parts_and_escapes_special_characters():
    password = "p@ss:w/rd%1 #?&"
    url = make_url(database_url_from_env({"POSTGRES_USER": "mik", "POSTGRES_PASSWORD": password, "POSTGRES_DB": "mik_insights"}))
    assert (url.drivername, url.username, url.password, url.host, url.port, url.database) == (
        "postgresql+psycopg", "mik", password, "db", 5432, "mik_insights")
    url2 = make_url(database_url_from_env({"POSTGRES_USER": "u", "POSTGRES_PASSWORD": "p", "POSTGRES_DB": "d",
                                           "POSTGRES_HOST": "localhost", "POSTGRES_PORT": "5433"}))
    assert (url2.host, url2.port) == ("localhost", 5433)


def test_env_example_has_no_duplicated_password_and_no_real_secret():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    active = [l for l in text.splitlines() if l and not l.startswith("#")]
    assert not any(l.startswith("DATABASE_URL=") for l in active)  # password is written once
    assert "POSTGRES_PASSWORD=change-me-locally" in active


# ---------------------------------------------------------------- H5: reproducible builds
def test_lock_files_are_fully_pinned_with_hashes():
    for name in ("requirements.txt", "requirements-dev.txt"):
        text = (ROOT / name).read_text(encoding="utf-8")
        packages = [m for m in re.findall(r"^([A-Za-z0-9_.\-]+)==", text, flags=re.M)]
        assert packages, name
        blocks = re.split(r"\n(?=[A-Za-z0-9_.\-]+==)", text)
        for block in blocks[1:]:
            assert "--hash=sha256:" in block, f"{name}: unhashed entry {block.splitlines()[0]}"
        assert not re.findall(r"^\s*[A-Za-z0-9_.\-]+(>=|~=|<)", text, flags=re.M), f"{name} has unpinned ranges"


def test_dockerfile_installs_only_from_the_lock():
    df = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert df.count("--require-hashes") >= 2
    assert not re.search(r"pip install [\"']?(fastapi|sqlalchemy|uvicorn)", df)
    assert "requirements-dev.txt" in df and "AS runtime" in df
