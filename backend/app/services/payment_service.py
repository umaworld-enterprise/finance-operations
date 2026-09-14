"""Payment processing service — Accounts-owned workflow."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, ConflictError, NotFoundError
from app.domain.rules.lock_rules import assert_record_not_locked
from app.domain.rules.status_transitions import assert_transition_allowed
from app.models.enums import RequestStatus, UserRole
from app.models.payment import PaymentDetails
from app.models.workflow import StatusHistory
from app.repositories.deposit_request_repo import DepositRequestRepository
from app.repositories.payment_repo import PaymentRepository
from app.schemas.payment import PaymentCreate, PaymentUpdate
from app.services.audit_service import AuditService


class PaymentService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._request_repo = DepositRequestRepository(session)
        self._payment_repo = PaymentRepository(session)
        self._audit = AuditService(session)

    async def create_or_update(
        self,
        request_id: UUID,
        data: PaymentCreate | PaymentUpdate,
        user_id: UUID,
        role: UserRole,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> PaymentDetails:
        if role not in {UserRole.ACCOUNTS_TEAM, UserRole.SUPER_ADMIN}:
            raise AuthorizationError("Only Accounts Team can manage payment details.")
        # Scalar fetch only — this path reads is_locked, nothing relational.
        request = await self._request_repo.get_for_validation(request_id)
        if not request:
            raise NotFoundError(f"Request {request_id} not found.")
        assert_record_not_locked(request.is_locked, role)

        existing = await self._payment_repo.get_by_request_id(request_id)
        fields = data.model_dump(exclude_unset=True)
        fields["updated_by"] = user_id

        if existing:
            payment = await self._payment_repo.update(existing, **fields)
        else:
            payment = await self._payment_repo.create(
                deposit_request_id=request_id, **fields
            )

        await self._audit.record_update(
            "payment_details", payment.id, user_id,
            field_name="payment_data",
            old_value=None,
            new_value=str(fields),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        # Analytics snapshot is recomputed after the response (BackgroundTasks
        # in the endpoint) — it must not block the save.
        return payment

    async def process_payment(
        self,
        request_id: UUID,
        user_id: UUID,
        role: UserRole,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> PaymentDetails:
        """Mark payment as processed → lock the deposit request."""
        if role not in {UserRole.ACCOUNTS_TEAM, UserRole.SUPER_ADMIN}:
            raise AuthorizationError("Only Accounts Team can process payments.")

        # Scalar fetch only — this path reads current_status, nothing relational.
        request = await self._request_repo.get_for_validation(request_id)
        if not request:
            raise NotFoundError(f"Request {request_id} not found.")
        if request.current_status == RequestStatus.PAYMENT_PROCESSED:
            raise ConflictError("Payment is already processed for this request.")

        # Enforce the same transition rules as the DB trigger — otherwise a
        # request on hold / reopened / awaiting HoM would fail at the DB layer
        # with a raw "Invalid status transition" message.
        assert_transition_allowed(request.current_status, RequestStatus.PAYMENT_PROCESSED, role)

        payment = await self._payment_repo.get_by_request_id_with_lock(request_id)
        if not payment:
            raise ConflictError("Payment details must be entered before processing.")

        # Completeness gate — the mandatory Payment Details fields must be
        # recorded before the request can be processed. Partial rows created by
        # set_ship_date / attach_tt_copy are legitimate, but they cannot be
        # processed until Accounts completes them. (Payment Reference Number
        # became optional in the Aug 2026 batch, item 3.2.)
        missing = [
            label
            for field, label in (
                ("payment_date", "Payment Date"),
                ("bank", "Bank"),
                ("payment_status", "Payment Status"),
            )
            if getattr(payment, field) in (None, "")
        ]
        if missing:
            raise ConflictError(
                "Payment details are incomplete — fill in "
                f"{', '.join(missing)} before processing."
            )

        # A tranche may only become PAID through its TT copy upload, so
        # request-level processing must never bulk-pay tranches (it used to).
        # Refuse while any tranche is still unpaid.
        from app.repositories.tranche_repo import TrancheRepository

        unpaid_count = await TrancheRepository(self._session).count_unpaid_for_request(
            request_id
        )
        if unpaid_count:
            raise ConflictError(
                f"This request still has {unpaid_count} unpaid tranche(s). "
                "Upload each tranche's TT copy to mark it paid — request-level "
                "processing cannot mark tranches paid."
            )

        # Capture BEFORE update() mutates the instance in place — otherwise
        # the history and audit rows record old_status == new_status.
        old_status = request.current_status

        # Lock the request and update status
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
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return payment

    async def attach_tt_copy(
        self,
        request_id: UUID,
        tt_copy_url: str,
        tt_copy_file_id: str,
        tt_copy_filename: str,
        user_id: UUID,
        role: UserRole,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> PaymentDetails:
        """Attach the Drive link for the TT copy to the payment record.

        Deliberately does NOT check the record lock: the flow is process (which
        locks the request) → then upload the bank's TT copy. Only the three
        tt_copy_* fields are writable through this path, and it is audited.
        """
        if role not in {UserRole.ACCOUNTS_TEAM, UserRole.SUPER_ADMIN}:
            raise AuthorizationError("Only Accounts Team can attach the TT copy.")
        request = await self._request_repo.get_for_validation(request_id)
        if not request:
            raise NotFoundError(f"Request {request_id} not found.")

        fields = {
            "tt_copy_url": tt_copy_url,
            "tt_copy_file_id": tt_copy_file_id,
            "tt_copy_filename": tt_copy_filename,
            "updated_by": user_id,
        }
        existing = await self._payment_repo.get_by_request_id(request_id)
        if existing:
            payment = await self._payment_repo.update(existing, **fields)
        else:
            payment = await self._payment_repo.create(
                deposit_request_id=request_id, **fields
            )

        await self._audit.record_update(
            "payment_details", payment.id, user_id,
            field_name="tt_copy",
            old_value=None,
            new_value=tt_copy_filename,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return payment

    async def set_ship_date(
        self,
        request_id: UUID,
        ship_date: date,
        user_id: UUID,
        role: UserRole,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> PaymentDetails:
        """Record the final ship date — the date that stops Cost of Fund accrual.

        Deliberately does NOT check the record lock: payment is processed (which
        locks the request) long before the goods actually ship, so this is the
        designed post-lock action. Only ship_date is writable through this path,
        and every change is audited with its before/after values.
        """
        if role not in {UserRole.SUPER_ADMIN, UserRole.FINANCE_ADMIN, UserRole.ACCOUNTS_TEAM}:
            raise AuthorizationError(
                "Only Super Admin, Finance Admin or Accounts Team can record the ship date."
            )
        request = await self._request_repo.get_for_validation(request_id)
        if not request:
            raise NotFoundError(f"Request {request_id} not found.")

        existing = await self._payment_repo.get_by_request_id(request_id)
        old_ship_date = existing.ship_date if existing else None
        fields = {"ship_date": ship_date, "updated_by": user_id}
        if existing:
            payment = await self._payment_repo.update(existing, **fields)
        else:
            payment = await self._payment_repo.create(
                deposit_request_id=request_id, **fields
            )

        await self._audit.record_update(
            "payment_details", payment.id, user_id,
            field_name="ship_date",
            old_value=str(old_ship_date) if old_ship_date else None,
            new_value=str(ship_date),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return payment

    async def get_by_request_id(self, request_id: UUID) -> PaymentDetails | None:
        return await self._payment_repo.get_by_request_id(request_id)
