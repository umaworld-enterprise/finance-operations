"""Deposit request endpoints."""

import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, status
from pydantic import BaseModel

from app.analytics.snapshot_job import seed_snapshot_for_request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.database import get_db_session
from app.core.dependencies import CurrentUser, get_current_user
from app.core.exceptions import AppError, AuthorizationError, NotFoundError
from app.models.deposit_request import DepositRequest
from app.models.enums import UserRole
from app.models.enums import RequestStatus
from app.models.masters import User as UserModel
from app.repositories.deposit_request_repo import DepositRequestRepository
from app.schemas.deposit_request import (
    ActivityItemResponse,
    DepositRequestCreate,
    DepositRequestDetailResponse,
    DepositRequestResponse,
    DepositRequestUpdate,
    HomDecisionRequest,
    StatusChangeRequest,
)
from app.schemas.common import MessageResponse, PaginatedResponse
from app.services.deposit_request_service import DepositRequestService
from app.services.notification_service import (
    notify_hom_decision,
    notify_request_created,
    notify_request_rejected_by_accounts,
    notify_status_change,
)

router = APIRouter(prefix="/requests", tags=["deposit-requests"])

DB = Annotated[AsyncSession, Depends(get_db_session)]
User = Annotated[CurrentUser, Depends(get_current_user)]


def _ip(req: Request) -> str | None:
    forwarded = req.headers.get("x-forwarded-for")
    return forwarded.split(",")[0].strip() if forwarded else (req.client.host if req.client else None)


@router.get("", response_model=PaginatedResponse[DepositRequestResponse])
async def list_requests(
    current_user: User,
    db: DB,
    status_filter: list[RequestStatus] | None = Query(None, alias="status"),
    supplier_id: UUID | None = None,
    customer_id: UUID | None = None,
    vertical_id: UUID | None = None,
    created_by: UUID | None = None,
    search: str | None = Query(None, max_length=100),
    sort: str | None = Query(None, pattern="^(newest|oldest|amount_desc|amount_asc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=1000),
) -> PaginatedResponse[DepositRequestResponse]:
    repo = DepositRequestRepository(db)
    offset = (page - 1) * page_size
    items = await repo.list_for_role(
        current_user.role, current_user.id,
        status=status_filter, supplier_id=supplier_id,
        customer_id=customer_id, vertical_id=vertical_id,
        created_by=created_by, search=search, sort=sort, limit=page_size, offset=offset,
    )
    total = await repo.count_for_role(
        current_user.role, current_user.id,
        status=status_filter, supplier_id=supplier_id,
        customer_id=customer_id, vertical_id=vertical_id,
        created_by=created_by, search=search,
    )
    responses = [DepositRequestResponse.model_validate(r) for r in items]
    # Who acted last — so hold/cancel/reject rows carry the person's name
    # (UAT Aug 2026, item 6).
    actors = await DepositRequestService(db).get_last_status_actors([r.id for r in items])
    for resp in responses:
        resp.last_status_change_by = actors.get(resp.id)
    return PaginatedResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=responses,
    )


@router.post("", response_model=DepositRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_request(
    data: DepositRequestCreate,
    current_user: User,
    request: Request,
    db: DB,
    background_tasks: BackgroundTasks,
) -> DepositRequestResponse:
    svc = DepositRequestService(db)
    req = await svc.create(
        data,
        current_user.id,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    # Analytics snapshot is computed after the response — it adds ~2 DB round
    # trips and is fully recalculable, so it must not block the submit.
    background_tasks.add_task(seed_snapshot_for_request, req.id)
    # Accounts (or HoM for flagged suppliers) learn about the new request.
    background_tasks.add_task(notify_request_created, req.id)
    return DepositRequestResponse.model_validate(req)


@router.get("/pending-payment-queue", response_model=list[DepositRequestResponse])
async def pending_payment_queue(
    current_user: User,
    db: DB,
) -> list[DepositRequestResponse]:
    """Oldest-first queue for Accounts Team dashboard."""
    from app.core.exceptions import AuthorizationError
    from app.models.enums import UserRole
    _ALLOWED = {UserRole.ACCOUNTS_TEAM, UserRole.SUPER_ADMIN, UserRole.MERCHANDISER}
    if current_user.role not in _ALLOWED:
        raise AuthorizationError("Access to the payment queue is not permitted for your role.")
    svc = DepositRequestService(db)
    created_by_filter = current_user.id if current_user.role == UserRole.MERCHANDISER else None
    requests = await svc.get_pending_payment_queue(created_by=created_by_filter)
    return [DepositRequestResponse.model_validate(r) for r in requests]


@router.get("/queue-kpis")
async def queue_kpis(current_user: User, db: DB) -> dict:
    """Financial-year-to-date KPI counts for the Accounts payment queue
    (UAT Aug 2026, items 5/17/19): pending / awaiting HoM / on hold /
    processed / rejected / cancelled / total, counted by created date
    within the current April–March financial year."""
    _ALLOWED = {UserRole.ACCOUNTS_TEAM, UserRole.SUPER_ADMIN}
    if current_user.role not in _ALLOWED:
        raise AuthorizationError("Access to the payment queue KPIs is not permitted for your role.")
    return await DepositRequestService(db).get_queue_kpis()


@router.get("/my-field-visibility")
async def my_field_visibility(current_user: User, db: DB) -> dict:
    """Returns {field_key: bool} for the calling user's role. Super admin always gets all true."""
    from app.models.enums import UserRole
    from app.services.analytics_service import get_field_visibility, FIELD_VISIBILITY_DEFAULTS
    if current_user.role == UserRole.SUPER_ADMIN:
        return {k: True for k in FIELD_VISIBILITY_DEFAULTS}
    config = await get_field_visibility(db)
    role = current_user.role.value
    return {k: v.get(role, False) for k, v in config.items()}


@router.get("/my-activity", response_model=list[ActivityItemResponse])
async def my_activity(
    current_user: User,
    db: DB,
    limit: int = Query(50, ge=1, le=100),
) -> list[ActivityItemResponse]:
    """Recent status changes on the current user's own requests."""
    svc = DepositRequestService(db)
    return await svc.get_my_activity(current_user.id, limit=limit)


@router.get("/pending-release")
async def pending_release(
    current_user: User,
    db: DB,
) -> list[dict]:
    """'Yet to be Released' tranches (2 onwards, unpaid, unreleased) on live
    pending-payment requests (19 Aug 2026). Drives the merchandiser
    'Tranche Payments to be Released' tile and the Accounts Workspace
    'Yet to be Released by Merchandiser' tile + tab. Merchandisers see their
    own; accounts / HoM / finance / super admins see all."""
    from app.models.enums import TrancheStatus
    from app.models.masters import Supplier
    from app.models.tranche import PaymentTranche, tranche_label

    Creator = aliased(UserModel)
    stmt = (
        select(PaymentTranche, DepositRequest, Supplier.name, Creator.full_name)
        .join(DepositRequest, DepositRequest.id == PaymentTranche.deposit_request_id)
        .join(Supplier, Supplier.id == DepositRequest.supplier_id)
        .outerjoin(Creator, Creator.id == DepositRequest.created_by)
        .where(
            PaymentTranche.status == TrancheStatus.UNPAID,
            PaymentTranche.released_at.is_(None),
            PaymentTranche.tranche_number > 1,
            DepositRequest.is_deleted == False,  # noqa: E712
            DepositRequest.current_status == RequestStatus.PENDING_PAYMENT,
        )
        .order_by(PaymentTranche.tentative_payment_date.asc().nulls_last())
    )
    if current_user.role == UserRole.MERCHANDISER:
        stmt = stmt.where(DepositRequest.created_by == current_user.id)
    rows = (await db.execute(stmt)).all()
    return [
        {
            "request_id": str(req.id),
            "request_number": req.request_number,
            "sunshine_invoice_number": req.sunshine_invoice_number,
            "supplier_name": supplier_name,
            "merchandiser_name": creator_name,
            "currency": req.currency.value if req.currency else None,
            "tranche_id": str(t.id),
            "tranche_label": tranche_label(t.tranche_number),
            "amount": float(t.amount),
            "tentative_payment_date": (
                t.tentative_payment_date.isoformat() if t.tentative_payment_date else None
            ),
        }
        for t, req, supplier_name, creator_name in rows
    ]


@router.get("/hom-queue", response_model=list[DepositRequestResponse])
async def hom_queue(
    current_user: User,
    db: DB,
) -> list[DepositRequestResponse]:
    """Requests awaiting Head of Merchandiser approval."""
    _ALLOWED = {UserRole.HEAD_OF_MERCHANDISER, UserRole.SUPER_ADMIN}
    if current_user.role not in _ALLOWED:
        raise AuthorizationError("Access to the HoM queue is not permitted for your role.")
    repo = DepositRequestRepository(db)
    items = await repo.list_for_role(
        current_user.role, current_user.id,
        status=[RequestStatus.PENDING_HOM_APPROVAL], limit=500, offset=0,
    )
    return [DepositRequestResponse.model_validate(r) for r in items]


class InvoiceCheckResponse(BaseModel):
    duplicate: bool
    request_number: str | None = None


@router.get("/check-invoice", response_model=InvoiceCheckResponse)
async def check_invoice_number(
    current_user: User,
    db: DB,
    field: str = Query(pattern="^(sunshine_invoice_number|supplier_invoice_number)$"),
    value: str = Query(min_length=1, max_length=200),
) -> InvoiceCheckResponse:
    """Pre-submit duplicate check for the request form — is this invoice
    number already used by a live (non-cancelled/rejected) request?
    Creation/update re-validate server-side regardless."""
    conflict = await DepositRequestService(db).find_invoice_conflict(field, value)
    return InvoiceCheckResponse(
        duplicate=conflict is not None,
        request_number=conflict.request_number if conflict else None,
    )


@router.get("/{request_id}", response_model=DepositRequestDetailResponse)
async def get_request(
    request_id: UUID,
    current_user: User,
    db: DB,
) -> DepositRequestDetailResponse:
    from app.models.enums import UserRole
    svc = DepositRequestService(db)
    request = await svc.get_detail(request_id, current_user.id, current_user.role)
    if current_user.role == UserRole.MERCHANDISER and request.created_by != current_user.id:
        raise NotFoundError(f"Deposit request {request_id} not found.")
    response = DepositRequestDetailResponse.model_validate(request)
    actors = await svc.get_last_status_actors([request.id])
    response.last_status_change_by = actors.get(request.id)
    return response


@router.patch("/{request_id}", response_model=DepositRequestResponse)
async def update_request(
    request_id: UUID,
    data: DepositRequestUpdate,
    current_user: User,
    request: Request,
    db: DB,
    background_tasks: BackgroundTasks,
) -> DepositRequestResponse:
    # Invoice-number updates: Super Admin, or Accounts Team from the payment
    # queue (11 Aug 2026 — when a file is changed in whole, Accounts action
    # the approved Invoice Change themselves; both the sunshine and the
    # proforma number are editable). Setting them at creation via the forms
    # is unaffected. Every change is audited per-field with its old and new
    # value by the service layer; duplicate validation applies regardless.
    _INVOICE_EDIT_ROLES = {UserRole.SUPER_ADMIN, UserRole.ACCOUNTS_TEAM}
    if current_user.role not in _INVOICE_EDIT_ROLES and (
        data.sunshine_invoice_number is not None or data.supplier_invoice_number is not None
    ):
        raise AuthorizationError(
            "Invoice numbers can only be updated by a Super Admin or the Accounts Team."
        )
    svc = DepositRequestService(db)
    req = await svc.update(
        request_id, data, current_user.id, current_user.role,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    # estimated_etd drives Grace ETD and therefore cost of fund — reseed the
    # snapshot so edits are reflected without waiting for the bulk job.
    background_tasks.add_task(seed_snapshot_for_request, req.id)
    return DepositRequestResponse.model_validate(req)


@router.delete("/{request_id}", response_model=MessageResponse)
async def delete_request(
    request_id: UUID,
    current_user: User,
    request: Request,
    db: DB,
) -> MessageResponse:
    svc = DepositRequestService(db)
    await svc.soft_delete(
        request_id, current_user.id, current_user.role,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return MessageResponse(message="Request deleted.")


@router.post("/{request_id}/hold", response_model=DepositRequestResponse)
async def hold_request(
    request_id: UUID,
    body: StatusChangeRequest,
    current_user: User,
    request: Request,
    db: DB,
    background_tasks: BackgroundTasks,
) -> DepositRequestResponse:
    from app.models.enums import RequestStatus, UserRole
    svc = DepositRequestService(db)
    target = (
        RequestStatus.HOLD_BY_MERCHANDISER
        if current_user.role in {UserRole.MERCHANDISER}
        else RequestStatus.HOLD_BY_ACCOUNTS
    )
    req = await svc.transition_status(
        request_id, target, current_user.id, current_user.role, body.remarks,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    background_tasks.add_task(
        notify_status_change, request_id, target.value, current_user.role.value, body.remarks
    )
    return DepositRequestResponse.model_validate(req)


@router.post("/{request_id}/resume", response_model=DepositRequestResponse)
async def resume_request(
    request_id: UUID,
    body: StatusChangeRequest,
    current_user: User,
    request: Request,
    db: DB,
    background_tasks: BackgroundTasks,
) -> DepositRequestResponse:
    svc = DepositRequestService(db)
    req = await svc.transition_status(
        request_id,
        RequestStatus.PENDING_PAYMENT,
        current_user.id,
        current_user.role,
        body.remarks,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    background_tasks.add_task(
        notify_status_change, request_id,
        RequestStatus.PENDING_PAYMENT.value, current_user.role.value, body.remarks,
    )
    return DepositRequestResponse.model_validate(req)


@router.post("/{request_id}/cancel", response_model=DepositRequestResponse)
async def cancel_request(
    request_id: UUID,
    body: StatusChangeRequest,
    current_user: User,
    request: Request,
    db: DB,
    background_tasks: BackgroundTasks,
) -> DepositRequestResponse:
    from app.models.enums import UserRole
    svc = DepositRequestService(db)
    target = (
        RequestStatus.CANCELLED_BY_MERCHANDISER
        if current_user.role == UserRole.MERCHANDISER
        else RequestStatus.CANCELLED_BY_ACCOUNTS
    )
    req = await svc.transition_status(
        request_id, target, current_user.id, current_user.role, body.remarks,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    background_tasks.add_task(
        notify_status_change, request_id, target.value, current_user.role.value, body.remarks
    )
    return DepositRequestResponse.model_validate(req)


@router.post("/{request_id}/reject", response_model=DepositRequestResponse)
async def reject_request(
    request_id: UUID,
    body: HomDecisionRequest,
    current_user: User,
    request: Request,
    db: DB,
    background_tasks: BackgroundTasks,
) -> DepositRequestResponse:
    """Accounts reject the whole request — terminal (UAT Aug 2026, items
    12/17/18). The reason is mandatory (HomDecisionRequest enforces it);
    the raising merchandiser AND Head of Merchandiser are notified. The
    invoice numbers become reusable and the merchandiser can no longer
    edit anything on the request."""
    _ALLOWED = {UserRole.ACCOUNTS_TEAM, UserRole.SUPER_ADMIN}
    if current_user.role not in _ALLOWED:
        raise AuthorizationError("Only Accounts Team or Super Admin can reject requests.")
    svc = DepositRequestService(db)
    req = await svc.transition_status(
        request_id, RequestStatus.REJECTED_BY_ACCOUNTS,
        current_user.id, current_user.role, body.remarks,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    background_tasks.add_task(notify_request_rejected_by_accounts, request_id, body.remarks)
    return DepositRequestResponse.model_validate(req)


@router.post("/{request_id}/reopen", response_model=DepositRequestResponse)
async def reopen_request(
    request_id: UUID,
    body: StatusChangeRequest,
    current_user: User,
    request: Request,
    db: DB,
    background_tasks: BackgroundTasks,
) -> DepositRequestResponse:
    svc = DepositRequestService(db)
    req = await svc.transition_status(
        request_id,
        RequestStatus.REOPENED,
        current_user.id,
        current_user.role,
        body.remarks,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    background_tasks.add_task(
        notify_status_change, request_id,
        RequestStatus.REOPENED.value, current_user.role.value, body.remarks,
    )
    return DepositRequestResponse.model_validate(req)


@router.post("/{request_id}/remarks", response_model=DepositRequestResponse)
async def update_remarks(
    request_id: UUID,
    body: StatusChangeRequest,
    current_user: User,
    db: DB,
) -> DepositRequestResponse:
    """Merchandiser adds/updates a remark on their own request. Visible to all roles."""
    svc = DepositRequestService(db)
    req = await svc.update_remarks(request_id, current_user.id, current_user.role, body.remarks)
    return DepositRequestResponse.model_validate(req)


@router.post("/{request_id}/hom-approve", response_model=DepositRequestResponse)
async def hom_approve(
    request_id: UUID,
    body: HomDecisionRequest,
    current_user: User,
    request: Request,
    db: DB,
    background_tasks: BackgroundTasks,
) -> DepositRequestResponse:
    """HoM approves a pending request — moves it to pending_payment for Accounts.
    The reason is mandatory; the raising merchandiser is notified."""
    _ALLOWED = {UserRole.HEAD_OF_MERCHANDISER, UserRole.SUPER_ADMIN}
    if current_user.role not in _ALLOWED:
        raise AuthorizationError("Only Head of Merchandiser or Super Admin can approve.")
    svc = DepositRequestService(db)
    req = await svc.transition_status(
        request_id, RequestStatus.PENDING_PAYMENT,
        current_user.id, current_user.role, body.remarks,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    background_tasks.add_task(notify_hom_decision, request_id, "approved", body.remarks)
    # The request just entered the payment queue — Accounts learn about it the
    # same way they do for directly-created requests.
    background_tasks.add_task(notify_request_created, request_id)
    return DepositRequestResponse.model_validate(req)


@router.post("/{request_id}/hom-reject", response_model=DepositRequestResponse)
async def hom_reject(
    request_id: UUID,
    body: HomDecisionRequest,
    current_user: User,
    request: Request,
    db: DB,
    background_tasks: BackgroundTasks,
) -> DepositRequestResponse:
    """HoM rejects a pending request — moves it to rejected_by_hom (terminal).
    The reason is mandatory; the raising merchandiser is notified."""
    _ALLOWED = {UserRole.HEAD_OF_MERCHANDISER, UserRole.SUPER_ADMIN}
    if current_user.role not in _ALLOWED:
        raise AuthorizationError("Only Head of Merchandiser or Super Admin can reject.")
    svc = DepositRequestService(db)
    req = await svc.transition_status(
        request_id, RequestStatus.REJECTED_BY_HOM,
        current_user.id, current_user.role, body.remarks,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    background_tasks.add_task(notify_hom_decision, request_id, "rejected", body.remarks)
    return DepositRequestResponse.model_validate(req)
