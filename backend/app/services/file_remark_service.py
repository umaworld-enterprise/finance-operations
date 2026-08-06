"""File Remarks — tracked merchandiser → Accounts communication on a file
(CIO batch 2, Aug 2026).

Raise: merchandiser on their OWN request (any status — locked/processed files
are the whole point), or Accounts/Super Admin on any request.
Decide: Accounts/Super Admin resolve with an optional response note.
A file remark moves no money — Accounts act manually (e.g. via the
super-admin invoice editor); Adjust Invoices remains the financial mechanism.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
)
from app.models.deposit_request import DepositRequest
from app.models.enums import UserRole
from app.models.file_remark import FileRemark, FileRemarkStatus
from app.models.masters import Supplier, User
from app.repositories.deposit_request_repo import DepositRequestRepository
from app.schemas.file_remark import FileRemarkCreate, FileRemarkResponse
from app.services.audit_service import AuditService

_DECIDER_ROLES = {UserRole.ACCOUNTS_TEAM, UserRole.SUPER_ADMIN}
_RAISER_ROLES = _DECIDER_ROLES | {UserRole.MERCHANDISER}
_VIEWER_ROLES = _RAISER_ROLES | {UserRole.FINANCE_ADMIN}

_CATEGORY_LABELS = {
    "invoice_number_change": "Invoice number change",
    "invoice_split": "Invoice split",
    "other": "Other",
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
        # Deliberately NO lock/status check: paid & processed (locked) files
        # are precisely what this channel exists for.

        remark = FileRemark(
            deposit_request_id=request.id,
            category=data.category,
            old_file_number=(data.old_file_number or "").strip() or None,
            new_file_number=(data.new_file_number or "").strip() or None,
            remark=data.remark.strip(),
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

    async def resolve(
        self,
        remark_id: UUID,
        user_id: UUID,
        role: UserRole,
        response_note: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> FileRemark:
        if role not in _DECIDER_ROLES:
            raise AuthorizationError("Only Accounts Team or Super Admin can resolve file remarks.")
        remark = await self._session.get(FileRemark, remark_id)
        if not remark:
            raise NotFoundError("File remark not found.")
        if remark.status != FileRemarkStatus.OPEN.value:
            raise ConflictError("This file remark is already resolved.")

        remark.status = FileRemarkStatus.RESOLVED.value
        remark.resolved_by = user_id
        remark.resolved_at = datetime.now(timezone.utc)
        remark.response_note = (response_note or "").strip() or None
        await self._session.flush()

        request = await self._session.get(DepositRequest, remark.deposit_request_id)
        request_number = request.request_number if request else "?"
        await self._audit.record_update(
            "file_remarks", remark.id, user_id,
            field_name="status",
            old_value=FileRemarkStatus.OPEN.value,
            new_value=(
                FileRemarkStatus.RESOLVED.value
                + (f" — {remark.response_note}" if remark.response_note else "")
            ),
            ip_address=ip_address, user_agent=user_agent,
        )
        if request:
            await self._audit.record_update(
                "deposit_requests", request.id, user_id,
                field_name="file_remark_resolved",
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
            parts.append(f"old file {remark.old_file_number}")
        if remark.new_file_number:
            parts.append(f"new file {remark.new_file_number}")
        parts.append(remark.remark)
        return " — ".join(parts)
