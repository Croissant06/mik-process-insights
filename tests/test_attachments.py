import base64

import pytest
from sqlalchemy import func, select

from app import attachments
from app.models import ReportAttachment, Submission
from tests.conftest import write_version
from tests.test_admin import audit_actions, login, make_admin


@pytest.fixture
def attachment_client(qdir, make_client):
    write_version(qdir, 2, lambda definition: definition.update(attachments=True))
    return make_client()


def with_file(client, valid_payload, content=b"synthetic work instructions", filename="Инструкция.txt"):
    return {
        **valid_payload(client), "questionnaire_version": 2,
        "attachments": [{"name": filename, "data": base64.b64encode(content).decode("ascii")}],
    }


def test_attachment_round_trip_and_access(attachment_client, valid_payload):
    client = attachment_client
    assert 'id="attachments"' in client.get("/").text
    assert client.post("/api/submissions", json={**valid_payload(client), "questionnaire_version": 2}).status_code == 201
    content = bytes(range(256)) * 1024  # Larger than the normal JSON route limit after encoding.
    response = client.post(attachments.UPLOAD_PATH, json=with_file(client, valid_payload, content))
    assert response.status_code == 201
    report_id = response.json()["id"]
    with client.app.state.session_factory() as db:
        item = db.scalar(select(ReportAttachment))
        assert item.submission_id == report_id
        path = f"/admin/attachments/{item.id}"
    assert client.get(path, follow_redirects=False).status_code == 303
    make_admin(client)
    assert login(client).status_code == 303
    assert "Инструкция.txt" in client.get(f"/admin/reports/{report_id}").text
    response = client.get(path)
    assert response.content == content
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-disposition"].startswith("attachment; filename*=UTF-8''")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"
    assert "download_attachment" in audit_actions(client)


@pytest.mark.parametrize("status", [422, 503])
def test_invalid_or_unscanned_file_does_not_save_report(attachment_client, valid_payload, monkeypatch, status):
    client = attachment_client
    payload = with_file(client, valid_payload)
    if status == 422:
        payload["attachments"][0]["name"] = "../private.txt"
    else:
        def unavailable(*args, **kwargs):
            raise attachments.ScannerUnavailable

        monkeypatch.setattr("app.routes.api.prepare_files", unavailable)
    response = client.post(attachments.UPLOAD_PATH, json=payload)
    assert response.status_code == status
    with client.app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Submission)) == 0
        assert db.scalar(select(func.count()).select_from(ReportAttachment)) == 0


def test_old_questionnaire_refuses_attachments(attachment_client, valid_payload):
    client = attachment_client
    payload = with_file(client, valid_payload)
    payload["questionnaire_version"] = 1
    assert client.post(attachments.UPLOAD_PATH, json=payload).status_code == 422
