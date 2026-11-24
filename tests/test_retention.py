"""Provisional 90-day retention: configurable, owner-run, dry-run by default, deletion doubly gated."""
import importlib.util
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.config import ConfigError, Settings
from app.models import AdminAudit, ReportAttachment, Submission


def load_cli():
    spec = importlib.util.spec_from_file_location("retention_review", Path(__file__).resolve().parent.parent / "scripts" / "retention_review.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def aged(client, valid_payload):
    """Three reports submitted 200, 91 and 89 days ago; the two oldest have a file each."""
    now = datetime.now(timezone.utc)
    ids = []
    for days, name in [(200, "Много Стар"), (91, "Стар"), (89, "Нов")]:
        r = client.post("/api/submissions", json={**valid_payload(client), "respondent_name": name,
                                                  "idempotency_key": str(uuid.uuid4())})
        ids.append(r.json()["id"])
    with client.app.state.session_factory() as db:
        for sid, days in zip(ids, (200, 91, 89)):
            db.get(Submission, sid).submitted_at = now - timedelta(days=days)
            if days > 90:
                db.add(ReportAttachment(submission_id=sid, filename="f.bin", content=b"x" * 1000))
        db.commit()
    return client


def total(client, model=Submission):
    with client.app.state.session_factory() as db:
        return db.scalar(select(func.count()).select_from(model))


def test_default_period_is_90_days_and_configurable(monkeypatch):
    monkeypatch.delenv("RETENTION_DAYS", raising=False)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("APP_ENV", "dev")
    assert Settings.from_env().retention_days == 90 and Settings(database_url="sqlite://").retention_days == 90
    monkeypatch.setenv("RETENTION_DAYS", "120")
    assert Settings.from_env().retention_days == 120
    for bad in ("3", "abc"):
        monkeypatch.setenv("RETENTION_DAYS", bad)
        with pytest.raises(ConfigError):
            Settings.from_env()


def test_review_counts_by_submission_time_and_changes_nothing(aged):
    mod = load_cli()
    with aged.app.state.session_factory() as db:
        r = mod.review(db, 90)
    assert (r["reports"], r["attachments"], r["bytes"]) == (2, 2, 2000)
    assert total(aged) == 3 and total(aged, ReportAttachment) == 2
    with aged.app.state.session_factory() as db:
        assert mod.review(db, 365)["reports"] == 0 and mod.review(db, 30)["reports"] == 3


def test_cli_is_a_dry_run_by_default_and_prints_no_personal_data(aged, monkeypatch, capsys, db_url):
    monkeypatch.setenv("DATABASE_URL", db_url)
    assert load_cli().main([]) == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "2 reports" in out and "Стар" not in out and "f.bin" not in out
    assert total(aged) == 3


@pytest.mark.parametrize("argv,env", [(["--delete"], {}), (["--delete", "--i-am-the-operator"], {}),
                                       (["--delete"], {"RETENTION_DELETION_APPROVED": "1"}),
                                       (["--delete", "--i-am-the-operator"], {"RETENTION_DELETION_APPROVED": "yes"})])
def test_deletion_needs_both_confirmations(aged, monkeypatch, db_url, argv, env):
    monkeypatch.setenv("DATABASE_URL", db_url)
    assert load_cli().main(argv, env=env) == 2
    assert total(aged) == 3


def test_period_below_seven_days_is_refused(aged, monkeypatch, db_url):
    monkeypatch.setenv("DATABASE_URL", db_url)
    assert load_cli().main(["--days", "1", "--delete", "--i-am-the-operator"],
                           env={"RETENTION_DELETION_APPROVED": "1"}) == 2 and total(aged) == 3


def test_confirmed_deletion_removes_only_expired_reports_and_their_files(aged, monkeypatch, db_url):
    monkeypatch.setenv("DATABASE_URL", db_url)
    assert load_cli().main(["--delete", "--i-am-the-operator"], env={"RETENTION_DELETION_APPROVED": "1"}) == 0
    assert total(aged) == 1 and total(aged, ReportAttachment) == 0
    with aged.app.state.session_factory() as db:
        assert db.scalar(select(Submission.respondent_name)) == "Нов"
        audit = db.scalar(select(AdminAudit).where(AdminAudit.action == "retention_deleted"))
        assert audit.detail == "reports=2 attachments=2 days=90" and audit.user_id is None
