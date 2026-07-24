"""Report endpoints — Excel, CSV, PDF export."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import CurrentUser, get_current_user
from app.services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["reports"])

DB = Annotated[AsyncSession, Depends(get_db_session)]
User = Annotated[CurrentUser, Depends(get_current_user)]

_EXTENSIONS = {"excel": "xlsx", "csv": "csv", "pdf": "pdf"}


def _fmt(format: Literal["excel", "csv", "pdf"] = Query("excel")) -> str:
    return format


@router.get("/requests")
async def request_report(
    current_user: User,
    db: DB,
    fmt: str = Depends(_fmt),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    date_field: Literal["created", "modified", "payment_date"] = Query("created"),
) -> Response:
    svc = ReportService(db)
    data, content_type = await svc.request_report(
        current_user.role, current_user.id, fmt,
        date_from=date_from, date_to=date_to, date_field=date_field,
    )
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="requests.{_EXTENSIONS[fmt]}"'},
    )


@router.get("/payments")
async def payment_report(
    current_user: User,
    db: DB,
    fmt: str = Depends(_fmt),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
) -> Response:
    svc = ReportService(db)
    data, content_type = await svc.payment_report(fmt, date_from=date_from, date_to=date_to)
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="payments.{_EXTENSIONS[fmt]}"'},
    )


@router.get("/suppliers")
async def supplier_report(
    current_user: User,
    db: DB,
    fmt: str = Depends(_fmt),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
) -> Response:
    svc = ReportService(db)
    data, content_type = await svc.supplier_report(fmt, date_from=date_from, date_to=date_to)
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="suppliers.{_EXTENSIONS[fmt]}"'},
    )


@router.get("/delays")
async def delay_report(
    current_user: User,
    db: DB,
    fmt: str = Depends(_fmt),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
) -> Response:
    svc = ReportService(db)
    data, content_type = await svc.delay_report(fmt, date_from=date_from, date_to=date_to)
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="delays.{_EXTENSIONS[fmt]}"'},
    )


@router.get("/cost-of-fund")
async def cost_of_fund_report(
    current_user: User,
    db: DB,
    fmt: str = Depends(_fmt),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
) -> Response:
    svc = ReportService(db)
    data, content_type = await svc.cost_of_fund_report(fmt, date_from=date_from, date_to=date_to)
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="cost-of-fund.{_EXTENSIONS[fmt]}"'},
    )
