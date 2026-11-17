import copy
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.models import Submission
from tests.conftest import write_version


def post(client, payload):
    return client.post("/api/submissions", json=payload)


def test_form_page_renders_bulgarian(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Дневник на работните дейности" in r.text
    assert "Изпрати дневен отчет" in r.text


def test_valid_submission_is_stored_with_utc_timestamp(client, valid_payload):
    r = post(client, valid_payload(client))
    assert r.status_code == 201
    with client.app.state.session_factory() as s:
        row = s.get(Submission, r.json()["id"])
        assert row.questionnaire_version == 1
        assert row.department_code == "dept_1"
        assert row.answers["obstacles"]["selected"] == ["waiting"]
        assert row.submitted_at.utcoffset() in (None, timedelta(0))
        assert abs(row.submitted_at.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)) < timedelta(minutes=1)


def test_required_fields_enforced_on_backend(client, valid_payload):
    p = valid_payload(client)
    p["respondent_name"] = "   "
    p["department"] = ""
    p["answers"]["tasks"] = ""
    p["answers"]["obstacles"] = {"selected": [], "texts": {}}
    r = post(client, p)
    assert r.status_code == 422
    assert set(r.json()["errors"]) == {"respondent_name", "department", "tasks", "obstacles"}


def test_unknown_department_and_option_rejected(client, valid_payload):
    p = valid_payload(client)
    p["department"] = "nope"
    p["answers"]["obstacles"] = {"selected": ["nope"], "texts": {}}
    errs = post(client, p).json()["errors"]
    assert "department" in errs and "obstacles" in errs


def test_exclusive_option_and_other_text(client, valid_payload):
    p = valid_payload(client)
    p["answers"]["obstacles"] = {"selected": ["none", "waiting"], "texts": {}}
    assert "obstacles" in post(client, p).json()["errors"]
    p["answers"]["obstacles"] = {"selected": ["other"], "texts": {"other": " "}}
    assert "obstacles.other" in post(client, p).json()["errors"]
    p["answers"]["obstacles"] = {"selected": ["other"], "texts": {"other": "Нещо друго"}}
    assert post(client, p).status_code == 201


def test_too_long_text_rejected(client, valid_payload):
    p = valid_payload(client)
    p["answers"]["tasks"] = "а" * 2001
    assert "tasks" in post(client, p).json()["errors"]


def test_work_date_window_uses_sofia_calendar(client, valid_payload):
    p = valid_payload(client)
    p["work_date"] = (datetime.fromisoformat(p["work_date"]) + timedelta(days=1)).date().isoformat()
    assert "work_date" in post(client, p).json()["errors"]  # future
    p["work_date"] = (datetime.fromisoformat(p["work_date"]) - timedelta(days=5)).date().isoformat()
    assert "work_date" in post(client, p).json()["errors"]  # too old
    p["work_date"] = "not-a-date"
    assert "work_date" in post(client, p).json()["errors"]


def test_sofia_vs_utc_day_boundary():
    from datetime import date

    from app.validation import today_local

    late_utc = datetime(2026, 11, 17, 22, 30, tzinfo=timezone.utc)  # 00:30 on the 18th in Sofia
    assert today_local("Europe/Sofia", late_utc) == date(2026, 11, 18)


def test_name_can_be_optional(make_client, qdir, valid_payload):
    def mutate(d):
        d["respondent"]["name"]["required"] = False

    write_version(qdir, 2, mutate)
    c = make_client()
    p = valid_payload(c)
    p["questionnaire_version"] = 2
    p["respondent_name"] = ""
    r = post(c, p)
    assert r.status_code == 201
    with c.app.state.session_factory() as s:
        assert s.get(Submission, r.json()["id"]).respondent_name is None


def test_old_version_stays_interpretable(make_client, qdir, valid_payload):
    c = make_client()
    old = post(c, valid_payload(c))
    assert old.status_code == 201

    def mutate(d):
        d["questions"][0]["label"] = "Нов текст на въпроса"

    write_version(qdir, 2, mutate)
    c2 = make_client()  # restart with new file
    assert c2.get("/api/questionnaire").json()["version"] == 2
    with c2.app.state.session_factory() as s:
        row = s.get(Submission, old.json()["id"])
        assert row.questionnaire_version == 1
        from app import questionnaire

        assert questionnaire.get_version(s, 1)["questions"][0]["label"] == "Основни задачи през деня"
    # a form rendered before the change can still be submitted against v1
    assert post(c2, valid_payload(c2)).status_code == 201


def test_published_version_is_immutable(make_client, qdir):
    make_client()
    f = qdir / "daily_report.v1.yaml"
    f.write_text(f.read_text(encoding="utf-8").replace("Основни задачи през деня", "Променено"), encoding="utf-8")
    import pytest

    from app.questionnaire import QuestionnaireError

    with pytest.raises(QuestionnaireError):
        make_client()


def test_unknown_questionnaire_version_rejected(client, valid_payload):
    p = valid_payload(client)
    p["questionnaire_version"] = 99
    assert post(client, p).status_code == 422


def test_malformed_body(client):
    assert client.post("/api/submissions", content=b"not json").status_code == 400
    assert post(client, ["x"]).status_code == 422
