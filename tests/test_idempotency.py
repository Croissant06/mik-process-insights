"""Safe retries: same key + same content = one report (200), same key + changed content = 409, no key = old behaviour."""
import uuid

import pytest
from sqlalchemy import func, select

from app import attachments
from app.models import ReportAttachment, Submission
from tests.conftest import write_version
from tests.test_attachments import with_file


def count(client, model=Submission):
    with client.app.state.session_factory() as db:
        return db.scalar(select(func.count()).select_from(model))


def keyed(client, valid_payload, key=None, **over):
    p = {**valid_payload(client), **over}
    p["idempotency_key"] = key or str(uuid.uuid4())
    return p


def test_retry_with_same_key_and_content_stores_one_report(client, valid_payload):
    p = keyed(client, valid_payload)
    first = client.post("/api/submissions", json=p)
    again = client.post("/api/submissions", json=p)
    assert first.status_code == 201 and again.status_code == 200
    assert again.json() == {"id": first.json()["id"], "duplicate": True}
    assert count(client) == 1


def test_same_key_with_changed_content_is_a_conflict(client, valid_payload):
    p = keyed(client, valid_payload)
    assert client.post("/api/submissions", json=p).status_code == 201
    changed = {**p, "respondent_name": "Друго Име"}
    r = client.post("/api/submissions", json=changed)
    assert r.status_code == 409 and "_form" in r.json()["errors"]
    assert count(client) == 1
    with client.app.state.session_factory() as db:
        assert db.scalar(select(Submission.respondent_name)) != "Друго Име"


def test_different_keys_are_separate_reports_and_no_key_still_works(client, valid_payload):
    base = valid_payload(client)
    assert client.post("/api/submissions", json={**base, "idempotency_key": str(uuid.uuid4())}).status_code == 201
    assert client.post("/api/submissions", json={**base, "idempotency_key": str(uuid.uuid4())}).status_code == 201
    assert client.post("/api/submissions", json=base).status_code == 201
    assert client.post("/api/submissions", json=base).status_code == 201
    assert count(client) == 4


@pytest.mark.parametrize("bad", ["", "abc", 5, "A" * 36, "../../etc/passwd", "g" * 8 + "-" + "0" * 4 + "-" + "0" * 4 + "-" + "0" * 4 + "-" + "0" * 12])
def test_malformed_key_is_refused(client, valid_payload, bad):
    r = client.post("/api/submissions", json={**valid_payload(client), "idempotency_key": bad})
    assert r.status_code == 422 and count(client) == 0


def test_attachment_route_retry_stores_one_report_and_scans_once(qdir, make_client, valid_payload, monkeypatch):
    write_version(qdir, 2, lambda d: d.update(attachments=True))
    client = make_client()
    calls = []
    real = attachments.prepare_files
    monkeypatch.setattr("app.routes.api.prepare_files", lambda *a, **k: calls.append(1) or real(*a, **k))
    p = {**with_file(client, valid_payload), "idempotency_key": str(uuid.uuid4())}
    first = client.post(attachments.UPLOAD_PATH, json=p)
    again = client.post(attachments.UPLOAD_PATH, json=p)
    assert first.status_code == 201 and again.status_code == 200 and again.json()["id"] == first.json()["id"]
    assert count(client) == 1 and count(client, ReportAttachment) == 1 and len(calls) == 1  # no second scan
    other_file = {**p, "attachments": [{**p["attachments"][0], "name": "друго.txt"}]}
    assert client.post(attachments.UPLOAD_PATH, json=other_file).status_code == 409
    assert count(client) == 1 and count(client, ReportAttachment) == 1


def test_parallel_retry_that_wins_the_race_is_recognised(qdir, make_client, valid_payload, monkeypatch):
    """The other request commits between our lookup and our insert: the unique key turns that into 200 / 409."""
    write_version(qdir, 2, lambda d: d.update(attachments=True))
    client = make_client()
    p = {**with_file(client, valid_payload), "idempotency_key": str(uuid.uuid4())}
    real = attachments.prepare_files

    def racing(raw, settings):
        files = real(raw, settings)
        monkeypatch.undo()
        assert client.post("/api/submissions/with-attachments", json=p).status_code == 201  # the "other" request
        return files

    monkeypatch.setattr("app.routes.api.prepare_files", racing)
    r = client.post(attachments.UPLOAD_PATH, json=p)
    assert r.status_code == 200 and r.json().get("duplicate") is True
    assert count(client) == 1 and count(client, ReportAttachment) == 1
