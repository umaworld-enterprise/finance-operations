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
from app.schemas.deposit_request import ActivityItemResponse, DepositRequestCreate, DepositRequestUpdate
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
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> DepositRequest:
        # 1. Validate supplier default status
        flag = await self._supplier_repo.get_active_default_flag(data.supplier_id)
        if flag and not data.override_flagged_supplier:
            assert_supplier_not_defaulted(
                DefaultedSupplierInfo(
                    supplier_name=flag.supplier.name,
                    outstanding_amount=Decimal(str(flag.outstanding_amount)),
                    currency=flag.currency,
                    default_reason=flag.default_reason,
                )
            )

        # Requests on flagged suppliers (with override) go to HoM before Accounts
        initial_status = (
            RequestStatus.PENDING_HOM_APPROVAL
            if (flag and data.override_flagged_supplier)
            else RequestStatus.PENDING_PAYMENT
        )

        # 2. Generate request number
        request_number = await self._repo.generate_request_number()

        # 3. Persist — exclude the override flag field (not a DB column)
        create_data = data.model_dump(exclude={"override_flagged_supplier"})
        request = await self._repo.create(
            request_number=request_number,
            submission_source=source,
            created_by=created_by,
            current_status=initial_status,
            **create_data,
        )

        # 4. Write initial status history
        self._session.add(
            StatusHistory(
                deposit_request_id=request.id,
                old_status=None,
                new_status=initial_status,
                changed_by=created_by,
            )
        )

        await self._audit.record_create(
            "deposit_requests", request.id, created_by,
            ip_address=ip_address, user_agent=user_agent,
        )

        # Reload with the 4 relations the response serialises. The analytics
        # snapshot is seeded AFTER the response via BackgroundTasks (endpoint).
        loaded = await self._repo.get_with_core_relations(request.id)
        return loaded  # type: ignore[return-value]

    async def create_public(
        self,
        data: DepositRequestCreate,
        submitter_email: str,
        created_by: UUID | None = None,
    ) -> DepositRequest:
        """Create a deposit request from the public form.

        `created_by` is set when the submitter email matches a registered user so
        the request appears in that user's dashboard automatically.
        """
        flag = await self._supplier_repo.get_active_default_flag(data.supplier_id)
        if flag and not data.override_flagged_supplier:
            assert_supplier_not_defaulted(
                DefaultedSupplierInfo(
                    supplier_name=flag.supplier.name,
                    outstanding_amount=Decimal(str(flag.outstanding_amount)),
                    currency=flag.currency,
                    default_reason=flag.default_reason,
                )
            )

        initial_status = (
            RequestStatus.PENDING_HOM_APPROVAL
            if (flag and data.override_flagged_supplier)
            else RequestStatus.PENDING_PAYMENT
        )

        request_number = await self._repo.generate_request_number()

        request = await self._repo.create(
            request_number=request_number,
            submission_source=SubmissionSource.PUBLIC_FORM,
            created_by=created_by,
            submitter_email=submitter_email,
            current_status=initial_status,
            **data.model_dump(exclude={"override_flagged_supplier"}),
        )

        self._session.add(
            StatusHistory(
                deposit_request_id=request.id,
                old_status=None,
                new_status=initial_status,
                changed_by=created_by,
            )
        )
        loaded = await self._repo.get_with_core_relations(request.id)
        return loaded  # type: ignore[return-value]

    async def update_remarks(
        self,
        request_id: UUID,
        user_id: UUID,
        role: UserRole,
        remarks: str | None,
    ) -> DepositRequest:
        """Merchandiser adds/updates remarks on their own request. Super Admin can do any."""
        request = await self._get_scalar_or_404(request_id)
        if role == UserRole.MERCHANDISER and request.created_by != user_id:
            raise AuthorizationError("You can only add remarks to your own requests.")
        await self._repo.update(request, remarks=remarks)
        loaded = await self._repo.get_with_core_relations(request_id)
        return loaded  # type: ignore[return-value]

    async def update(
        self,
        request_id: UUID,
        data: DepositRequestUpdate,
        user_id: UUID,
        role: UserRole,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> DepositRequest:
        request = await self._get_scalar_or_404(request_id)
        assert_record_not_locked(request.is_locked, role)

        if role == UserRole.MERCHANDISER and request.created_by != user_id:
            raise AuthorizationError("You can only edit your own requests.")

        changes = data.model_dump(exclude_unset=True)
        for field, new_val in changes.items():
            old_val = getattr(request, field, None)
            await self._audit.record_update(
                "deposit_requests", request.id, user_id,
                field_name=field, old_value=str(old_val), new_value=str(new_val),
                ip_address=ip_address, user_agent=user_agent,
            )

        await self._repo.update(request, **changes)
        loaded = await self._repo.get_with_core_relations(request_id)
        return loaded  # type: ignore[return-value]

    async def transition_status(
        self,
        request_id: UUID,
        target: RequestStatus,
        user_id: UUID,
        role: UserRole,
        remarks: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> DepositRequest:
        request = await self._get_scalar_or_404(request_id)

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
            # Don't write a MerchandiserAction when Super Admin is approving a HOM request;
            # pending_hom_approval → pending_payment is a HOM action, not a merchandiser resume.
            is_hom_approval = (
                target == RequestStatus.PENDING_PAYMENT
                and old_status == RequestStatus.PENDING_HOM_APPROVAL
            )
            if target in action_map and not is_hom_approval:
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
            ip_address=ip_address, user_agent=user_agent,
        )
        # Reload with the 4 relations DepositRequestResponse serialises.
        loaded = await self._repo.get_with_core_relations(request.id)
        return loaded  # type: ignore[return-value]

    async def soft_delete(
        self,
        request_id: UUID,
        user_id: UUID,
        role: UserRole,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        request = await self._get_scalar_or_404(request_id)
        if role != UserRole.SUPER_ADMIN:
            raise AuthorizationError("Only Super Admin can delete requests.")
        await self._repo.soft_delete(request, user_id)
        await self._audit.record_delete(
            "deposit_requests", request.id, user_id,
            ip_address=ip_address, user_agent=user_agent,
        )

    async def get_detail(self, request_id: UUID, user_id: UUID | None = None, role: UserRole | None = None) -> DepositRequest:
        request = await self._repo.get_with_relations(request_id)
        if not request:
            raise NotFoundError(f"Deposit request {request_id} not found.")
        return request

    async def list_for_role(self, role: UserRole, user_id: UUID, **filters) -> list[DepositRequest]:  # type: ignore[no-untyped-def]
        return await self._repo.list_for_role(role, user_id, **filters)

    async def get_pending_payment_queue(self, created_by: UUID | None = None) -> list[DepositRequest]:
        return await self._repo.get_pending_payment_queue(created_by=created_by)

    async def get_my_activity(self, user_id: UUID, limit: int = 50) -> list[ActivityItemResponse]:
        from sqlalchemy import desc, select
        from app.models.masters import Supplier
        from app.models.workflow import StatusHistory

        result = await self._session.execute(
            select(
                StatusHistory.id,
                StatusHistory.deposit_request_id,
                StatusHistory.old_status,
                StatusHistory.new_status,
                StatusHistory.remarks,
                StatusHistory.changed_at,
                DepositRequest.request_number,
                Supplier.name.label("supplier_name"),
            )
            .join(DepositRequest, StatusHistory.deposit_request_id == DepositRequest.id)
            .join(Supplier, DepositRequest.supplier_id == Supplier.id)
            .where(
                DepositRequest.created_by == user_id,
                DepositRequest.is_deleted.is_(False),
                StatusHistory.old_status.is_not(None),
            )
            .order_by(desc(StatusHistory.changed_at))
            .limit(limit)
        )
        return [
            ActivityItemResponse(
                id=row.id,
                request_id=row.deposit_request_id,
                request_number=row.request_number,
                supplier_name=row.supplier_name,
                old_status=row.old_status,
                new_status=row.new_status,
                remarks=row.remarks,
                changed_at=row.changed_at,
            )
            for row in result.all()
        ]

    async def _get_scalar_or_404(self, request_id: UUID) -> DepositRequest:
        """Fetch only scalar columns for guard/validation hot-paths.

        Does NOT load any relationships. Use when only current_status,
        is_locked, or created_by are needed before a mutation. Cuts 9
        selectinload subqueries (≈10 DB round trips) down to a single SELECT.
        """
        request = await self._repo.get_for_validation(request_id)
        if not request:
            raise NotFoundError(f"Deposit request {request_id} not found.")
        return request

    async def _get_or_404(self, request_id: UUID) -> DepositRequest:
        request = await self._repo.get_with_relations(request_id)
        if not request:
            raise NotFoundError(f"Deposit request {request_id} not found.")
        return request
