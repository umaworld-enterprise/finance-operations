"""Tranche-level workflow — merchandiser edits, Accounts payments, TT copies.

State rules enforced server-side (not only in the UI):
- Only the request's own merchandiser (or Super Admin) may edit a tranche,
  and only while it is UNPAID; editable fields are amount and tentative date.
- Only Accounts Team / Super Admin may pay a tranche or attach its TT copy.
- A paid tranche is immutable through normal editing; double payment and
  duplicate TT uploads are rejected under a row-level lock.
- When the last unpaid tranche is paid, the request transitions to
  payment_processed and locks — same rules the request-level flow enforced.
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.domain.rules.lock_rules import assert_record_not_locked
from app.domain.rules.status_transitions import assert_transition_allowed
from app.models.deposit_request import DepositRequest
from app.models.enums import RequestStatus, TrancheStatus, UserRole
from app.models.tranche import PaymentTranche
from app.models.workflow import StatusHistory
from app.repositories.deposit_request_repo import DepositRequestRepository
from app.repositories.tranche_repo import TrancheRepository
from app.schemas.tranche import TrancheUpdate
from app.services.audit_service import AuditService

# Statuses in which the requested advance is still "live" — tranches remain
# editable by the merchandiser and payable by Accounts (payment itself is
# further restricted to pending_payment below).
_TERMINAL_STATUSES = {
    RequestStatus.CANCELLED_BY_MERCHANDISER,
    RequestStatus.CANCELLED_BY_ACCOUNTS,
    RequestStatus.REJECTED_BY_HOM,
}

_ACCOUNTS_ROLES = {UserRole.ACCOUNTS_TEAM, UserRole.SUPER_ADMIN}


class TrancheService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = TrancheRepository(session)
        self._request_repo = DepositRequestRepository(session)
        self._audit = AuditService(session)

    # ── Reads ─────────────────────────────────────────────────────────────────

    async def list_for_request(self, request_id: UUID) -> list[PaymentTranche]:
        return await self._repo.list_for_request(request_id)

    # ── Merchandiser edits ────────────────────────────────────────────────────

    async def update_tranche(
        self,
        request_id: UUID,
        tranche_id: UUID,
        data: TrancheUpdate,
        user_id: UUID,
        role: UserRole,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> PaymentTranche:
        """Edit amount / tentative date of an UNPAID tranche.

        Returns the updated tranche; the caller schedules the Accounts Team
        notification so Accounts always works from the latest values.
        """
        request = await self._get_request_or_404(request_id)

        if role not in {UserRole.MERCHANDISER, UserRole.SUPER_ADMIN}:
            raise AuthorizationError("Only the request's merchandiser can edit tranches.")
        if role == UserRole.MERCHANDISER and request.created_by != user_id:
            raise AuthorizationError("You can only edit tranches on your own requests.")
        assert_record_not_locked(request.is_locked, role)
        if request.current_status in _TERMINAL_STATUSES:
            raise ConflictError("Tranches cannot be edited on a cancelled or rejected request.")

        tranche = await self._get_tranche_locked(request_id, tranche_id)
        if tranche.status == TrancheStatus.PAID:
            raise ConflictError(
                f"{tranche.label} is already paid and can no longer be edited. "
                "Use the Adjust Invoices module to reallocate paid value."
            )

        changes = data.model_dump(exclude_unset=True, exclude_none=True)
        if not changes:
            raise ValidationError("No changes supplied.")

        if "amount" in changes:
            new_total = (
                await self._repo.sum_amounts_for_request(request_id)
                - Decimal(str(tranche.amount))
                + Decimal(str(changes["amount"]))
            )
            if new_total > Decimal(str(request.total_supplier_invoice_amount)):
                raise ValidationError(
                    "Total of tranche amounts cannot exceed the total supplier "
                    "proforma invoice amount."
                )

        for field, new_val in changes.items():
            old_val = getattr(tranche, field)
            await self._audit.record_update(
                "payment_tranches", tranche.id, user_id,
                field_name=field, old_value=str(old_val), new_value=str(new_val),
                ip_address=ip_address, user_agent=user_agent,
            )

        tranche = await self._repo.update(tranche, **changes)

        if "amount" in changes:
            await self._sync_request_totals(request, user_id, ip_address, user_agent)

        return tranche

    # ── Accounts payments ─────────────────────────────────────────────────────

    async def pay_tranche(
        self,
        request_id: UUID,
        tranche_id: UUID,
        user_id: UUID,
        role: UserRole,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> PaymentTranche:
        """Mark a specific UNPAID tranche as paid.

        When it is the request's last unpaid tranche, the request moves to
        payment_processed and locks (same transition the request-level flow
        used, still enforced by the DB trigger).
        """
        if role not in _ACCOUNTS_ROLES:
            raise AuthorizationError("Only Accounts Team can process tranche payments.")

        # Lock the request row first — concurrent payments of DIFFERENT
        # tranches on the same request must serialise, or both would count the
        # other as unpaid and the final-tranche completion would never fire.
        request = await self._get_request_locked_or_404(request_id)
        tranche = await self._get_tranche_locked(request_id, tranche_id)

        if tranche.status == TrancheStatus.PAID:
            raise ConflictError(f"{tranche.label} is already paid.")
        if request.current_status != RequestStatus.PENDING_PAYMENT:
            raise ConflictError(
                "Tranches can only be paid while the request is pending payment "
                f"(current status: {request.current_status.value})."
            )

        remaining_unpaid = await self._repo.count_unpaid_for_request(request_id)
        is_final = remaining_unpaid == 1
        if is_final:
            # The full-payment transition must be permitted before we pay the
            # final tranche — mirrors the request-level process_payment guard.
            assert_transition_allowed(
                request.current_status, RequestStatus.PAYMENT_PROCESSED, role
            )

        tranche = await self._repo.update(
            tranche,
            status=TrancheStatus.PAID,
            paid_at=datetime.now(timezone.utc),
            paid_by=user_id,
        )
        await self._audit.record_update(
            "payment_tranches", tranche.id, user_id,
            field_name="status",
            old_value=TrancheStatus.UNPAID.value, new_value=TrancheStatus.PAID.value,
            ip_address=ip_address, user_agent=user_agent,
        )

        if is_final:
            old_status = request.current_status
            await self._request_repo.update(
                request,
                current_status=RequestStatus.PAYMENT_PROCESSED,
                is_locked=True,
            )
            self._session.add(
                StatusHistory(
                    deposit_request_id=request_id,
                    old_status=old_status,
                    new_status=RequestStatus.PAYMENT_PROCESSED,
                    changed_by=user_id,
                )
            )
            await self._audit.record_status_change(
                "deposit_requests", request_id, user_id,
                old_status=old_status.value,
                new_status=RequestStatus.PAYMENT_PROCESSED.value,
                ip_address=ip_address, user_agent=user_agent,
            )

        return tranche

    async def attach_tt_copy(
        self,
        request_id: UUID,
        tranche_id: UUID,
        tt_copy_url: str,
        tt_copy_file_id: str,
        tt_copy_filename: str,
        user_id: UUID,
        role: UserRole,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[PaymentTranche, bool]:
        """Attach the bank's TT copy to a specific tranche.

        Uploading against an UNPAID tranche completes its payment in the same
        action (the bank has paid — the TT copy is the proof), running the
        full pay_tranche validation. Returns (tranche, auto_paid).

        Duplicate uploads against a paid tranche are rejected; only a Super
        Admin may replace an existing TT copy.
        """
        if role not in _ACCOUNTS_ROLES:
            raise AuthorizationError("Only Accounts Team can attach the TT copy.")

        await self._get_request_or_404(request_id)
        tranche = await self._get_tranche_locked(request_id, tranche_id)

        if tranche.tt_copy_url and role != UserRole.SUPER_ADMIN:
            raise ConflictError(
                f"A TT copy is already attached to {tranche.label}. "
                "Contact a Super Admin if it must be replaced."
            )

        auto_paid = False
        if tranche.status == TrancheStatus.UNPAID:
            tranche = await self.pay_tranche(
                request_id, tranche_id, user_id, role,
                ip_address=ip_address, user_agent=user_agent,
            )
            auto_paid = True

        tranche = await self._repo.update(
            tranche,
            tt_copy_url=tt_copy_url,
            tt_copy_file_id=tt_copy_file_id,
            tt_copy_filename=tt_copy_filename,
        )
        await self._audit.record_update(
            "payment_tranches", tranche.id, user_id,
            field_name="tt_copy",
            old_value=None, new_value=tt_copy_filename,
            ip_address=ip_address, user_agent=user_agent,
        )
        return tranche, auto_paid

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _sync_request_totals(
        self,
        request: DepositRequest,
        user_id: UUID,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        """Keep deposit_amount (= sum of tranches) and the derived deposit
        percentage in step after a tranche amount change — analytics, reports
        and dashboards all read these request-level fields."""
        new_total = await self._repo.sum_amounts_for_request(request.id)
        old_amount = Decimal(str(request.deposit_amount))
        if new_total == old_amount:
            return
        invoice_total = Decimal(str(request.total_supplier_invoice_amount))
        new_pct = round(new_total / invoice_total * 100, 2) if invoice_total else None
        await self._audit.record_update(
            "deposit_requests", request.id, user_id,
            field_name="deposit_amount",
            old_value=str(old_amount), new_value=str(new_total),
            ip_address=ip_address, user_agent=user_agent,
        )
        await self._request_repo.update(
            request, deposit_amount=new_total, deposit_percentage=new_pct
        )

    async def _get_request_or_404(self, request_id: UUID) -> DepositRequest:
        request = await self._request_repo.get_for_validation(request_id)
        if not request:
            raise NotFoundError(f"Request {request_id} not found.")
        return request

    async def _get_request_locked_or_404(self, request_id: UUID) -> DepositRequest:
        """Scalar fetch with SELECT … FOR UPDATE on the request row."""
        from sqlalchemy import select

        result = await self._session.execute(
            select(DepositRequest)
            .where(
                DepositRequest.id == request_id,
                DepositRequest.is_deleted.is_(False),
            )
            .with_for_update()
        )
        request = result.scalar_one_or_none()
        if not request:
            raise NotFoundError(f"Request {request_id} not found.")
        return request

    async def _get_tranche_locked(self, request_id: UUID, tranche_id: UUID) -> PaymentTranche:
        tranche = await self._repo.get_with_lock(tranche_id)
        if not tranche or tranche.deposit_request_id != request_id:
            raise NotFoundError(f"Tranche {tranche_id} not found on this request.")
        return tranche
