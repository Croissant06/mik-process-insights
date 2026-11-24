"""Request protection for state-changing requests (audit finding H2).

Pure ASGI middleware, applied to POST/PUT/PATCH/DELETE:

* Cross-site browser requests are rejected (403): `Sec-Fetch-Site: cross-site`, or an `Origin` header that is not the
  request's own Host / an entry of ALLOWED_ORIGINS. A `text/plain` cross-site form POST needs no CORS preflight, so
  without this any web page an employee visits could submit on their behalf.
  Requests without Origin/Sec-Fetch-Site (curl, scripts, tests) are not browser-CSRF vectors and are allowed.
* `/api/*` requires `Content-Type: application/json` (415).
* The body is capped (413), by Content-Length and while streaming (chunked bodies).

Responses are generic JSON; nothing from the request is echoed or logged.
"""
from __future__ import annotations

import json
from urllib.parse import urlsplit

from app.attachments import MAX_UPLOAD_REQUEST, UPLOAD_PATH

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


class BodyTooLarge(Exception):
    pass


def _json(status: int, message: str) -> tuple[list, bytes]:
    body = json.dumps({"errors": {"_form": message}}, ensure_ascii=False).encode()
    return [(b"content-type", b"application/json; charset=utf-8"), (b"content-length", str(len(body)).encode()),
            (b"cache-control", b"no-store")], body


class RequestProtectionMiddleware:
    def __init__(self, app, *, allowed_origins: tuple[str, ...] = (), max_body_bytes: int = 256 * 1024,
                 path_limits: dict[str, int] | None = None, public_origin: str | None = None):
        self.app = app
        self.path_limits = path_limits or {"/admin/": 4096}  # sign-in/logout forms are tiny
        self.allowed = {o.lower() for o in allowed_origins}
        self.max_body = max_body_bytes
        self.public_origin = public_origin.lower() if public_origin else None

    async def _reject(self, send, status: int, message: str):
        headers, body = _json(status, message)
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})

    def _origin_ok(self, headers: dict[bytes, bytes]) -> bool:
        if headers.get(b"sec-fetch-site", b"").decode("latin-1").lower() == "cross-site":
            return False
        origin = headers.get(b"origin", b"").decode("latin-1").strip()
        if not origin:
            if self.public_origin:
                return headers.get(b"sec-fetch-site", b"").lower() == b"same-origin"
            return True
        if origin.lower() == "null":
            return False
        trusted = self.allowed | ({self.public_origin} if self.public_origin else set())
        if trusted:  # configured: exact trusted origins only, Host is not consulted
            return origin.rstrip("/").lower() in trusted
        host = headers.get(b"host", b"").decode("latin-1").strip().lower()
        try:
            return bool(host) and urlsplit(origin).netloc.lower() == host
        except ValueError:
            return False

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in UNSAFE:
            return await self.app(scope, receive, send)
        headers = {k.lower(): v for k, v in scope["headers"]}

        if not self._origin_ok(headers):
            return await self._reject(send, 403, "Заявката е отказана.")
        if scope["path"].startswith("/api/"):
            ctype = headers.get(b"content-type", b"").decode("latin-1").split(";")[0].strip().lower()
            if ctype != "application/json":
                return await self._reject(send, 415, "Невалидна заявка.")
        limit = (MAX_UPLOAD_REQUEST if scope["method"] == "POST" and scope["path"] == UPLOAD_PATH
                 else next((v for k, v in self.path_limits.items() if scope["path"].startswith(k)), self.max_body))
        declared = headers.get(b"content-length")
        if declared is not None:
            try:
                if int(declared) > limit:
                    return await self._reject(send, 413, "Заявката е твърде голяма.")
            except ValueError:
                return await self._reject(send, 400, "Невалидна заявка.")

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise BodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except BodyTooLarge:
            await self._reject(send, 413, "Заявката е твърде голяма.")


# ---- security headers --------------------------------------------------------------------------------------------

import base64  # noqa: E402
import hashlib  # noqa: E402
import logging  # noqa: E402
import re  # noqa: E402
import uuid  # noqa: E402
from pathlib import Path  # noqa: E402

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def inline_script_hashes() -> list[str]:
    """CSP hashes of the (static) inline scripts in base.html, computed from the file so they never drift."""
    text = (TEMPLATE_DIR / "base.html").read_text(encoding="utf-8")
    hashes = []
    for body in re.findall(r"<script>(.*?)</script>", text, re.S):
        hashes.append("'sha256-" + base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode() + "'")
    return hashes


def build_csp() -> str:
    scripts = " ".join(["'self'", *inline_script_hashes()])
    return "; ".join([
        "default-src 'self'", f"script-src {scripts}", "style-src 'self' 'unsafe-inline'",  # inline style="" attributes are used
        "img-src 'self' data:", "font-src 'self'", "connect-src 'self'", "object-src 'none'", "base-uri 'none'",
        "form-action 'self'", "frame-ancestors 'none'",
    ])


class SecurityHeadersMiddleware:
    """Adds browser security headers to every response (a header a route already set is left alone)."""

    def __init__(self, app, *, hsts: bool = False):
        self.app = app
        self.headers = [
            (b"content-security-policy", build_csp().encode()),
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
            (b"referrer-policy", b"same-origin"),  # NOT no-referrer: that makes browsers send "Origin: null" on form posts
            (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=(), usb=()"),
            (b"cross-origin-opener-policy", b"same-origin"),
        ]
        if hsts:
            self.headers.append((b"strict-transport-security", b"max-age=15552000"))

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                present = {k.lower() for k, _ in message.get("headers", [])}
                message = {**message, "headers": [*message.get("headers", []),
                                                  *[(k, v) for k, v in self.headers if k not in present]]}
            await send(message)

        await self.app(scope, receive, send_with_headers)


# ---- sanitized error handling ------------------------------------------------------------------------------------

log = logging.getLogger("app.errors")


class ErrorGuardMiddleware:
    """Turns an unexpected exception into a generic 500 and logs ONLY: request id, method, path (no query string),
    exception type and the source line. Never the exception message (database errors can contain submitted values),
    never headers, cookies, bodies or answers. The exception is not re-raised, so the server does not print it either."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = False

        async def tracking_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as exc:  # noqa: BLE001
            request_id = uuid.uuid4().hex[:12]
            tb = exc.__traceback__
            while tb and tb.tb_next:
                tb = tb.tb_next
            where = f"{Path(tb.tb_frame.f_code.co_filename).name}:{tb.tb_lineno}" if tb else "?"
            log.error("unhandled error request_id=%s method=%s path=%s type=%s at=%s", request_id, scope["method"],
                      scope["path"], type(exc).__name__, where)
            if not started:
                body = json.dumps({"errors": {"_form": f"Възникна грешка. Опитайте отново по-късно. (код {request_id})"}},
                                  ensure_ascii=False).encode()
                await send({"type": "http.response.start", "status": 500, "headers": [
                    (b"content-type", b"application/json; charset=utf-8"), (b"content-length", str(len(body)).encode()),
                    (b"cache-control", b"no-store"), (b"x-request-id", request_id.encode())]})
                await send({"type": "http.response.body", "body": body})
