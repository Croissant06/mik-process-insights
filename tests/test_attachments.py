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


def _many(client, valid_payload, n, size):
    p = with_file(client, valid_payload)
    p["attachments"] = [
        {"name": f"файл-{i}.dat", "data": base64.b64encode(bytes([i]) * size).decode("ascii")} for i in range(n)
    ]
    return p


def test_ten_files_of_five_mib_are_accepted_and_eleven_refused(attachment_client, valid_payload):
    client = attachment_client
    assert attachments.MAX_FILES == 10 and attachments.MAX_FILE_BYTES == 5 * 1024 * 1024
    ok = client.post(attachments.UPLOAD_PATH, json=_many(client, valid_payload, 10, attachments.MAX_FILE_BYTES))
    assert ok.status_code == 201, ok.text[:200]
    with client.app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(ReportAttachment)) == 10
    too_many = client.post(attachments.UPLOAD_PATH, json=_many(client, valid_payload, 11, 10))
    assert too_many.status_code == 422 and "10" in too_many.json()["errors"]["attachments"]
    too_big = client.post(attachments.UPLOAD_PATH, json=_many(client, valid_payload, 1, attachments.MAX_FILE_BYTES + 1))
    assert too_big.status_code == 422
    with client.app.state.session_factory() as db:  # the refused reports saved nothing
        assert db.scalar(select(func.count()).select_from(Submission)) == 1


def test_upload_request_limit_fits_ten_encoded_files_and_ordinary_route_stays_small():
    full = 10 * attachments.MAX_ENCODED_BYTES
    assert attachments.MAX_UPLOAD_REQUEST > full and attachments.MAX_UPLOAD_REQUEST < full + 1024 * 1024
    assert 66 * 1024 * 1024 < attachments.MAX_UPLOAD_REQUEST < 72 * 1024 * 1024


def test_any_company_file_format_is_accepted(attachment_client, valid_payload):
    client = attachment_client
    for name in ("лекало.dxf", "поръчка.xlsx", "снимка.heic", "програма.exe", "без-разширение"):
        r = client.post(attachments.UPLOAD_PATH, json=with_file(client, valid_payload, b"\x00\x01data", name))
        assert r.status_code == 201, name


def test_only_two_uploads_are_processed_at_once(attachment_client, valid_payload):
    import asyncio

    from app.routes import api

    client = attachment_client
    async def fill():
        await api._UPLOAD_SLOTS.acquire(); await api._UPLOAD_SLOTS.acquire()
    asyncio.run(fill())
    try:
        r = client.post(attachments.UPLOAD_PATH, json=with_file(client, valid_payload))
        assert r.status_code == 503 and r.headers["retry-after"] == "10"
    finally:
        api._UPLOAD_SLOTS = asyncio.Semaphore(2)
