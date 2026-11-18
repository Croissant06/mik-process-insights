"""H2: cross-site, wrong content type and oversized requests are rejected before any processing."""
import json

import pytest

H = {"content-type": "application/json"}


def body(client, valid_payload):
    return json.dumps(valid_payload(client), ensure_ascii=False).encode()


def count(client):
    from sqlalchemy import func, select

    from app.models import Submission

    with client.app.state.session_factory() as s:
        return s.scalar(select(func.count()).select_from(Submission))


def test_normal_json_post_still_works(client, valid_payload):
    assert client.post("/api/submissions", content=body(client, valid_payload), headers=H).status_code == 201


def test_same_origin_browser_post_works(client, valid_payload):
    h = {**H, "origin": "http://testserver", "sec-fetch-site": "same-origin"}
    assert client.post("/api/submissions", content=body(client, valid_payload), headers=h).status_code == 201


@pytest.mark.parametrize("headers", [
    {"origin": "http://evil.example"},
    {"origin": "null"},
    {"sec-fetch-site": "cross-site"},
    {"origin": "http://testserver.evil.example"},
])
def test_cross_site_post_is_rejected_and_stores_nothing(client, valid_payload, headers):
    r = client.post("/api/submissions", content=body(client, valid_payload), headers={**H, **headers})
    assert r.status_code == 403 and count(client) == 0


def test_text_plain_cross_site_form_post_is_rejected(client, valid_payload):
    # the classic CSRF: text/plain needs no preflight
    r = client.post("/api/submissions", content=body(client, valid_payload),
                    headers={"content-type": "text/plain", "origin": "http://evil.example"})
    assert r.status_code == 403 and count(client) == 0


@pytest.mark.parametrize("ctype", ["text/plain", "application/x-www-form-urlencoded", "multipart/form-data; boundary=x", ""])
def test_api_requires_json_content_type(client, valid_payload, ctype):
    headers = {"content-type": ctype} if ctype else {}
    r = client.post("/api/submissions", content=body(client, valid_payload), headers=headers)
    assert r.status_code == 415 and count(client) == 0


def test_json_with_charset_is_accepted(client, valid_payload):
    h = {"content-type": "application/json; charset=utf-8"}
    assert client.post("/api/submissions", content=body(client, valid_payload), headers=h).status_code == 201


def test_oversized_body_by_content_length_is_rejected(client):
    r = client.post("/api/submissions", content=b'{"x":"' + b"a" * (300 * 1024) + b'"}', headers=H)
    assert r.status_code == 413


def test_oversized_chunked_body_is_rejected(client):
    def chunks():
        for _ in range(40):
            yield b"a" * 10_000  # 400 KB, no Content-Length

    r = client.post("/api/submissions", content=chunks(), headers=H)
    assert r.status_code == 413


def test_allowed_origins_setting(make_client, valid_payload):
    c = make_client(allowed_origins=("https://reports.example.com",))
    h = {**H, "origin": "https://reports.example.com"}
    assert c.post("/api/submissions", content=body(c, valid_payload), headers=h).status_code == 201


def test_js_required_fallback_still_accepts_same_origin_form_post(client):
    r = client.post("/js-required", data={"a": "b"}, headers={"origin": "http://testserver"})
    assert r.status_code == 400  # our own fail-closed page, not a 403


def test_rejections_do_not_echo_the_request(client):
    r = client.post("/api/submissions", content="СЕКРЕТ", headers={"content-type": "text/plain"})
    assert "СЕКРЕТ" not in r.text
