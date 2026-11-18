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

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def _json(status: int, message: str) -> tuple[list, bytes]:
    body = json.dumps({"errors": {"_form": message}}, ensure_ascii=False).encode()
    return [(b"content-type", b"application/json; charset=utf-8"), (b"content-length", str(len(body)).encode()),
            (b"cache-control", b"no-store")], body


class RequestProtectionMiddleware:
    def __init__(self, app, *, allowed_origins: tuple[str, ...] = (), max_body_bytes: int = 256 * 1024):
        self.app = app
        self.allowed = {o.lower() for o in allowed_origins}
        self.max_body = max_body_bytes

    async def _reject(self, send, status: int, message: str):
        headers, body = _json(status, message)
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})

    def _origin_ok(self, headers: dict[bytes, bytes]) -> bool:
        if headers.get(b"sec-fetch-site", b"").decode("latin-1").lower() == "cross-site":
            return False
        origin = headers.get(b"origin", b"").decode("latin-1").strip()
        if not origin:
            return True
        if origin.lower() == "null":
            return False
        if origin.rstrip("/").lower() in self.allowed:
            return True
        host = headers.get(b"host", b"").decode("latin-1").strip().lower()
        return bool(host) and urlsplit(origin).netloc.lower() == host

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
        declared = headers.get(b"content-length")
        if declared is not None:
            try:
                if int(declared) > self.max_body:
                    return await self._reject(send, 413, "Заявката е твърде голяма.")
            except ValueError:
                return await self._reject(send, 400, "Невалидна заявка.")

        received = 0
        too_big = False

        async def limited_receive():
            nonlocal received, too_big
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body:
                    too_big = True
                    return {"type": "http.request", "body": b"", "more_body": False}
            return message

        started = False

        async def guarded_send(message):
            nonlocal started
            if too_big and not started:
                started = True
                headers_, body = _json(413, "Заявката е твърде голяма.")
                await send({"type": "http.response.start", "status": 413, "headers": headers_})
                await send({"type": "http.response.body", "body": body})
                return
            if too_big:
                return  # swallow whatever the app tried to send after we answered 413
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        await self.app(scope, limited_receive, guarded_send)
