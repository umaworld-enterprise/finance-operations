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
    # Renamed "Invoice Change" → "File Change" (4 Sep 2026) — stored category
    # value stays "invoice_amount_change".
    "invoice_amount_change": "File Change",
    # New (4 Sep 2026, migration 0033): the invoice's VALUE changes — the
    # merchandiser proposes a revised amount; Accounts approve, then apply
    # the final revised amount as a separate step.
    "invoice_value_change": "Invoice Value Change",
}


def category_label(category: str) -> str:
    return _CATEGORY_LABELS.get(category, category)


def _root_file_number(request: DepositRequest) -> str:
    """The request's own file reference: sunshine invoice number, else the
    proforma number, else the request number (10 Aug rework)."""
    return (
        (request.sunshine_invoice_number or "").strip()
        or (request.supplier_invoice_number or "").strip()
        or request.request_number
    )


class FileRemarkService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._request_repo = DepositRequestRepository(session)
        self._audit = AuditService(session)

    async def live_files_for_request(self, request: DepositRequest) -> dict[str, "Decimal"]:
        """The request's CURRENT file set (19 Aug 2026 chain support): start
        from the root file with the full deposit, then replay every APPROVED
        remark in decision order — a split moves value from its parent file
        into the new file numbers (the parent keeps the balance, and drops
        out once fully consumed); an invoice change replaces its parent file
        number with the new one. The result is what the merchandiser can
        select for the next split / invoice change — chains of any depth,
        always anchored to (and audited on) this core request."""
        from decimal import Decimal

        files: dict[str, Decimal] = {
            _root_file_number(request): Decimal(str(request.deposit_amount))
        }
        result = await self._session.execute(
            select(FileRemark)
            .where(
                FileRemark.deposit_request_id == request.id,
                FileRemark.status == FileRemarkStatus.APPROVED.value,
            )
            .order_by(FileRemark.resolved_at.asc().nulls_last(), FileRemark.created_at.asc())
        )
        for r in result.scalars().all():
            old = (r.old_file_number or "").strip()
            if r.category == "invoice_split" and r.split_targets:
                total = sum(
                    (Decimal(str(t.get("amount") or 0)) for t in r.split_targets),
                    Decimal("0"),
                )
                if old in files:
                    files[old] -= total
                    if files[old] <= 0:
                        del files[old]
                for t in r.split_targets:
                    number = (t.get("file_number") or "").strip()
                    if number:
                        files[number] = files.get(number, Decimal("0")) + Decimal(
                            str(t.get("amount") or 0)
                        )
            elif r.category == "invoice_amount_change" and r.new_file_number:
                carried = files.pop(old, None)
                files[r.new_file_number] = (
                    Decimal(str(r.new_amount)) if r.new_amount is not None else (carried or Decimal("0"))
                )
            elif r.category == "invoice_value_change" and r.new_amount is not None:
                # Value change (4 Sep 2026): the file keeps its number, its
                # amount becomes the revised figure — but ONLY once Accounts
                # applied it (approved rows with NULL new_amount are still
                # awaiting the revised amount and change nothing).
                if old in files:
                    files[old] = Decimal(str(r.new_amount))
        return files

    async def selectable_files(self, user_id: UUID, role: UserRole) -> list[dict]:
        """Every file the raiser can pick in the New File Remark dropdown:
        the live files (root + split-born + invoice-changed, any depth) of
        each payment-completed request, minus files already under an OPEN
        remark. Merchandisers see their own requests; accounts / super see
        all."""
        if role not in _RAISER_ROLES:
            raise AuthorizationError("Your role cannot raise file remarks.")
        stmt = select(DepositRequest).where(
            DepositRequest.is_deleted == False,  # noqa: E712
            DepositRequest.current_status == RequestStatus.PAYMENT_PROCESSED,
        )
        if role == UserRole.MERCHANDISER:
            stmt = stmt.where(DepositRequest.created_by == user_id)
        requests = list((await self._session.execute(stmt)).scalars().all())
        if not requests:
            return []
        from sqlalchemy import and_, or_

        # Held back: files under an OPEN remark, plus files whose approved
        # Invoice Value Change is still awaiting the revised amount (4 Sep
        # 2026) — their amount is about to move, so no new remark yet.
        open_rows = (
            await self._session.execute(
                select(FileRemark.deposit_request_id, FileRemark.old_file_number).where(
                    FileRemark.deposit_request_id.in_([r.id for r in requests]),
                    or_(
                        FileRemark.status == FileRemarkStatus.OPEN.value,
                        and_(
                            FileRemark.category == "invoice_value_change",
                            FileRemark.status == FileRemarkStatus.APPROVED.value,
                            FileRemark.new_amount.is_(None),
                        ),
                    ),
                )
            )
        ).all()
        under_open = {(rid, (num or "").strip()) for rid, num in open_rows}
        out: list[dict] = []
        for req in requests:
            live = await self.live_files_for_request(req)
            for number, amount in live.items():
                if (req.id, number) in under_open:
                    continue  # already being actioned — one open remark per file
                out.append(
                    {
                        "deposit_request_id": str(req.id),
                        "request_number": req.request_number,
                        "file_number": number,
                        "amount": float(amount),
                        "currency": req.currency.value if req.currency else None,
                        "is_root": number == _root_file_number(req),
                    }
                )
        out.sort(key=lambda r: (r["request_number"], not r["is_root"], r["file_number"]))
        return out

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

        from decimal import Decimal

        # The selected FILE (19 Aug 2026 chain support): the root file or any
        # live file born from an approved split / invoice change on this
        # request — validated against the server-replayed live set, which
        # also supplies the old amount. Every chained remark stays anchored
        # to this core request, so its audit trail records the whole chain.
        live = await self.live_files_for_request(request)
        if data.file_number and data.file_number.strip():
            parent_file = data.file_number.strip()
            if parent_file not in live:
                raise ValidationError(
                    f"'{parent_file}' is not a live file of this request — "
                    "pick a file from the dropdown."
                )
            deposit = live[parent_file]
        else:
            # Legacy callers without a file selection act on the root file.
            parent_file = _root_file_number(request)
            deposit = live.get(parent_file, Decimal(str(request.deposit_amount)))

        # Amounts can never exceed the selected file's amount (7 Aug fix —
        # the old amount is the ceiling for what can be moved or split).
        if data.category == "invoice_split" and data.split_targets:
            total = sum((t.amount for t in data.split_targets), Decimal("0"))
            if total > deposit:
                raise BusinessRuleError(
                    f"The split amounts total {total}, which exceeds the file's "
                    f"amount of {deposit}."
                )
        # Invoice Change (19 Aug 2026): a whole-invoice change keeps the
        # amount — new_amount is server-derived below, no ceiling to check.
        remark = FileRemark(
            deposit_request_id=request.id,
            category=data.category,
            old_file_number=parent_file,
            # Server-derived (4 Aug follow-up; chain-aware 19 Aug 2026): the
            # old amount is the SELECTED file's live amount — pre-populated
            # and non-editable in the UI, never accepted from the client.
            old_amount=deposit,
            new_file_number=(data.new_file_number or "").strip() or None,
            # Server-derived (19 Aug 2026): the whole invoice changes number,
            # not value — the new amount IS the selected file's amount,
            # locked in the UI and never accepted from the client.
            new_amount=(
                deposit
                if data.category == "invoice_amount_change"
                else None
            ),
            # Invoice Value Change (4 Sep 2026): the merchandiser's PROPOSED
            # figure — the final amount lands in new_amount only when Accounts
            # apply it after approval. No ceiling: a revision can go up or down.
            proposed_amount=(
                data.proposed_amount if data.category == "invoice_value_change" else None
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

    async def apply_revised_amount(
        self,
        remark_id: UUID,
        revised_amount: "Decimal",
        user_id: UUID,
        role: UserRole,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> FileRemark:
        """Accounts apply the final revised amount on an APPROVED Invoice
        Value Change (4 Sep 2026) — the separate step after approval. The
        figure lands in new_amount, takes effect in the live-file ledger,
        and is applied exactly once."""
        if role not in _DECIDER_ROLES:
            raise AuthorizationError(
                "Only Accounts Team or Super Admin can update the revised amount."
            )
        remark = await self._session.get(FileRemark, remark_id)
        if not remark:
            raise NotFoundError("File remark not found.")
        if remark.category != "invoice_value_change":
            raise BusinessRuleError(
                "Only Invoice Value Change remarks carry a revised amount."
            )
        if remark.status != FileRemarkStatus.APPROVED.value:
            raise ConflictError(
                "The revised amount can only be updated on an APPROVED "
                "Invoice Value Change."
            )
        if remark.new_amount is not None:
            raise ConflictError(
                "The revised amount has already been applied on this remark."
            )

        remark.new_amount = revised_amount
        await self._session.flush()

        request = await self._session.get(DepositRequest, remark.deposit_request_id)
        request_number = request.request_number if request else "?"
        summary = (
            f"Revised amount on {remark.old_file_number or request_number}: "
            f"{remark.old_amount} → {revised_amount}"
            + (f" (proposed {remark.proposed_amount})" if remark.proposed_amount is not None else "")
        )
        await self._audit.record_update(
            "file_remarks", remark.id, user_id,
            field_name="new_amount",
            old_value=None, new_value=str(revised_amount),
            ip_address=ip_address, user_agent=user_agent,
        )
        if request:
            await self._audit.record_update(
                "deposit_requests", request.id, user_id,
                field_name="file_remark_amount_updated",
                old_value=None, new_value=summary,
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
        if remark.proposed_amount is not None:
            parts.append(f"proposed amount {remark.proposed_amount}")
        if remark.split_targets:
            targets = ", ".join(
                f"{t.get('file_number')} ({t.get('amount')})" for t in remark.split_targets
            )
            parts.append(f"splits to {targets}")
        if remark.remark:
            parts.append(remark.remark)
        return " — ".join(parts)
