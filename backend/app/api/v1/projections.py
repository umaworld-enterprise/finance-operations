"""Projections module endpoints (4 Sep 2026).

Monthly per-vertical projections (USD / EUR / CNY): merchandisers file NEXT
month's numbers between the 25th and month end; after the deadline only the
Super Admin can add them (the unblock path). The dashboard compares each
month's projections against the actual deposit amounts requested that month.
"""

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import CurrentUser, get_current_user
from app.services.projection_service import ProjectionService

router = APIRouter(prefix="/projections", tags=["projections"])

DB = Annotated[AsyncSession, Depends(get_db_session)]
User = Annotated[CurrentUser, Depends(get_current_user)]


class ProjectionItem(BaseModel):
    vertical_id: UUID
    amount_usd: Decimal = Field(0, ge=0)
    amount_eur: Decimal = Field(0, ge=0)
    amount_cny: Decimal = Field(0, ge=0)


class ProjectionSubmit(BaseModel):
    year: int = Field(ge=2020, le=2100)
    month: int = Field(ge=1, le=12)
    items: list[ProjectionItem] = Field(min_length=1)


@router.get("/status")
async def projection_status(current_user: User, db: DB) -> dict:
    """The caller's own projection state — drives the merchandiser form, the
    fill-it popup and the blocked banner."""
    return await ProjectionService(db).get_status(current_user.id)


@router.post("")
async def submit_projections(
    body: ProjectionSubmit, current_user: User, db: DB
) -> dict:
    """Upsert projection rows. Merchandisers: own verticals, next month,
    while the 25th→EOM window is open. Super Admin: any vertical/period —
    the on-behalf unblock path."""
    svc = ProjectionService(db)
    count = await svc.submit(
        current_user.id, current_user.role,
        body.year, body.month,
        [item.model_dump() for item in body.items],
    )
    return {"saved": count}


@router.get("/dashboard")
async def projection_dashboard(
    current_user: User, db: DB,
    year: int = Query(default=None),
    month: int = Query(default=None, ge=1, le=12),
) -> dict:
    """Projection vs actual per vertical for one month (defaults to the
    current month). Available to every role."""
    today = date.today()
    y = year or today.year
    m = month or today.month
    rows = await ProjectionService(db).dashboard(y, m)
    return {"year": y, "month": m, "rows": rows}
