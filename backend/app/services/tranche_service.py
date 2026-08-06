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

from sqlalchemy import select
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
from app.models.enums import AdjustmentStatus, RequestStatus, TrancheStatus, UserRole
from app.models.payment import PaymentDetails
from app.models.tranche import PaymentTranche
from app.models.workflow import StatusHistory
from app.repositories.deposit_request_repo import DepositRequestRepository
from app.repositories.tranche_repo import AdjustmentRepository, TrancheRepository
from app.schemas.tranche import TranchePaymentDetailsUpdate, TrancheCreate, TrancheUpdate
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

# Merchandisers may modify/add/delete tranches only while the request is
# still pending (Aug 2026 batch, item 2.3) — i.e. before Accounts act on it.
_MERCHANDISER_EDITABLE_STATUSES = {
    RequestStatus.PENDING_PAYMENT,
    RequestStatus.PENDING_HOM_APPROVAL,
}


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

        await self._assert_merchandiser_may_modify(request, role)

        tranche = await self._get_tranche_locked(request_id, tranche_id)
        if tranche.status == TrancheStatus.PAID:
            raise ConflictError(
                f"{tranche.label} is already paid and can no longer be edited. "
                "Use the Adjust Invoices module to reallocate paid value."
            )
        if tranche.status == TrancheStatus.REJECTED:
            raise ConflictError(
                f"{tranche.label} was rejected and is kept for record-keeping only — "
                "add a replacement tranche instead."
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

    async def add_tranche(
        self,
        request_id: UUID,
        data: TrancheCreate,
        user_id: UUID,
        role: UserRole,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> PaymentTranche:
        """Merchandiser adds a tranche to their own pending, untouched request."""
        request = await self._get_request_or_404(request_id)
        if role not in {UserRole.MERCHANDISER, UserRole.SUPER_ADMIN}:
            raise AuthorizationError("Only the request's merchandiser can add tranches.")
        if role == UserRole.MERCHANDISER and request.created_by != user_id:
            raise AuthorizationError("You can only add tranches on your own requests.")
        assert_record_not_locked(request.is_locked, role)
        if request.current_status in _TERMINAL_STATUSES:
            raise ConflictError("Tranches cannot be added on a cancelled or rejected request.")
        await self._assert_merchandiser_may_modify(request, role, adding=True)

        new_total = await self._repo.sum_amounts_for_request(request_id) + Decimal(str(data.amount))
        if new_total > Decimal(str(request.total_supplier_invoice_amount)):
            raise ValidationError(
                "Total of tranche amounts cannot exceed the total supplier "
                "proforma invoice amount."
            )

        existing = await self._repo.list_for_request(request_id)
        next_number = max((t.tranche_number for t in existing), default=0) + 1
        tranche = await self._repo.create(
            deposit_request_id=request_id,
            tranche_number=next_number,
            amount=data.amount,
            tentative_payment_date=data.tentative_payment_date,
        )
        await self._audit.record_create(
            "payment_tranches", tranche.id, user_id,
            new_value=(
                f"{tranche.label} added: {data.amount}, "
                f"tentative {data.tentative_payment_date}"
            ),
            ip_address=ip_address, user_agent=user_agent,
        )
        await self._sync_request_totals(request, user_id, ip_address, user_agent)
        return tranche

    async def delete_tranche(
        self,
        request_id: UUID,
        tranche_id: UUID,
        user_id: UUID,
        role: UserRole,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> str:
        """Merchandiser deletes an unpaid tranche from their own pending,
        untouched request. Returns the deleted tranche's label (for the
        Accounts notification — the row is gone afterwards)."""
        request = await self._get_request_or_404(request_id)
        if role not in {UserRole.MERCHANDISER, UserRole.SUPER_ADMIN}:
            raise AuthorizationError("Only the request's merchandiser can delete tranches.")
        if role == UserRole.MERCHANDISER and request.created_by != user_id:
            raise AuthorizationError("You can only delete tranches on your own requests.")
        assert_record_not_locked(request.is_locked, role)
        if request.current_status in _TERMINAL_STATUSES:
            raise ConflictError("Tranches cannot be deleted on a cancelled or rejected request.")
        await self._assert_merchandiser_may_modify(request, role)

        tranche = await self._get_tranche_locked(request_id, tranche_id)
        if tranche.status == TrancheStatus.PAID:
            raise ConflictError(f"{tranche.label} is paid and cannot be deleted.")
        if tranche.status == TrancheStatus.REJECTED:
            raise ConflictError(
                f"{tranche.label} was rejected and is kept for record-keeping — it cannot be deleted."
            )
        if len(await self._repo.list_for_request(request_id)) <= 1:
            raise ValidationError("A request must keep at least one tranche.")
        # FK safety: invoice adjustments reference tranches on either side.
        if await AdjustmentRepository(self._session).list_for_tranche_ids([tranche_id]):
            raise ConflictError(
                f"{tranche.label} is referenced by invoice adjustments and cannot be deleted."
            )

        label = tranche.label
        await self._audit.record_delete(
            "payment_tranches", tranche_id, user_id,
            old_value=f"{label}: {tranche.amount}, tentative {tranche.tentative_payment_date}",
            ip_address=ip_address, user_agent=user_agent,
        )
        await self._session.delete(tranche)
        await self._session.flush()
        await self._sync_request_totals(request, user_id, ip_address, user_agent)
        return label

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
        if tranche.status == TrancheStatus.REJECTED:
            raise ConflictError(f"{tranche.label} was rejected and cannot be paid.")
        # Readiness gate (Aug 2026, item 3.1): a tranche becomes PAID only via
        # this explicit action, and only once its TT copy AND payment details
        # (payment date + bank; reference number optional) are recorded.
        # accounts_remarks was briefly mandatory here (1 Aug) — reverted to
        # optional by the CIO batch of 4 Aug.
        missing = []
        if not tranche.tt_copy_url:
            missing.append("TT copy")
        if not tranche.payment_date:
            missing.append("payment date")
        if not tranche.bank:
            missing.append("bank")
        if missing:
            raise ConflictError(
                f"{tranche.label} cannot be marked paid until its "
                f"{' and '.join(missing)} {'are' if len(missing) > 1 else 'is'} recorded."
            )
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
            await self._sync_request_payment_details(request_id, user_id)

        return tranche

    async def _sync_request_payment_details(self, request_id: UUID, user_id: UUID) -> None:
        """Derive the request-level payment_details from the tranches when the
        final tranche is paid (Aug 2026 follow-up: the request-level Payment
        Details form was removed — details are captured per tranche now).

        Analytics (payment_to_ship_days, payment_to_request_days, CoF inputs)
        and report exports read payment_details.payment_date / payment_status,
        so these must keep being written: payment_date = the latest tranche
        payment date (the day the request became fully paid), payment_status =
        'processed'. Bank and reference number remain per-tranche. An existing
        partial row (ship_date / legacy TT copy) is updated, never replaced.
        """
        from app.models.enums import PaymentStatus
        from app.repositories.payment_repo import PaymentRepository

        tranches = await self._repo.list_for_request(request_id)
        dates = [t.payment_date for t in tranches if t.payment_date]
        payment_date = (
            max(dates) if dates else datetime.now(timezone.utc).date()
        )
        fields = {
            "payment_date": payment_date,
            "payment_status": PaymentStatus.PROCESSED.value,
            "updated_by": user_id,
        }
        repo = PaymentRepository(self._session)
        existing = await repo.get_by_request_id(request_id)
        if existing:
            await repo.update(existing, **fields)
        else:
            await repo.create(deposit_request_id=request_id, **fields)

    async def reject_tranche(
        self,
        request_id: UUID,
        tranche_id: UUID,
        reason: str,
        user_id: UUID,
        role: UserRole,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> PaymentTranche:
        """Accounts/HoM reject an UNPAID tranche with a mandatory reason
        (Aug 2026 — breaks the touched-lock deadlock).

        The tranche stays visible for record-keeping but its amount stops
        counting toward the invoice ceiling and the derived deposit_amount,
        and the merchandiser regains the ability to ADD replacement tranches
        even though Accounts have touched the request."""
        if role not in _ACCOUNTS_ROLES | {UserRole.HEAD_OF_MERCHANDISER}:
            raise AuthorizationError(
                "Only Accounts Team, Head of Merchandiser or Super Admin can reject a tranche."
            )
        if not reason or not reason.strip():
            raise ValidationError("A reason is mandatory when rejecting a tranche.")

        request = await self._get_request_or_404(request_id)
        if request.current_status in _TERMINAL_STATUSES:
            raise ConflictError("Tranches cannot be rejected on a cancelled or rejected request.")
        assert_record_not_locked(request.is_locked, role)

        tranche = await self._get_tranche_locked(request_id, tranche_id)
        if tranche.status == TrancheStatus.PAID:
            raise ConflictError(
                f"{tranche.label} is already paid and cannot be rejected. "
                "Use the Adjust Invoices module to reallocate paid value."
            )
        if tranche.status == TrancheStatus.REJECTED:
            raise ConflictError(f"{tranche.label} is already rejected.")

        tranche = await self._repo.update(
            tranche,
            status=TrancheStatus.REJECTED,
            rejection_reason=reason.strip(),
            rejected_at=datetime.now(timezone.utc),
            rejected_by=user_id,
        )
        await self._audit.record_update(
            "payment_tranches", tranche.id, user_id,
            field_name="status",
            old_value=TrancheStatus.UNPAID.value,
            new_value=f"{TrancheStatus.REJECTED.value} — {reason.strip()}",
            ip_address=ip_address, user_agent=user_agent,
        )
        # The rejected amount stops counting — deposit_amount re-derives from
        # the live tranches only.
        await self._sync_request_totals(request, user_id, ip_address, user_agent)
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
    ) -> PaymentTranche:
        """Attach the bank's TT copy to a specific tranche.

        Attach only — NO status change (Aug 2026, item 3.1, reversing the
        July auto-pay): the tranche becomes PAID exclusively through the
        explicit pay_tranche action, which requires this TT copy plus the
        tranche's payment details.

        Duplicate uploads against a tranche are rejected; only a Super Admin
        may replace an existing TT copy.
        """
        if role not in _ACCOUNTS_ROLES:
            raise AuthorizationError("Only Accounts Team can attach the TT copy.")

        await self._get_request_or_404(request_id)
        tranche = await self._get_tranche_locked(request_id, tranche_id)

        if tranche.status == TrancheStatus.REJECTED:
            raise ConflictError(f"{tranche.label} was rejected — TT copies cannot be attached.")
        if tranche.tt_copy_url and role != UserRole.SUPER_ADMIN:
            raise ConflictError(
                f"A TT copy is already attached to {tranche.label}. "
                "Contact a Super Admin if it must be replaced."
            )

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
        return tranche

    async def update_payment_details(
        self,
        request_id: UUID,
        tranche_id: UUID,
        data: "TranchePaymentDetailsUpdate",
        user_id: UUID,
        role: UserRole,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> PaymentTranche:
        """Accounts record per-tranche payment details (payment date, bank,
        optional reference number) ahead of marking the tranche paid.

        Unpaid tranches only — a paid tranche is immutable."""
        if role not in _ACCOUNTS_ROLES:
            raise AuthorizationError("Only Accounts Team can record tranche payment details.")

        request = await self._get_request_or_404(request_id)
        if request.current_status in _TERMINAL_STATUSES:
            raise ConflictError(
                "Payment details cannot be recorded on a cancelled or rejected request."
            )
        tranche = await self._get_tranche_locked(request_id, tranche_id)
        if tranche.status == TrancheStatus.PAID:
            raise ConflictError(
                f"{tranche.label} is already paid — its payment details are locked."
            )
        if tranche.status == TrancheStatus.REJECTED:
            raise ConflictError(
                f"{tranche.label} was rejected — payment details cannot be recorded."
            )

        changes = data.model_dump(exclude_unset=True)
        if not changes:
            raise ValidationError("No changes supplied.")

        # Bank is dropdown-only (Aug 2026 bank master, client decision:
        # no free-text fallback) — the value must be an active bank name
        # composed with the request's currency: "DBS (EUR)".
        if changes.get("bank"):
            await self._assert_bank_allowed(request, changes["bank"])

        for field, new_val in changes.items():
            old_val = getattr(tranche, field)
            await self._audit.record_update(
                "payment_tranches", tranche.id, user_id,
                field_name=field, old_value=str(old_val), new_value=str(new_val),
                ip_address=ip_address, user_agent=user_agent,
            )
        return await self._repo.update(tranche, **changes)

    async def _assert_bank_allowed(self, request: DepositRequest, bank_value: str) -> None:
        """The bank master stores names only; the stored tranche value is
        '{name} ({request currency})' — or the bare name when the request has
        no currency. An empty master blocks bank entry entirely."""
        from app.models.masters import BankMaster

        names = list(
            (
                await self._session.execute(
                    select(BankMaster.name).where(BankMaster.is_active == True)  # noqa: E712
                )
            ).scalars().all()
        )
        if not names:
            raise ValidationError(
                "No banks are configured — ask an administrator to add banks "
                "before recording payment details."
            )
        currency = request.currency.value if request.currency else None
        allowed = {f"{n} ({currency})" for n in names} if currency else {n for n in names}
        if bank_value not in allowed:
            raise ValidationError(
                f"'{bank_value}' is not an available bank for this request's "
                "currency. Pick one from the dropdown."
            )

    # ── Internals ─────────────────────────────────────────────────────────────

    async def accounts_touched_reason(self, request_id: UUID) -> str | None:
        """Human-readable reason if Accounts has written anything against this
        request, else None (Aug 2026 batch, item 2.3 — 'any accounts write').

        Counts: a paid tranche, an uploaded TT copy, a payment_details row
        (incl. partial rows from ship-date / TT paths), or a COMPLETED invoice
        adjustment touching the request's tranches. Pending merchandiser-raised
        adjustments do not count — Accounts hasn't acted on those.
        REJECTED tranches are dead records: any TT copy / payment details on
        them no longer count as a touch (otherwise the deadlock the rejection
        exists to break would immediately re-form).
        """
        tranches = await self._repo.list_for_request(request_id)
        live = [t for t in tranches if t.status != TrancheStatus.REJECTED]
        if any(t.status == TrancheStatus.PAID for t in live):
            return "a tranche has already been paid"
        if any(t.tt_copy_url for t in live):
            return "a TT copy has already been uploaded"
        if any(
            t.payment_date or t.bank or t.payment_reference_number or t.accounts_remarks
            for t in live
        ):
            return "payment details have been recorded against a tranche"
        payment_row = await self._session.scalar(
            select(PaymentDetails.id).where(
                PaymentDetails.deposit_request_id == request_id
            )
        )
        if payment_row is not None:
            return "the Accounts team has started payment processing"
        adjustments = await AdjustmentRepository(self._session).list_for_tranche_ids(
            [t.id for t in tranches]
        )
        if any(a.status == AdjustmentStatus.COMPLETED for a in adjustments):
            return "a completed invoice adjustment references this request"
        return None

    async def has_rejected_tranche(self, request_id: UUID) -> bool:
        return any(
            t.status == TrancheStatus.REJECTED
            for t in await self._repo.list_for_request(request_id)
        )

    async def _assert_merchandiser_may_modify(
        self, request: DepositRequest, role: UserRole, *, adding: bool = False
    ) -> None:
        """Merchandisers may change tranches only while the request is still
        pending AND untouched by Accounts. Super Admin keeps the broader
        pre-existing rules (lock / terminal-status / paid-tranche checks).

        Exception (Aug 2026 rejection workflow): while a REJECTED tranche
        exists, ADDING replacement tranches is allowed even after Accounts
        have touched the request — that is the point of the rejection.
        Edits/deletes of other tranches stay frozen."""
        if role != UserRole.MERCHANDISER:
            return
        if request.current_status not in _MERCHANDISER_EDITABLE_STATUSES:
            raise ConflictError(
                "Tranches can only be changed while the request is still pending "
                f"(current status: {request.current_status.value})."
            )
        reason = await self.accounts_touched_reason(request.id)
        if reason:
            if adding and await self.has_rejected_tranche(request.id):
                return
            raise ConflictError(f"Tranches can no longer be changed — {reason}.")

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
