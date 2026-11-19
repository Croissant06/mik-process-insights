"""Security headers (M9) and sanitized error handling (M3)."""
import logging
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import create_app
from app.security import build_csp, inline_script_hashes

SECRET = "ТАЙНО-ИМЕ-123"


def test_every_response_carries_security_headers(client):
    for r in (client.get("/"), client.get("/healthz"), client.get("/admin/login"), client.get("/nope"),
              client.get("/static/css/tokens.css")):
        h = r.headers
        assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
        assert h["referrer-policy"] == "same-origin"
        assert "frame-ancestors 'none'" in h["content-security-policy"] and "object-src 'none'" in h["content-security-policy"]
        assert "camera=()" in h["permissions-policy"] and h["cross-origin-opener-policy"] == "same-origin"
        assert "strict-transport-security" not in h  # dev: plain HTTP


def test_csp_allows_only_own_scripts_and_the_hashed_theme_bootstrap(client):
    csp = build_csp()
    script = re.search(r"script-src ([^;]+)", csp).group(1)
    assert "'unsafe-inline'" not in script and "'unsafe-eval'" not in script and "http" not in script
    assert len(inline_script_hashes()) == 1 and inline_script_hashes()[0] in script
    page = client.get("/").text
    inline = re.findall(r"<script>(.*?)</script>", page, re.S)
    assert len(inline) == 1  # the only inline script is the hashed one; nothing else may be added without a new hash
    assert "onclick=" not in page and "javascript:" not in page


def test_hsts_only_when_cookies_are_secure(make_client):
    assert "max-age" in make_client(cookie_secure=True).get("/healthz").headers["strict-transport-security"]


def test_openapi_and_docs_are_not_exposed(client):
    for path in ("/openapi.json", "/docs", "/redoc"):
        assert client.get(path).status_code == 404


def boom_app(make_client):
    c = make_client()
    app = c.app

    @app.get("/boom")
    def boom():
        raise RuntimeError(f"db said: INSERT ... VALUES ('{SECRET}')")

    @app.get("/boom-db")
    def boom_db():
        with app.state.session_factory() as db:
            db.execute(text(f"SELECT {SECRET!r}::nonexistent"))

    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("path", ["/boom", "/boom-db"])
def test_unexpected_error_is_generic_and_log_has_no_values(make_client, caplog, path):
    c = boom_app(make_client)
    with caplog.at_level(logging.DEBUG):
        r = c.get(path + "?name=SECRETQUERY", headers={"cookie": "mik_admin=sessiontoken", "x-secret": "ASCII-SECRET"})
    assert r.status_code == 500 and SECRET not in r.text and "Traceback" not in r.text
    rid = r.headers["x-request-id"]
    assert rid in r.text and "content-security-policy" in r.headers  # even the 500 has the security headers
    out = " ".join(rec.getMessage() for rec in caplog.records if not rec.name.startswith(("httpx", "httpcore")))  # server-side logs only
    assert f"request_id={rid}" in out and "path=" + path in out and "type=" in out
    assert SECRET not in out and "SECRETQUERY" not in out and "ASCII-SECRET" not in out and "sessiontoken" not in out and "INSERT" not in out and "?name" not in out
    assert not any(rec.exc_info for rec in caplog.records if rec.name == "app.errors")


def test_error_after_partial_response_does_not_crash_the_server(make_client):
    assert boom_app(make_client).get("/healthz").status_code == 200
