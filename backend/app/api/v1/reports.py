"""Report endpoints — Excel, CSV, PDF export."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import CurrentUser, get_current_user
from app.services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["reports"])

DB = Annotated[AsyncSession, Depends(get_db_session, scope="function")]
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


@router.get("/bank-ledger")
async def bank_ledger_report(
    current_user: User,
    db: DB,
    fmt: str = Depends(_fmt),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
) -> Response:
    """Bank Ledger extract (UAT Aug 2026, item 1): Supplier, Supplier
    Proforma Invoice No., Sunshine Invoice No., Selected Customer, Currency,
    Deposit Amount — the exact columns used on the bank ledger sheet."""
    svc = ReportService(db)
    data, content_type = await svc.bank_ledger_report(
        current_user.role, current_user.id, fmt, date_from=date_from, date_to=date_to
    )
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="bank-ledger.{_EXTENSIONS[fmt]}"'},
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


@router.get("/pending-payments")
async def pending_payments_report(
    current_user: User,
    db: DB,
    fmt: str = Depends(_fmt),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
) -> Response:
    """Every column the Accounts Pending tab shows, with per-tranche raised
    dates and a tranche-level ageing band (5 Nov 2026)."""
    svc = ReportService(db)
    data, content_type = await svc.pending_payments_report(fmt, date_from=date_from, date_to=date_to)
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="pending-payments.{_EXTENSIONS[fmt]}"'},
    )


@router.get("/ageing")
async def ageing_report(
    current_user: User,
    db: DB,
    fmt: str = Depends(_fmt),
    basis: str = Query("shipment", pattern="^(shipment|payment)$"),
    cut: str = Query("currency", pattern="^(currency|customer)$"),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
) -> Response:
    """The Analytics Ageing grid as a download (5 Nov 2026)."""
    svc = ReportService(db)
    data, content_type = await svc.ageing_report(
        fmt, basis=basis, cut=cut, date_from=date_from, date_to=date_to
    )
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="ageing-{basis}-{cut}.{_EXTENSIONS[fmt]}"'},
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
