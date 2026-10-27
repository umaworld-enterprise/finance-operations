"""Request bodies over the limit are refused before parsing or auth (27 Oct 2026, security).

Before this, an anonymous upload to /requests/bulk-pay (and the other upload
routes) was received in full and spooled to disk, whatever its size, and
only then answered 401 — nothing in front of the app limited it.
"""

import json

import pytest

from app.core.config import get_settings
from app.main import MAX_REQUEST_BODY_BYTES, BodySizeLimitMiddleware, app

pytestmark = pytest.mark.asyncio

LIMIT = 100  # bytes, for the middleware-level tests


async def _run(headers, chunks, limit=LIMIT):
    """Drive the middleware around a tiny app that reads the whole body, then answers 200."""
    sent: list[dict] = []
    seen = {"app_called": False, "app_got": b"", "app_saw_disconnect": False, "reads": 0}
    queue = [{"type": "http.request", "body": c, "more_body": i < len(chunks) - 1}
             for i, c in enumerate(chunks)]

    async def receive():
        seen["reads"] += 1
        return queue.pop(0) if queue else {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    async def inner(scope, receive, send):
        seen["app_called"] = True
        while True:
            m = await receive()
            if m["type"] == "http.disconnect":
                seen["app_saw_disconnect"] = True
                break
            seen["app_got"] += m.get("body", b"")
            if not m.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    scope = {"type": "http", "method": "POST", "path": "/x", "headers": headers}
    await BodySizeLimitMiddleware(inner, max_body_bytes=limit)(scope, receive, send)
    starts = [m for m in sent if m["type"] == "http.response.start"]
    return starts, sent, seen


def _body(sent):
    return b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")


async def test_declared_oversize_is_refused_without_reading_the_body():
    starts, sent, seen = await _run([(b"content-length", str(LIMIT + 1).encode())], [b"x" * 10])
    assert [s["status"] for s in starts] == [413]
    assert json.loads(_body(sent))["error_code"] == "PAYLOAD_TOO_LARGE"
    assert not seen["app_called"]
    assert seen["reads"] == 0


async def test_streamed_oversize_is_cut_off_at_the_limit():
    starts, sent, seen = await _run([], [b"x" * 60, b"x" * 60, b"x" * 60])
    assert [s["status"] for s in starts] == [413]  # the app's own 200 is dropped
    assert seen["app_saw_disconnect"]
    assert len(seen["app_got"]) <= LIMIT
    assert seen["reads"] == 2  # stops reading at the chunk that crossed the limit


async def test_body_at_the_limit_passes_through_untouched():
    starts, sent, seen = await _run([(b"content-length", str(LIMIT).encode())], [b"x" * LIMIT])
    assert [s["status"] for s in starts] == [200]
    assert _body(sent) == b"ok"
    assert seen["app_got"] == b"x" * LIMIT


async def test_non_http_scopes_pass_through():
    seen = {}

    async def inner(scope, receive, send):
        seen["type"] = scope["type"]

    async def noop(*_args):
        return {}

    await BodySizeLimitMiddleware(inner, max_body_bytes=LIMIT)({"type": "lifespan"}, noop, noop)
    assert seen["type"] == "lifespan"


async def test_app_refuses_oversized_anonymous_upload_before_auth(monkeypatch):
    """Through the real middleware stack: 413 with CORS and no-store headers,
    and the body is never read — so nothing is parsed or spooled to disk."""
    monkeypatch.setattr(get_settings(), "app_env", "production")
    assert MAX_REQUEST_BODY_BYTES == 100 * 1024 * 1024
    origin = get_settings().cors_origins[0].encode()
    reads = 0
    sent: list[dict] = []

    async def receive():
        nonlocal reads
        reads += 1
        return {"type": "http.request", "body": b"--x\r\n", "more_body": True}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
        "scheme": "http", "path": "/api/v1/requests/bulk-pay",
        "raw_path": b"/api/v1/requests/bulk-pay",
        "query_string": b"", "root_path": "", "server": ("test", 80), "client": ("1.2.3.4", 1),
        "headers": [
            (b"host", b"test"), (b"origin", origin),
            (b"content-type", b"multipart/form-data; boundary=x"),
            (b"content-length", str(MAX_REQUEST_BODY_BYTES + 1).encode()),
        ],
    }
    await app(scope, receive, send)
    start = next(m for m in sent if m["type"] == "http.response.start")
    headers = {k.lower(): v for k, v in start["headers"]}
    assert start["status"] == 413
    assert json.loads(_body(sent))["error_code"] == "PAYLOAD_TOO_LARGE"
    assert headers[b"access-control-allow-origin"] == origin
    assert b"no-store" in headers[b"cache-control"]
    assert reads == 0
