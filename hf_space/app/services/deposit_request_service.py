"""Core business logic for DepositRequest workflow."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, NotFoundError
from app.domain.rules.lock_rules import assert_record_not_locked
from app.domain.rules.status_transitions import assert_transition_allowed
from app.domain.rules.supplier_validation import (
    DefaultedSupplierInfo,
    assert_supplier_not_defaulted,
)
from app.models.deposit_request import DepositRequest
from app.models.enums import (
    AccountsActionType,
    AuditAction,
    MerchandiserActionType,
    RequestStatus,
    SubmissionSource,
    UserRole,
)
from app.models.workflow import AccountsAction, MerchandiserAction, StatusHistory
from app.repositories.deposit_request_repo import DepositRequestRepository
from app.repositories.supplier_repo import SupplierRepository
from app.schemas.deposit_request import DepositRequestCreate, DepositRequestUpdate
from app.services.audit_service import AuditService


class DepositRequestService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = DepositRequestRepository(session)
        self._supplier_repo = SupplierRepository(session)
        self._audit = AuditService(session)

    async def create(
        self,
        data: DepositRequestCreate,
        created_by: UUID,
        source: SubmissionSource = SubmissionSource.IN_APP,
    ) -> DepositRequest:
        # 1. Validate supplier default status
        flag = await self._supplier_repo.get_active_default_flag(data.supplier_id)
        if flag:
            assert_supplier_not_defaulted(
                DefaultedSupplierInfo(
                    supplier_name=flag.supplier.name,
                    outstanding_amount=Decimal(str(flag.outstanding_amount)),
                    currency=flag.currency,
                    default_reason=flag.default_reason,
                )
            )

        # 2. Generate request number
        request_number = await self._repo.generate_request_number()

        # 3. Persist
        request = await self._repo.create(
            request_number=request_number,
            submission_source=source,
            created_by=created_by,
            **data.model_dump(),
        )

        # 4. Write initial status history
        self._session.add(
            StatusHistory(
                deposit_request_id=request.id,
                old_status=None,
                new_status=RequestStatus.PENDING_PAYMENT,
                changed_by=created_by,
            )
        )

        await self._audit.record_create("deposit_requests", request.id, created_by)
        return request

    async def update(
        self,
        request_id: UUID,
        data: DepositRequestUpdate,
        user_id: UUID,
        role: UserRole,
    ) -> DepositRequest:
        request = await self._get_or_404(request_id)
        assert_record_not_locked(request.is_locked, role)

        if role == UserRole.MERCHANDISER and request.created_by != user_id:
            raise AuthorizationError("You can only edit your own requests.")

        changes = data.model_dump(exclude_unset=True)
        for field, new_val in changes.items():
            old_val = getattr(request, field, None)
            await self._audit.record_update(
                "deposit_requests", request.id, user_id,
                field_name=field, old_value=str(old_val), new_value=str(new_val),
            )

        return await self._repo.update(request, **changes)

    async def transition_status(
        self,
        request_id: UUID,
        target: RequestStatus,
        user_id: UUID,
        role: UserRole,
        remarks: str | None = None,
    ) -> DepositRequest:
        request = await self._get_or_404(request_id)

        # Merchandiser can only act on own records
        if role == UserRole.MERCHANDISER and request.created_by != user_id:
            raise AuthorizationError("You can only change status of your own requests.")

        assert_transition_allowed(request.current_status, target, role)
        assert_record_not_locked(request.is_locked, role)

        old_status = request.current_status
        request = await self._repo.update(request, current_status=target)

        # Record action in dedicated action tables
        if role in {UserRole.MERCHANDISER, UserRole.SUPER_ADMIN}:
            action_map = {
                RequestStatus.HOLD_BY_MERCHANDISER: MerchandiserActionType.HOLD,
                RequestStatus.CANCELLED_BY_MERCHANDISER: MerchandiserActionType.CANCEL,
                RequestStatus.PENDING_PAYMENT: MerchandiserActionType.RESUME,
            }
            if target in action_map:
                self._session.add(
                    MerchandiserAction(
                        deposit_request_id=request.id,
                        action_type=action_map[target],
                        remarks=remarks,
                        performed_by=user_id,
                    )
                )
        else:
            action_map_acc = {
                RequestStatus.HOLD_BY_ACCOUNTS: AccountsActionType.HOLD,
                RequestStatus.CANCELLED_BY_ACCOUNTS: AccountsActionType.CANCEL,
                RequestStatus.REOPENED: AccountsActionType.REOPEN,
            }
            if target in action_map_acc:
                self._session.add(
                    AccountsAction(
                        deposit_request_id=request.id,
                        action_type=action_map_acc[target],
                        remarks=remarks,
                        performed_by=user_id,
                    )
                )

        self._session.add(
            StatusHistory(
                deposit_request_id=request.id,
                old_status=old_status,
                new_status=target,
                remarks=remarks,
                changed_by=user_id,
            )
        )

        await self._audit.record_status_change(
            "deposit_requests", request.id, user_id,
            old_status=old_status.value, new_status=target.value,
        )
        return request

    async def soft_delete(self, request_id: UUID, user_id: UUID, role: UserRole) -> None:
        request = await self._get_or_404(request_id)
        if role != UserRole.SUPER_ADMIN:
            raise AuthorizationError("Only Super Admin can delete requests.")
        await self._repo.soft_delete(request, user_id)
        await self._audit.record_delete("deposit_requests", request.id, user_id)

    async def get_detail(self, request_id: UUID) -> DepositRequest:
        request = await self._repo.get_with_relations(request_id)
        if not request:
            raise NotFoundError(f"Deposit request {request_id} not found.")
        return request

    async def list_for_role(self, role: UserRole, user_id: UUID, **filters) -> list[DepositRequest]:  # type: ignore[no-untyped-def]
        return await self._repo.list_for_role(role, user_id, **filters)

    async def get_pending_payment_queue(self) -> list[DepositRequest]:
        return await self._repo.get_pending_payment_queue()

    async def _get_or_404(self, request_id: UUID) -> DepositRequest:
        request = await self._repo.get_with_relations(request_id)
        if not request:
            raise NotFoundError(f"Deposit request {request_id} not found.")
        return request
