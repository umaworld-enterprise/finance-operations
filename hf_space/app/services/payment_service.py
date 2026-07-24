"""Payment processing service — Accounts-owned workflow."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, ConflictError, NotFoundError
from app.domain.rules.lock_rules import assert_record_not_locked
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
    ) -> PaymentDetails:
        request = await self._request_repo.get_with_relations(request_id)
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
        )
        return payment

    async def process_payment(
        self, request_id: UUID, user_id: UUID, role: UserRole
    ) -> PaymentDetails:
        """Mark payment as processed → lock the deposit request."""
        if role not in {UserRole.ACCOUNTS_TEAM, UserRole.SUPER_ADMIN}:
            raise AuthorizationError("Only Accounts Team can process payments.")

        request = await self._request_repo.get_with_relations(request_id)
        if not request:
            raise NotFoundError(f"Request {request_id} not found.")
        if request.current_status == RequestStatus.PAYMENT_PROCESSED:
            raise ConflictError("Payment is already processed for this request.")

        payment = await self._payment_repo.get_by_request_id(request_id)
        if not payment:
            raise ConflictError("Payment details must be entered before processing.")

        # Lock the request and update status
        await self._request_repo.update(
            request,
            current_status=RequestStatus.PAYMENT_PROCESSED,
            is_locked=True,
        )
        self._session.add(
            StatusHistory(
                deposit_request_id=request_id,
                old_status=request.current_status,
                new_status=RequestStatus.PAYMENT_PROCESSED,
                changed_by=user_id,
            )
        )

        await self._audit.record_status_change(
            "deposit_requests", request_id, user_id,
            old_status=request.current_status.value,
            new_status=RequestStatus.PAYMENT_PROCESSED.value,
        )
        return payment

    async def get_by_request_id(self, request_id: UUID) -> PaymentDetails | None:
        return await self._payment_repo.get_by_request_id(request_id)
