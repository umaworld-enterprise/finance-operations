"""Core business logic for DepositRequest workflow."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, BusinessRuleError, NotFoundError
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
from app.models.tranche import PaymentTranche
from app.models.workflow import AccountsAction, MerchandiserAction, StatusHistory
from app.repositories.deposit_request_repo import DepositRequestRepository
from app.repositories.supplier_repo import SupplierRepository
from app.schemas.deposit_request import ActivityItemResponse, DepositRequestCreate, DepositRequestUpdate
from app.services.audit_service import AuditService


# Requests in these statuses no longer block invoice-number reuse — a
# cancelled/rejected request's number may legitimately be re-raised.
_DUPLICATE_EXEMPT_STATUSES = {
    RequestStatus.CANCELLED_BY_MERCHANDISER,
    RequestStatus.CANCELLED_BY_ACCOUNTS,
    RequestStatus.REJECTED_BY_HOM,
    RequestStatus.REJECTED_BY_ACCOUNTS,
}

# Terminal statuses on which a merchandiser may no longer edit the request
# at all (UAT change note Aug 2026, item 18).
_MERCHANDISER_EDIT_BLOCKED_STATUSES = _DUPLICATE_EXEMPT_STATUSES

_INVOICE_FIELDS = {
    "sunshine_invoice_number": "Sunshine Invoice No.",
    "supplier_invoice_number": "Supplier Proforma Invoice No.",
}


class DepositRequestService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = DepositRequestRepository(session)
        self._supplier_repo = SupplierRepository(session)
        self._audit = AuditService(session)

    # ── Duplicate invoice validation (Aug 2026 batch, item 1.3) ───────────────

    async def find_invoice_conflict(
        self, field: str, value: str | None, exclude_request_id: UUID | None = None
    ) -> DepositRequest | None:
        """Live request already using this invoice number (case-insensitive,
        trimmed), or None. Enforced at the service layer, not a DB unique
        index — legacy data already contains at least one duplicate pair."""
        if field not in _INVOICE_FIELDS:
            raise ValueError(f"Not a duplicate-checked field: {field}")
        if not value or not value.strip():
            return None
        column = getattr(DepositRequest, field)
        stmt = (
            select(DepositRequest)
            .where(
                func.lower(func.trim(column)) == value.strip().lower(),
                DepositRequest.is_deleted.is_(False),
                DepositRequest.current_status.notin_(_DUPLICATE_EXEMPT_STATUSES),
            )
            .order_by(DepositRequest.created_at)
            .limit(1)
        )
        if exclude_request_id is not None:
            stmt = stmt.where(DepositRequest.id != exclude_request_id)
        return (await self._session.execute(stmt)).scalars().first()

    async def _assert_invoice_numbers_unique(
        self,
        sunshine_invoice_number: str | None,
        supplier_invoice_number: str | None,
        exclude_request_id: UUID | None = None,
    ) -> None:
        for field, value in (
            ("sunshine_invoice_number", sunshine_invoice_number),
            ("supplier_invoice_number", supplier_invoice_number),
        ):
            conflict = await self.find_invoice_conflict(field, value, exclude_request_id)
            if conflict:
                raise BusinessRuleError(
                    f"{_INVOICE_FIELDS[field]} '{value.strip()}' is already used by "
                    f"request {conflict.request_number}. Duplicate deposit requests "
                    "are not allowed."
                )

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

        # 1b. No duplicate deposit requests against the same invoice numbers
        await self._assert_invoice_numbers_unique(
            data.sunshine_invoice_number, data.supplier_invoice_number
        )

        # 2. Generate request number
        request_number = await self._repo.generate_request_number()

        # 3. Persist — exclude fields that are not DB columns on the request
        create_data = data.model_dump(exclude={"override_flagged_supplier", "tranches"})
        self._apply_derived_percentage(data, create_data)
        request = await self._repo.create(
            request_number=request_number,
            submission_source=source,
            created_by=created_by,
            current_status=initial_status,
            **create_data,
        )
        self._add_tranches(request, data)

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

        await self._assert_invoice_numbers_unique(
            data.sunshine_invoice_number, data.supplier_invoice_number
        )

        request_number = await self._repo.generate_request_number()

        create_data = data.model_dump(exclude={"override_flagged_supplier", "tranches"})
        self._apply_derived_percentage(data, create_data)
        request = await self._repo.create(
            request_number=request_number,
            submission_source=SubmissionSource.PUBLIC_FORM,
            created_by=created_by,
            submitter_email=submitter_email,
            current_status=initial_status,
            **create_data,
        )
        self._add_tranches(request, data)

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

    @staticmethod
    def _apply_derived_percentage(data: DepositRequestCreate, create_data: dict) -> None:
        """When tranches drive the deposit amount, the request-level deposit
        percentage is system-calculated (sum of tranches / invoice total)."""
        if data.tranches and data.total_supplier_invoice_amount:
            create_data["deposit_percentage"] = round(
                Decimal(str(create_data["deposit_amount"]))
                / Decimal(str(data.total_supplier_invoice_amount))
                * 100,
                2,
            )

    def _add_tranches(self, request: DepositRequest, data: DepositRequestCreate) -> None:
        """Create the request's Advance Payment Tranches.

        Submissions without explicit tranches (public form, legacy API
        callers) get a single compatibility tranche covering the full deposit
        amount, flagged is_legacy since it carries no tentative payment date.
        """
        if data.tranches:
            for i, t in enumerate(data.tranches, start=1):
                self._session.add(
                    PaymentTranche(
                        deposit_request_id=request.id,
                        tranche_number=i,
                        amount=t.amount,
                        tentative_payment_date=t.tentative_payment_date,
                    )
                )
        else:
            self._session.add(
                PaymentTranche(
                    deposit_request_id=request.id,
                    tranche_number=1,
                    amount=request.deposit_amount,
                    tentative_payment_date=None,
                    is_legacy=True,
                )
            )

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
        # Rejected/cancelled requests are closed to the merchandiser entirely
        # (UAT Aug 2026, item 18) — remarks included.
        if (
            role == UserRole.MERCHANDISER
            and request.current_status in _MERCHANDISER_EDIT_BLOCKED_STATUSES
        ):
            raise BusinessRuleError(
                "This request can no longer be edited "
                f"(current status: {request.current_status.value})."
            )
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
        # Once a request is rejected or cancelled, the merchandiser can no
        # longer change anything on it (UAT Aug 2026, item 18).
        if (
            role == UserRole.MERCHANDISER
            and request.current_status in _MERCHANDISER_EDIT_BLOCKED_STATUSES
        ):
            raise BusinessRuleError(
                "This request can no longer be edited "
                f"(current status: {request.current_status.value})."
            )

        changes = data.model_dump(exclude_unset=True)

        # Invoice numbers must stay unique across live requests when edited
        # (super-admin invoice editor, generic PATCH).
        if "sunshine_invoice_number" in changes or "supplier_invoice_number" in changes:
            await self._assert_invoice_numbers_unique(
                changes.get("sunshine_invoice_number"),
                changes.get("supplier_invoice_number"),
                exclude_request_id=request.id,
            )

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
                RequestStatus.REJECTED_BY_ACCOUNTS: AccountsActionType.REJECT,
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

    async def get_last_status_actors(self, request_ids: list[UUID]) -> dict[UUID, str]:
        """Full name of the user who made each request's most recent status
        change — lets the queue say WHO held/cancelled/rejected, not just
        which side (UAT Aug 2026, item 6). One batch query."""
        if not request_ids:
            return {}
        from sqlalchemy import and_
        from sqlalchemy import func as sa_func

        from app.models.masters import User as UserModel
        from app.models.workflow import StatusHistory

        latest = (
            select(
                StatusHistory.deposit_request_id,
                sa_func.max(StatusHistory.changed_at).label("last_at"),
            )
            .where(StatusHistory.deposit_request_id.in_(request_ids))
            .group_by(StatusHistory.deposit_request_id)
            .subquery()
        )
        stmt = (
            select(StatusHistory.deposit_request_id, UserModel.full_name)
            .join(
                latest,
                and_(
                    StatusHistory.deposit_request_id == latest.c.deposit_request_id,
                    StatusHistory.changed_at == latest.c.last_at,
                ),
            )
            .join(UserModel, StatusHistory.changed_by == UserModel.id)
        )
        rows = (await self._session.execute(stmt)).all()
        return {request_id: full_name for request_id, full_name in rows}

    async def get_queue_kpis(self) -> dict:
        """Financial-year-to-date counts for the payment-queue KPI cards
        (UAT Aug 2026, items 5/17/19). Every bucket counts requests CREATED
        between 1 April (India FY) and now, grouped by current status."""
        from datetime import datetime, timezone

        from sqlalchemy import func as sa_func

        now = datetime.now(timezone.utc)
        fy_start_year = now.year if now.month >= 4 else now.year - 1
        fy_start = datetime(fy_start_year, 4, 1, tzinfo=timezone.utc)

        stmt = (
            select(DepositRequest.current_status, sa_func.count())
            .where(
                DepositRequest.is_deleted.is_(False),
                DepositRequest.created_at >= fy_start,
            )
            .group_by(DepositRequest.current_status)
        )
        counts: dict[RequestStatus, int] = {
            status: n for status, n in (await self._session.execute(stmt)).all()
        }

        def bucket(*statuses: RequestStatus) -> int:
            return sum(counts.get(s, 0) for s in statuses)

        return {
            "fy_start": fy_start.date().isoformat(),
            "fy_label": f"FY {fy_start_year}–{(fy_start_year + 1) % 100:02d}",
            "pending_payment": bucket(RequestStatus.PENDING_PAYMENT),
            "awaiting_hom": bucket(RequestStatus.PENDING_HOM_APPROVAL),
            "on_hold": bucket(
                RequestStatus.HOLD_BY_MERCHANDISER, RequestStatus.HOLD_BY_ACCOUNTS
            ),
            "processed": bucket(RequestStatus.PAYMENT_PROCESSED),
            "rejected": bucket(
                RequestStatus.REJECTED_BY_ACCOUNTS, RequestStatus.REJECTED_BY_HOM
            ),
            "cancelled": bucket(
                RequestStatus.CANCELLED_BY_MERCHANDISER,
                RequestStatus.CANCELLED_BY_ACCOUNTS,
            ),
            "total": sum(counts.values()),
        }

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
