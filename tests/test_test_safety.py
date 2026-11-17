"""Regression tests for the destructive-test guard and the fail-closed form fallback."""
import pytest

from tests.safety import APPROVED_DB_NAME, OPT_IN_VAR, destructive_target_problem

OK_URL = f"postgresql+psycopg://test:test@db-test:5432/{APPROVED_DB_NAME}"
OPT = {OPT_IN_VAR: "1"}


def test_approved_disposable_database_is_accepted():
    assert destructive_target_problem(OK_URL, OPT) is None
    assert destructive_target_problem(f"postgresql+psycopg://u@127.0.0.1:5433/{APPROVED_DB_NAME}", OPT) is None


@pytest.mark.parametrize("name", ["mik", "mik_prod", "test", "mik_test2", "mik_test_x", "my_test_db", "MIK_TEST", ""])
def test_database_name_must_match_exactly(name):
    url = f"postgresql+psycopg://test:test@db-test:5432/{name}"
    assert destructive_target_problem(url, OPT)


@pytest.mark.parametrize("host", ["db", "prod.example.com", "10.0.0.5", "mik-server"])
def test_remote_or_application_hosts_are_refused(host):
    # `db` is the host of the real Compose database service: it must never be wipeable.
    assert destructive_target_problem(f"postgresql+psycopg://u:p@{host}:5432/{APPROVED_DB_NAME}", OPT)


def test_opt_in_is_required():
    assert destructive_target_problem(OK_URL, {})
    assert destructive_target_problem(OK_URL, {OPT_IN_VAR: "true"})
    assert destructive_target_problem(OK_URL, {OPT_IN_VAR: "0"})


def test_application_database_is_never_wiped():
    assert destructive_target_problem(OK_URL, {**OPT, "DATABASE_URL": OK_URL})


def test_non_postgres_and_garbage_urls_are_refused():
    assert destructive_target_problem("sqlite:///x.db", OPT)
    assert destructive_target_problem("not a url", OPT)


def test_compose_test_stack_is_approved_and_opted_in():
    import re
    from pathlib import Path

    text = (Path(__file__).resolve().parent.parent / "docker-compose.test.yml").read_text(encoding="utf-8")
    url = re.search(r"TEST_DATABASE_URL:\s*(\S+)", text).group(1)
    assert destructive_target_problem(url, {OPT_IN_VAR: re.search(rf"{OPT_IN_VAR}:\s*\"?(\w+)", text).group(1)}) is None


# --- form must fail closed without JavaScript (no GET with names/answers in the URL) ---

def test_form_has_post_fallback_and_never_get(client):
    html = client.get("/").text
    assert 'method="post"' in html and 'action="/js-required"' in html
    assert "<noscript>" in html and "JavaScript" in html


def test_js_required_stores_nothing_and_does_not_echo(client):
    secret = "Иван Петров ТАЙНА"
    r = client.post("/js-required", data={"respondent_name": secret, "tasks": secret})
    assert r.status_code == 400
    assert secret not in r.text and "no-store" in r.headers["cache-control"]
    with client.app.state.session_factory() as s:
        from sqlalchemy import func, select

        from app.models import Submission

        assert s.scalar(select(func.count()).select_from(Submission)) == 0


def test_query_string_is_never_echoed_or_stored(client):
    r = client.get("/", params={"respondent_name": "ТАЙНА-В-URL", "tasks": "ТАЙНА-В-URL"})
    assert "ТАЙНА-В-URL" not in r.text
