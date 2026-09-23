"""API responses must never be cached (23 Sep 2026, executive bug: "requests
are only visible after a refresh").

Without cache headers, browsers — Safari and installed PWAs especially —
applied heuristic caching to GET responses, so the frontend's 10-15 s polls
were answered from the local HTTP cache with the same stale body. The
middleware stamps every response as uncacheable.
"""

import pytest

from app.main import NoStoreCacheMiddleware

pytestmark = pytest.mark.asyncio


async def _run(inner_headers: list[tuple[bytes, bytes]]) -> dict[bytes, bytes]:
    """Send one HTTP response through the middleware, return its headers."""

    async def app(scope, receive, send):  # noqa: ANN001
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": inner_headers,
        })
        await send({"type": "http.response.body", "body": b"{}"})

    captured: dict[bytes, bytes] = {}

    async def send(message):  # noqa: ANN001
        if message["type"] == "http.response.start":
            captured.update({k.lower(): v for k, v in message["headers"]})

    async def receive():  # noqa: ANN001
        return {"type": "http.request"}

    await NoStoreCacheMiddleware(app)({"type": "http", "path": "/api/v1/requests"}, receive, send)
    return captured


async def test_responses_are_marked_uncacheable():
    headers = await _run([(b"content-type", b"application/json")])
    assert b"no-store" in headers[b"cache-control"]
    assert headers[b"pragma"] == b"no-cache"
    assert headers[b"expires"] == b"0"
    # Unrelated headers survive.
    assert headers[b"content-type"] == b"application/json"


async def test_existing_cache_headers_are_replaced_not_duplicated():
    """A cacheable header set further down the stack must not survive —
    duplicate Cache-Control values let the browser pick the permissive one."""
    headers = await _run([
        (b"content-type", b"application/json"),
        (b"Cache-Control", b"public, max-age=3600"),
    ])
    assert headers[b"cache-control"] == b"no-store, no-cache, must-revalidate, max-age=0"


async def test_non_http_scopes_pass_through():
    """Websocket/lifespan scopes must not be touched."""
    seen = {}

    async def app(scope, receive, send):  # noqa: ANN001
        seen["type"] = scope["type"]

    async def noop(*_args):  # noqa: ANN001
        return {}

    await NoStoreCacheMiddleware(app)({"type": "lifespan"}, noop, noop)
    assert seen["type"] == "lifespan"
