"""Adjust Invoices endpoints — Accounts-owned reallocation of paid tranches."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import CurrentUser, get_current_user
from app.core.exceptions import AuthorizationError
from app.models.enums import UserRole
from app.schemas.tranche import AdjustmentCreate, AdjustmentResponse, SupplierTrancheOptions
from app.services.adjustment_service import AdjustmentService

router = APIRouter(prefix="/adjustments", tags=["adjustments"])

DB = Annotated[AsyncSession, Depends(get_db_session)]
User = Annotated[CurrentUser, Depends(get_current_user)]

_VIEW_ROLES = {UserRole.ACCOUNTS_TEAM, UserRole.SUPER_ADMIN, UserRole.FINANCE_ADMIN}
_WRITE_ROLES = {UserRole.ACCOUNTS_TEAM, UserRole.SUPER_ADMIN}


def _ip(req: Request) -> str | None:
    forwarded = req.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return req.client.host if req.client else None


@router.get("", response_model=list[AdjustmentResponse])
async def list_adjustments(
    current_user: User,
    db: DB,
    limit: int = Query(100, ge=1, le=500),
) -> list[AdjustmentResponse]:
    if current_user.role not in _VIEW_ROLES:
        raise AuthorizationError("Access to invoice adjustments is not permitted for your role.")
    return await AdjustmentService(db).list_recent(limit=limit)


@router.post("", response_model=AdjustmentResponse, status_code=201)
async def create_adjustment(
    data: AdjustmentCreate,
    current_user: User,
    request: Request,
    db: DB,
) -> AdjustmentResponse:
    """Reallocate value from an already-paid tranche to a tranche on another
    invoice of the same supplier. The paid tranche itself is never modified."""
    if current_user.role not in _WRITE_ROLES:
        raise AuthorizationError("Only Accounts Team can adjust invoices.")
    svc = AdjustmentService(db)
    adjustment = await svc.create(
        data, current_user.id, current_user.role,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return await svc.to_response(adjustment)


@router.get("/supplier/{supplier_id}/options", response_model=SupplierTrancheOptions)
async def supplier_tranche_options(
    supplier_id: UUID,
    current_user: User,
    db: DB,
) -> SupplierTrancheOptions:
    """Paid source tranches (with remaining balance) and unpaid destination
    tranches across the supplier's requests."""
    if current_user.role not in _VIEW_ROLES:
        raise AuthorizationError("Access to invoice adjustments is not permitted for your role.")
    paid_sources, unpaid_destinations = await AdjustmentService(db).supplier_tranche_options(
        supplier_id
    )
    return SupplierTrancheOptions(
        paid_sources=paid_sources, unpaid_destinations=unpaid_destinations
    )
