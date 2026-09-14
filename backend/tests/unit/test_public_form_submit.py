"""Public form endpoints are RETIRED (Aug 2026): every route returns 410 Gone.

The submission logic these tests used to exercise lives on in
DepositRequestService.create_public (covered indirectly via the request
creation tests); the unauthenticated HTTP surface is what was removed.
"""

import pytest

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/public/masters"),
        ("GET", "/api/v1/public/form-config"),
        ("POST", "/api/v1/public/submit"),
    ],
)
async def test_public_form_endpoints_are_gone(client, method, path):
    res = await client.request(method, path, json={} if method == "POST" else None)
    assert res.status_code == 410
    assert "retired" in res.json()["detail"].lower()


async def test_gone_response_points_users_to_sign_in(client):
    res = await client.post("/api/v1/public/submit", json={})
    assert "sign in" in res.json()["detail"].lower()
