"""Adjust Invoices endpoints — reallocation of paid tranches.

Accounts Team / Super Admin record adjustments directly and decide the
pending queue; merchandisers raise adjustment requests (PENDING_APPROVAL)
and see their own (change note B3).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import CurrentUser, get_current_user
from app.core.exceptions import AuthorizationError
from app.models.enums import UserRole
from app.schemas.tranche import (
    AdjustmentCreate,
    AdjustmentDecision,
    AdjustmentResponse,
    SupplierTrancheOptions,
)
from app.services.adjustment_service import AdjustmentService
from app.services.notification_service import (
    notify_adjustment_created,
    notify_adjustment_decided,
)

router = APIRouter(prefix="/adjustments", tags=["adjustments"])

DB = Annotated[AsyncSession, Depends(get_db_session)]
User = Annotated[CurrentUser, Depends(get_current_user)]

_DECIDER_ROLES = {UserRole.ACCOUNTS_TEAM, UserRole.SUPER_ADMIN}
_VIEW_ROLES = _DECIDER_ROLES | {UserRole.FINANCE_ADMIN, UserRole.MERCHANDISER}
_WRITE_ROLES = _DECIDER_ROLES | {UserRole.MERCHANDISER}


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
    """Adjustment history. Merchandisers see only adjustments they raised."""
    if current_user.role not in _VIEW_ROLES:
        raise AuthorizationError("Access to invoice adjustments is not permitted for your role.")
    performed_by = current_user.id if current_user.role == UserRole.MERCHANDISER else None
    return await AdjustmentService(db).list_recent(limit=limit, performed_by=performed_by)


@router.get("/pending", response_model=list[AdjustmentResponse])
async def list_pending_adjustments(
    current_user: User,
    db: DB,
) -> list[AdjustmentResponse]:
    """The Accounts queue — merchandiser-raised adjustment requests awaiting
    a decision, oldest first."""
    if current_user.role not in _DECIDER_ROLES | {UserRole.FINANCE_ADMIN}:
        raise AuthorizationError("Only Accounts Team can view the adjustment queue.")
    return await AdjustmentService(db).list_pending()


@router.post("", response_model=AdjustmentResponse, status_code=201)
async def create_adjustment(
    data: AdjustmentCreate,
    current_user: User,
    request: Request,
    db: DB,
    background_tasks: BackgroundTasks,
) -> AdjustmentResponse:
    """Reallocate value from an already-paid tranche to a tranche on another
    invoice of the same supplier. The paid tranche itself is never modified.

    Merchandiser-raised adjustments are created PENDING_APPROVAL for the
    Accounts queue; Accounts/Super Admin adjustments complete immediately."""
    if current_user.role not in _WRITE_ROLES:
        raise AuthorizationError("Your role cannot raise invoice adjustments.")
    svc = AdjustmentService(db)
    adjustment = await svc.create(
        data, current_user.id, current_user.role,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    background_tasks.add_task(notify_adjustment_created, adjustment.id)
    return await svc.to_response(adjustment)


@router.post("/{adjustment_id}/approve", response_model=AdjustmentResponse)
async def approve_adjustment(
    adjustment_id: UUID,
    body: AdjustmentDecision,
    current_user: User,
    request: Request,
    db: DB,
    background_tasks: BackgroundTasks,
) -> AdjustmentResponse:
    """Approve a pending adjustment — all create-time validations re-run
    (state may have changed) and the raising merchandiser is notified."""
    svc = AdjustmentService(db)
    adjustment = await svc.approve(
        adjustment_id, current_user.id, current_user.role, body.reason,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    background_tasks.add_task(
        notify_adjustment_decided, adjustment_id, "approved", body.reason
    )
    return await svc.to_response(adjustment)


@router.post("/{adjustment_id}/reject", response_model=AdjustmentResponse)
async def reject_adjustment(
    adjustment_id: UUID,
    body: AdjustmentDecision,
    current_user: User,
    request: Request,
    db: DB,
    background_tasks: BackgroundTasks,
) -> AdjustmentResponse:
    """Reject a pending adjustment with a mandatory reason — the raising
    merchandiser is notified."""
    svc = AdjustmentService(db)
    adjustment = await svc.reject(
        adjustment_id, current_user.id, current_user.role, body.reason,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    background_tasks.add_task(
        notify_adjustment_decided, adjustment_id, "rejected", body.reason
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
