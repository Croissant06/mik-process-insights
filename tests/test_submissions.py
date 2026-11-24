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


def freeze_today(monkeypatch, d):
    monkeypatch.setattr("app.routes.api.today_local", lambda tz: d)
    monkeypatch.setattr("app.routes.pages.today_local", lambda tz: d)


def test_work_date_window_is_configurable(make_client, valid_payload, monkeypatch):
    from datetime import date

    freeze_today(monkeypatch, date(2026, 11, 17))
    c = make_client(max_backdate_days=7)
    p = valid_payload(c)
    for ok in ("2026-11-17", "2026-11-10", "2026-11-16"):  # today, the earliest allowed day, yesterday
        p["work_date"] = ok
        assert post(c, p).status_code == 201, ok
    for bad in ("2026-11-09", "2026-11-18", "2027-01-01", "2026-02-30", "17.11.2026", ""):
        p["work_date"] = bad
        r = post(c, p)
        assert r.status_code == 422 and "work_date" in r.json()["errors"], bad
    p["work_date"] = "2026-11-09"
    assert "10.11.2026" in post(c, p).json()["errors"]["work_date"]  # message names the window, DD.MM.YYYY
    assert "17.11.2026" in post(c, p).json()["errors"]["work_date"]


def test_backdating_zero_means_today_only(make_client, valid_payload, monkeypatch):
    from datetime import date

    freeze_today(monkeypatch, date(2026, 11, 17))
    c = make_client(max_backdate_days=0)
    p = valid_payload(c)
    p["work_date"] = "2026-11-16"
    assert "work_date" in post(c, p).json()["errors"]
    p["work_date"] = "2026-11-17"
    assert post(c, p).status_code == 201


def test_default_has_no_backdate_limit_but_never_future(make_client, valid_payload, monkeypatch):
    from datetime import date

    from app.config import Settings

    assert Settings(database_url="sqlite://").max_backdate_days is None
    freeze_today(monkeypatch, date(2026, 11, 17))
    c = make_client()
    p = valid_payload(c)
    for ok in ("2026-11-17", "2026-06-01", "2020-01-01", "2019-12-31", "1999-05-05"):
        p["work_date"] = ok
        assert post(c, p).status_code == 201, ok
    for bad in ("2026-11-18", "2027-01-01", "9999-12-31"):  # future dates only; there is no earliest date
        p["work_date"] = bad
        assert "work_date" in post(c, p).json()["errors"], bad


def test_env_parsing_of_backdate_setting():
    from app.config import _parse_backdate

    assert _parse_backdate(None) is None and _parse_backdate("") is None and _parse_backdate("unlimited") is None
    assert _parse_backdate("0") == 0 and _parse_backdate("14") == 14


def test_date_picker_uses_server_side_sofia_date(make_client, monkeypatch):
    from datetime import date

    freeze_today(monkeypatch, date(2026, 11, 18))
    html = make_client(max_backdate_days=7).get("/").text
    assert "Дата на отчета" in html
    assert 'data-today="2026-11-18"' in html and 'data-min="2026-11-11"' in html
    assert 'value="2026-11-18"' in html and ">18.11.2026<" in html
    assert 'name="work_date"' in html and 'id="work_date" name="work_date"' in html
    assert "до 7 дни назад" in html


def test_unlimited_picker_has_no_earliest_date_and_no_hint(make_client, monkeypatch):
    from datetime import date

    freeze_today(monkeypatch, date(2026, 11, 18))
    html = make_client().get("/").text
    assert "data-min" not in html and "2020" not in html and "дни назад" not in html


def test_picker_defaults_to_sofia_not_utc_day(make_client, monkeypatch):
    # 22:30 UTC on 17 Nov is already 18 Nov in Sofia (UTC+2)
    from datetime import datetime, timezone

    import app.validation as v

    real = v.today_local
    late = datetime(2026, 11, 17, 22, 30, tzinfo=timezone.utc)
    monkeypatch.setattr("app.routes.pages.today_local", lambda tz: real(tz, late))
    assert 'data-today="2026-11-18"' in make_client().get("/").text


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
    assert client.post("/api/submissions", content=b"not json", headers={"content-type": "application/json"}).status_code == 400
    assert post(client, ["x"]).status_code == 422


def test_management_questionnaire_doc_is_up_to_date():
    """docs/business/QUESTIONNAIRE_BG.md is generated from the YAML; fail if someone edits one without the other."""
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    r = subprocess.run([sys.executable, str(root / "scripts" / "generate_questionnaire_doc.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_very_old_valid_dates_are_accepted_when_backdating_is_unlimited(make_client, valid_payload, monkeypatch):
    from datetime import date

    freeze_today(monkeypatch, date(2026, 11, 19))
    c = make_client()
    p = valid_payload(c)
    for ok in ("2026-11-19", "1990-02-28", "0100-01-01"):
        p["work_date"] = ok
        assert post(c, p).status_code == 201, ok
    for bad in ("2026-11-20", "2026-02-30", "not-a-date"):
        p["work_date"] = bad
        assert "work_date" in post(c, p).json()["errors"], bad
