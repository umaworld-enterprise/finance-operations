"""Behaviour the fastapi 0.115 -> 0.133 upgrade must not change (27 Oct 2026).

1. The request's DB session commits BEFORE the response is sent and before
   BackgroundTasks run. fastapi >= 0.118 moved the exit of ``yield``
   dependencies to after the response; ``get_db_session`` commits on exit, so
   background jobs (notifications, snapshot seeding) would have looked up rows
   that were not committed yet, and commit errors would have been answered 200.
   Every ``Depends(get_db_session)`` therefore declares ``scope="function"`` —
   uniformly, because the dependency cache is keyed by scope and a mix would
   hand the auth dependency and the endpoint two different sessions.
2. A JSON body sent without a Content-Type header is still accepted
   (fastapi >= 0.132 refuses it unless ``strict_content_type=False``).
"""

from collections.abc import AsyncGenerator

from fastapi import BackgroundTasks
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

from app.api.v1.requests import DB
from app.core.database import get_db_session
from app.main import app


def _db_dependants(dependant):
    for dep in dependant.dependencies:
        if dep.call is get_db_session:
            yield dep
        yield from _db_dependants(dep)


def test_every_db_session_dependency_is_function_scoped():
    found = [
        (route.path, dep.scope)
        for route in app.routes
        if isinstance(route, APIRoute)
        for dep in _db_dependants(route.dependant)
    ]
    assert found, "no route depends on get_db_session — the walk is broken"
    assert {scope for _, scope in found} == {"function"}, [f for f in found if f[1] != "function"]


async def test_session_commits_before_background_tasks_run():
    events: list[str] = []

    async def recording_session() -> AsyncGenerator[str, None]:
        yield "session"
        events.append("commit")

    async def background() -> None:
        events.append("background")

    probe_path = "/__test__/commit-order"

    @app.post(probe_path)
    async def probe(db: DB, tasks: BackgroundTasks) -> dict:
        tasks.add_task(background)
        return {"ok": True}

    app.dependency_overrides[get_db_session] = recording_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(probe_path)
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.router.routes[:] = [
            r for r in app.router.routes if getattr(r, "path", None) != probe_path
        ]

    assert resp.status_code == 200
    assert events == ["commit", "background"]


async def test_json_body_without_content_type_is_accepted(client):
    resp = await client.post("/api/v1/masters/banks", content=b'{"name": "Compat Test Bank"}')
    assert resp.status_code == 201, resp.text
