"""Form fields are bounded before authentication runs (27 Oct 2026, security).

FastAPI reads and parses a route's form body before it resolves the route's
dependencies, so on the upload endpoints (``/requests/bulk-pay`` and friends)
an anonymous caller's body is parsed in full before ``current_user`` refuses
it. starlette < 1.3.1 enforced ``max_fields`` for multipart bodies only and
silently ignored it for ``application/x-www-form-urlencoded``
(PYSEC-2026-249): an unauthenticated request could make the server parse an
unbounded field list. With starlette 1.3.1 the oversized form is refused as a
bad request; before, it was parsed in full and only then answered 401.

Both tests run with real authentication: the suite's default ``app_env`` is
"development", where ``get_current_user`` signs everyone in as a dev user.

File parts are not limited here: the whole request body is capped at
100 MB by BodySizeLimitMiddleware (test_body_size_limit.py), and an
anonymous upload under that is still spooled to disk before the 401.
"""

import pytest

from app.core.config import get_settings

pytestmark = pytest.mark.asyncio

BULK_PAY = "/api/v1/requests/bulk-pay"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}


@pytest.fixture(autouse=True)
def _real_auth(monkeypatch):
    monkeypatch.setattr(get_settings(), "app_env", "production")


async def test_oversized_urlencoded_form_is_refused_before_auth(client):
    body = "&".join(f"f{i}=x" for i in range(5000))  # starlette's default limit is 1000
    resp = await client.post(BULK_PAY, content=body, headers=FORM)
    # 400 from the form limit. A 401 here means the body was parsed in full and
    # only the auth check stopped the request.
    assert resp.status_code == 400
    assert "Too many fields" in resp.text


async def test_small_anonymous_form_is_still_refused_by_auth(client):
    resp = await client.post(BULK_PAY, content="bank=x", headers=FORM)
    assert resp.status_code == 401
