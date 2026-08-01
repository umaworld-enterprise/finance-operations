"""Tranche-level endpoints — merchandiser edits, Accounts payments, TT copies,
request-level audit trail and adjustment traceability."""

import asyncio
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.snapshot_job import seed_snapshot_for_request
from app.core.database import get_db_session
from app.core.dependencies import CurrentUser, get_current_user
from app.core.exceptions import NotFoundError, ValidationError
from app.integrations.google_drive.drive_service import (
    build_tt_copy_filename,
    upload_tt_copy_to_drive,
    validate_tt_copy,
)
from app.models.deposit_request import DepositRequest
from app.models.enums import UserRole
from app.models.tranche import PaymentTranche
from app.repositories.audit_repo import AuditRepository
from app.repositories.deposit_request_repo import DepositRequestRepository
from app.schemas.common import MessageResponse
from app.schemas.deposit_request import RequestAuditEntryResponse
from app.schemas.tranche import (
    AdjustmentResponse,
    TrancheCreate,
    TranchePaymentDetailsUpdate,
    TrancheResponse,
    TrancheUpdate,
)
from app.services.adjustment_service import AdjustmentService
from app.services.notification_service import (
    notify_tranche_event,
    notify_tranche_removed,
    notify_tranche_updated,
)
from app.services.tranche_service import _MERCHANDISER_EDITABLE_STATUSES, TrancheService

router = APIRouter(prefix="/requests/{request_id}/tranches", tags=["tranches"])

DB = Annotated[AsyncSession, Depends(get_db_session)]
User = Annotated[CurrentUser, Depends(get_current_user)]


def _ip(req: Request) -> str | None:
    forwarded = req.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return req.client.host if req.client else None


async def _request_or_404(
    db: AsyncSession, request_id: UUID, current_user: CurrentUser
) -> DepositRequest:
    """Load the request applying the same visibility rule as GET /requests/{id}:
    merchandisers only see their own records."""
    request = await DepositRequestRepository(db).get_for_validation(request_id)
    if not request:
        raise NotFoundError(f"Request {request_id} not found.")
    if current_user.role == UserRole.MERCHANDISER and request.created_by != current_user.id:
        raise NotFoundError(f"Request {request_id} not found.")
    return request


def _tranche_response(tranche: PaymentTranche, total_invoice_amount: object) -> TrancheResponse:
    return TrancheResponse.model_validate(tranche).with_percentage(
        Decimal(str(total_invoice_amount))
    )


@router.get("", response_model=list[TrancheResponse])
async def list_tranches(
    request_id: UUID,
    current_user: User,
    db: DB,
) -> list[TrancheResponse]:
    request = await _request_or_404(db, request_id, current_user)
    tranches = await TrancheService(db).list_for_request(request_id)
    return [_tranche_response(t, request.total_supplier_invoice_amount) for t in tranches]


@router.get("/modifiable")
async def tranches_modifiable(
    request_id: UUID,
    current_user: User,
    db: DB,
) -> dict:
    """Can the merchandiser still modify/add/delete tranches on this request?
    Blocked once the request leaves pending or Accounts write anything
    (Aug 2026 batch, item 2.3). Returns the human-readable reason when not."""
    request = await _request_or_404(db, request_id, current_user)
    if request.current_status not in _MERCHANDISER_EDITABLE_STATUSES:
        reason: str | None = (
            "the request is no longer pending "
            f"(current status: {request.current_status.value})"
        )
    else:
        reason = await TrancheService(db).accounts_touched_reason(request_id)
    return {"modifiable": reason is None, "reason": reason}


@router.post("", response_model=TrancheResponse, status_code=201)
async def add_tranche(
    request_id: UUID,
    data: TrancheCreate,
    current_user: User,
    request: Request,
    db: DB,
    background_tasks: BackgroundTasks,
) -> TrancheResponse:
    """Merchandiser adds a tranche to their own pending, untouched request.
    Accounts Team is notified of the change."""
    svc = TrancheService(db)
    tranche = await svc.add_tranche(
        request_id, data, current_user.id, current_user.role,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    req = await DepositRequestRepository(db).get_for_validation(request_id)
    background_tasks.add_task(seed_snapshot_for_request, request_id)
    background_tasks.add_task(
        notify_tranche_updated, request_id, tranche.id,
        f"added with amount {tranche.amount}",
    )
    return _tranche_response(tranche, req.total_supplier_invoice_amount)


@router.delete("/{tranche_id}", response_model=MessageResponse)
async def delete_tranche(
    request_id: UUID,
    tranche_id: UUID,
    current_user: User,
    request: Request,
    db: DB,
    background_tasks: BackgroundTasks,
) -> MessageResponse:
    """Merchandiser deletes an unpaid tranche from their own pending,
    untouched request. Accounts Team is notified of the change."""
    svc = TrancheService(db)
    label = await svc.delete_tranche(
        request_id, tranche_id, current_user.id, current_user.role,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    background_tasks.add_task(seed_snapshot_for_request, request_id)
    background_tasks.add_task(notify_tranche_removed, request_id, label)
    return MessageResponse(message=f"{label} deleted.")


@router.patch("/{tranche_id}", response_model=TrancheResponse)
async def update_tranche(
    request_id: UUID,
    tranche_id: UUID,
    data: TrancheUpdate,
    current_user: User,
    request: Request,
    db: DB,
    background_tasks: BackgroundTasks,
) -> TrancheResponse:
    """Merchandiser edits an UNPAID tranche (amount / tentative payment date)
    on their own request. Accounts Team is notified of the change."""
    svc = TrancheService(db)
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    tranche = await svc.update_tranche(
        request_id, tranche_id, data, current_user.id, current_user.role,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    req = await DepositRequestRepository(db).get_for_validation(request_id)
    # deposit_amount may have changed — keep the analytics snapshot in step.
    background_tasks.add_task(seed_snapshot_for_request, request_id)
    summary = ", ".join(f"{k} → {v}" for k, v in changes.items())
    background_tasks.add_task(notify_tranche_updated, request_id, tranche_id, summary)
    return _tranche_response(tranche, req.total_supplier_invoice_amount)


@router.patch("/{tranche_id}/payment-details", response_model=TrancheResponse)
async def update_tranche_payment_details(
    request_id: UUID,
    tranche_id: UUID,
    data: TranchePaymentDetailsUpdate,
    current_user: User,
    request: Request,
    db: DB,
) -> TrancheResponse:
    """Accounts record per-tranche payment details (payment date, bank,
    optional reference number) ahead of marking the tranche paid."""
    svc = TrancheService(db)
    tranche = await svc.update_payment_details(
        request_id, tranche_id, data, current_user.id, current_user.role,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    req = await DepositRequestRepository(db).get_for_validation(request_id)
    return _tranche_response(tranche, req.total_supplier_invoice_amount)


@router.post("/{tranche_id}/pay", response_model=TrancheResponse)
async def pay_tranche(
    request_id: UUID,
    tranche_id: UUID,
    current_user: User,
    request: Request,
    db: DB,
    background_tasks: BackgroundTasks,
) -> TrancheResponse:
    """Accounts explicitly mark an unpaid tranche as paid (Aug 2026, item 3.1).

    Requires the tranche's TT copy AND payment details (payment date + bank)
    to already be recorded — the TT upload itself never changes status.
    Paying the last tranche completes and locks the request."""
    svc = TrancheService(db)
    tranche = await svc.pay_tranche(
        request_id, tranche_id, current_user.id, current_user.role,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    req = await DepositRequestRepository(db).get_for_validation(request_id)
    background_tasks.add_task(seed_snapshot_for_request, request_id)
    background_tasks.add_task(notify_tranche_event, request_id, tranche_id, "paid")
    return _tranche_response(tranche, req.total_supplier_invoice_amount)


@router.post("/{tranche_id}/tt-copy", response_model=TrancheResponse)
async def upload_tranche_tt_copy(
    request_id: UUID,
    tranche_id: UUID,
    file: UploadFile,
    current_user: User,
    request: Request,
    db: DB,
    background_tasks: BackgroundTasks,
) -> TrancheResponse:
    """Upload the bank's TT copy against a specific tranche.

    Attach only — the tranche's status does NOT change (Aug 2026, item 3.1).
    Marking it paid is a separate explicit action once payment details are
    also recorded. The merchandiser is notified of the attachment.
    """
    content = await file.read()
    error = validate_tt_copy(file.content_type, len(content))
    if error:
        raise ValidationError(error)

    deposit_request = await DepositRequestRepository(db).get_for_validation(request_id)
    if not deposit_request:
        raise NotFoundError(f"Request {request_id} not found.")

    svc = TrancheService(db)
    tranches = await svc.list_for_request(request_id)
    target = next((t for t in tranches if t.id == tranche_id), None)
    if target is None:
        raise NotFoundError(f"Tranche {tranche_id} not found on this request.")

    filename = build_tt_copy_filename(
        deposit_request.request_number, file.content_type,
        tranche_number=target.tranche_number,
    )
    file_id, link = await asyncio.to_thread(
        upload_tt_copy_to_drive, content, filename, file.content_type
    )

    tranche = await svc.attach_tt_copy(
        request_id, tranche_id,
        tt_copy_url=link,
        tt_copy_file_id=file_id,
        tt_copy_filename=filename,
        user_id=current_user.id,
        role=current_user.role,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    background_tasks.add_task(seed_snapshot_for_request, request_id)
    background_tasks.add_task(notify_tranche_event, request_id, tranche_id, "tt_attached")
    return _tranche_response(tranche, deposit_request.total_supplier_invoice_amount)


# ── Request-level traceability ────────────────────────────────────────────────

audit_router = APIRouter(prefix="/requests/{request_id}", tags=["deposit-requests"])


@audit_router.get("/audit", response_model=list[RequestAuditEntryResponse])
async def request_audit_trail(
    request_id: UUID,
    current_user: User,
    db: DB,
) -> list[RequestAuditEntryResponse]:
    """Combined audit history for the request, its tranches and any invoice
    adjustments touching them."""
    await _request_or_404(db, request_id, current_user)
    tranche_ids = [t.id for t in await TrancheService(db).list_for_request(request_id)]
    adjustment_ids = [
        a.id for a in await AdjustmentService(db).list_for_request(request_id)
    ]
    from app.repositories.payment_repo import PaymentRepository
    payment = await PaymentRepository(db).get_by_request_id(request_id)
    logs = await AuditRepository(db).list_for_entity_scope(
        [
            ("deposit_requests", [request_id]),
            ("payment_details", [payment.id] if payment else []),
            ("payment_tranches", tranche_ids),
            ("invoice_adjustments", adjustment_ids),
        ]
    )
    return [
        RequestAuditEntryResponse(
            id=log.id,
            entity_name=log.entity_name,
            entity_id=log.entity_id,
            field_name=log.field_name,
            old_value=log.old_value,
            new_value=log.new_value,
            action=log.action,
            changed_by_name=log.changed_by_user.full_name if log.changed_by_user else None,
            changed_by_email=log.changed_by_user.email if log.changed_by_user else None,
            changed_at=log.changed_at,
        )
        for log in logs
    ]


@audit_router.get("/adjustments", response_model=list[AdjustmentResponse])
async def request_adjustments(
    request_id: UUID,
    current_user: User,
    db: DB,
) -> list[AdjustmentResponse]:
    """Adjustments where this request's tranches are source or destination —
    reallocations are traceable from both sides."""
    await _request_or_404(db, request_id, current_user)
    return await AdjustmentService(db).list_for_request(request_id)
