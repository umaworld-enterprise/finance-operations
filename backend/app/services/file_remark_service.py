"""File Remarks — tracked merchandiser → Accounts communication on a file
(CIO batch 2, Aug 2026).

Raise: merchandiser on their OWN request (any status — locked/processed files
are the whole point), or Accounts/Super Admin on any request.
Decide (UAT Aug 2026, item 14): Accounts/Super Admin APPROVE (processed) with
an optional note, or REJECT with a mandatory reason — the raiser is notified
either way. A file remark moves no money — Accounts act manually (e.g. via
the super-admin invoice editor); Adjust Invoices remains the financial
mechanism.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import (
    AuthorizationError,
    BusinessRuleError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.models.deposit_request import DepositRequest
from app.models.enums import RequestStatus, UserRole
from app.models.file_remark import FileRemark, FileRemarkStatus
from app.models.masters import Supplier, User
from app.repositories.deposit_request_repo import DepositRequestRepository
from app.schemas.file_remark import FileRemarkCreate, FileRemarkResponse
from app.services.audit_service import AuditService

_DECIDER_ROLES = {UserRole.ACCOUNTS_TEAM, UserRole.SUPER_ADMIN}
_RAISER_ROLES = _DECIDER_ROLES | {UserRole.MERCHANDISER}
_VIEWER_ROLES = _RAISER_ROLES | {UserRole.FINANCE_ADMIN}

_CATEGORY_LABELS = {
    "invoice_split": "Split Invoices",
    # Renamed from "Invoice amount changes" (11 Aug 2026) — stored category
    # value stays "invoice_amount_change".
    "invoice_amount_change": "Invoice Change",
}


def category_label(category: str) -> str:
    return _CATEGORY_LABELS.get(category, category)


class FileRemarkService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._request_repo = DepositRequestRepository(session)
        self._audit = AuditService(session)

    async def create(
        self,
        data: FileRemarkCreate,
        user_id: UUID,
        role: UserRole,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> FileRemark:
        if role not in _RAISER_ROLES:
            raise AuthorizationError("Your role cannot raise file remarks.")

        request = await self._request_repo.get_for_validation(data.deposit_request_id)
        if not request:
            raise NotFoundError(f"Request {data.deposit_request_id} not found.")
        if role == UserRole.MERCHANDISER and request.created_by != user_id:
            raise AuthorizationError("You can only raise file remarks on your own requests.")
        # Rule (4 Aug rework): only payment-completed files are eligible —
        # splits and amount moves only make sense once the deposit is paid.
        if request.current_status != RequestStatus.PAYMENT_PROCESSED:
            raise BusinessRuleError(
                "File remarks can only be raised on payment-completed files "
                f"(current status: {request.current_status.value})."
            )

        # Amounts can never exceed the file's deposit amount (7 Aug fix —
        # the old amount is the ceiling for what can be moved or split).
        from decimal import Decimal

        deposit = Decimal(str(request.deposit_amount))
        if data.category == "invoice_split" and data.split_targets:
            total = sum((t.amount for t in data.split_targets), Decimal("0"))
            if total > deposit:
                raise BusinessRuleError(
                    f"The split amounts total {total}, which exceeds the file's "
                    f"deposit amount of {deposit}."
                )
        # Invoice Change (19 Aug 2026): a whole-invoice change keeps the
        # amount — new_amount is server-derived below, no ceiling to check.

        # Server-derived parent reference (10 Aug rework): the "old file" is
        # always the selected request itself — its sunshine invoice number
        # when present, else the proforma number, else the request number.
        # Never accepted from the client; recorded for BOTH categories so a
        # split's history shows which file it split from.
        parent_file = (
            (request.sunshine_invoice_number or "").strip()
            or (request.supplier_invoice_number or "").strip()
            or request.request_number
        )
        remark = FileRemark(
            deposit_request_id=request.id,
            category=data.category,
            old_file_number=parent_file,
            # Server-derived (4 Aug follow-up): the old amount is always the
            # selected file's deposit amount — pre-populated and non-editable
            # in the UI, never accepted from the client.
            old_amount=request.deposit_amount,
            new_file_number=(data.new_file_number or "").strip() or None,
            # Server-derived (19 Aug 2026): the whole invoice changes number,
            # not value — the new amount IS the file's deposit amount, locked
            # in the UI and never accepted from the client.
            new_amount=(
                request.deposit_amount
                if data.category == "invoice_amount_change"
                else None
            ),
            split_targets=(
                [
                    {"file_number": t.file_number.strip(), "amount": float(t.amount)}
                    for t in data.split_targets
                ]
                if data.split_targets
                else None
            ),
            remark=(data.remark or "").strip() or None,
            status=FileRemarkStatus.OPEN.value,
            created_by=user_id,
        )
        self._session.add(remark)
        await self._session.flush()

        summary = self._summary(remark, request.request_number)
        await self._audit.record_create(
            "file_remarks", remark.id, user_id,
            new_value=summary,
            ip_address=ip_address, user_agent=user_agent,
        )
        # Visible from the request-level audit trail too.
        await self._audit.record_update(
            "deposit_requests", request.id, user_id,
            field_name="file_remark_raised",
            old_value=None, new_value=summary,
            ip_address=ip_address, user_agent=user_agent,
        )
        return remark

    async def decide(
        self,
        remark_id: UUID,
        decision: str,
        user_id: UUID,
        role: UserRole,
        response_note: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> FileRemark:
        """Accounts approve (processed) or reject an open remark (UAT Aug
        2026, item 14). A rejection requires a reason; an approval note is
        optional. The raiser is notified by the caller either way."""
        if role not in _DECIDER_ROLES:
            raise AuthorizationError("Only Accounts Team or Super Admin can decide file remarks.")
        if decision not in (FileRemarkStatus.APPROVED.value, FileRemarkStatus.REJECTED.value):
            raise ValidationError("Decision must be 'approved' or 'rejected'.")
        note = (response_note or "").strip() or None
        if decision == FileRemarkStatus.REJECTED.value and not note:
            raise ValidationError("A reason is mandatory when rejecting a file remark.")
        remark = await self._session.get(FileRemark, remark_id)
        if not remark:
            raise NotFoundError("File remark not found.")
        if remark.status != FileRemarkStatus.OPEN.value:
            raise ConflictError("This file remark has already been decided.")

        remark.status = decision
        remark.resolved_by = user_id
        remark.resolved_at = datetime.now(timezone.utc)
        remark.response_note = note
        await self._session.flush()

        request = await self._session.get(DepositRequest, remark.deposit_request_id)
        request_number = request.request_number if request else "?"
        await self._audit.record_update(
            "file_remarks", remark.id, user_id,
            field_name="status",
            old_value=FileRemarkStatus.OPEN.value,
            new_value=decision + (f" — {note}" if note else ""),
            ip_address=ip_address, user_agent=user_agent,
        )
        if request:
            await self._audit.record_update(
                "deposit_requests", request.id, user_id,
                field_name=f"file_remark_{decision}",
                old_value=None,
                new_value=self._summary(remark, request_number),
                ip_address=ip_address, user_agent=user_agent,
            )
        return remark

    async def list(
        self,
        user_id: UUID,
        role: UserRole,
        status: str | None = None,
        deposit_request_id: UUID | None = None,
        limit: int = 200,
    ) -> list[FileRemarkResponse]:
        """Merchandisers see their own; accounts/finance/super see all."""
        if role not in _VIEWER_ROLES:
            raise AuthorizationError("Access to file remarks is not permitted for your role.")
        stmt = (
            select(FileRemark)
            .options(
                selectinload(FileRemark.deposit_request),
                selectinload(FileRemark.creator),
                selectinload(FileRemark.resolver),
            )
            .order_by(FileRemark.created_at.desc())
            .limit(limit)
        )
        if role == UserRole.MERCHANDISER:
            stmt = stmt.where(FileRemark.created_by == user_id)
        if status:
            stmt = stmt.where(FileRemark.status == status)
        if deposit_request_id:
            stmt = stmt.where(FileRemark.deposit_request_id == deposit_request_id)
        remarks = list((await self._session.execute(stmt)).scalars().all())
        out: list[FileRemarkResponse] = []
        for r in remarks:
            resp = FileRemarkResponse.model_validate(r)
            if r.deposit_request:
                resp.request_number = r.deposit_request.request_number
                resp.sunshine_invoice_number = r.deposit_request.sunshine_invoice_number
                resp.currency = (
                    r.deposit_request.currency.value if r.deposit_request.currency else None
                )
                supplier = await self._session.get(Supplier, r.deposit_request.supplier_id)
                resp.supplier_name = supplier.name if supplier else None
            resp.created_by_name = r.creator.full_name if r.creator else None
            resp.resolved_by_name = r.resolver.full_name if r.resolver else None
            out.append(resp)
        return out

    @staticmethod
    def _summary(remark: FileRemark, request_number: str) -> str:
        parts = [f"{category_label(remark.category)} on {request_number}"]
        if remark.old_file_number:
            parts.append(
                f"old file {remark.old_file_number}"
                + (f" ({remark.old_amount})" if remark.old_amount is not None else "")
            )
        if remark.new_file_number:
            parts.append(
                f"new file {remark.new_file_number}"
                + (f" ({remark.new_amount})" if remark.new_amount is not None else "")
            )
        if remark.split_targets:
            targets = ", ".join(
                f"{t.get('file_number')} ({t.get('amount')})" for t in remark.split_targets
            )
            parts.append(f"splits to {targets}")
        if remark.remark:
            parts.append(remark.remark)
        return " — ".join(parts)
