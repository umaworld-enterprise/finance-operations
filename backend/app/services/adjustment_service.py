"""Adjust Invoices — reallocate value from a paid tranche to another invoice.

A paid tranche is never edited, deleted, or overwritten. Each adjustment is
an additive, linked transaction: source paid tranche → destination tranche on
ANOTHER request (invoice) of the SAME supplier, with amount, actor, timestamp
and reason. Reallocations can never exceed the source tranche's remaining
paid balance (original amount minus prior adjustments), validated under a
row-level lock.

Approval: the client has not yet decided whether adjustments need approval.
No comparable generic approval pattern exists in this codebase (HoM approval
is a request-status flow specific to flagged suppliers), so adjustments are
created directly as COMPLETED. The status enum already carries
pending_approval / rejected so an approval step can be added without schema
changes.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import (
    AuthorizationError,
    NotFoundError,
    ValidationError,
)
from app.models.deposit_request import DepositRequest
from app.models.enums import AdjustmentStatus, TrancheStatus, UserRole
from app.models.masters import User
from app.models.tranche import InvoiceAdjustment, PaymentTranche
from app.repositories.tranche_repo import AdjustmentRepository, TrancheRepository
from app.schemas.tranche import AdjustmentCreate, AdjustmentResponse, TrancheResponse
from app.services.audit_service import AuditService

_ADJUSTMENT_ROLES = {UserRole.ACCOUNTS_TEAM, UserRole.SUPER_ADMIN}


class AdjustmentService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = AdjustmentRepository(session)
        self._tranche_repo = TrancheRepository(session)
        self._audit = AuditService(session)

    async def create(
        self,
        data: AdjustmentCreate,
        user_id: UUID,
        role: UserRole,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> InvoiceAdjustment:
        if role not in _ADJUSTMENT_ROLES:
            raise AuthorizationError("Only Accounts Team can adjust invoices.")
        if data.source_tranche_id == data.destination_tranche_id:
            raise ValidationError("Source and destination tranches must differ.")

        # Lock the source first — the balance check below must not race a
        # concurrent adjustment against the same paid tranche.
        source = await self._tranche_repo.get_with_lock(data.source_tranche_id)
        if not source:
            raise NotFoundError("Source tranche not found.")
        destination = await self._tranche_repo.get_with_request(data.destination_tranche_id)
        if not destination:
            raise NotFoundError("Destination tranche not found.")

        source_request = await self._session.get(DepositRequest, source.deposit_request_id)
        dest_request = destination.deposit_request
        if source_request is None or source_request.is_deleted or dest_request.is_deleted:
            raise NotFoundError("The related request no longer exists.")

        if source.status != TrancheStatus.PAID:
            raise ValidationError("Only an already-paid tranche can be the adjustment source.")
        if destination.status == TrancheStatus.PAID:
            raise ValidationError("The destination tranche is already paid.")
        if source.deposit_request_id == destination.deposit_request_id:
            raise ValidationError(
                "The destination must be a tranche on another invoice, not the same request."
            )
        if source_request.supplier_id != dest_request.supplier_id:
            raise ValidationError(
                "Adjustments are only allowed between invoices of the same supplier."
            )

        available = Decimal(str(source.amount)) - await self._repo.adjusted_out_total(source.id)
        if data.amount > available:
            raise ValidationError(
                f"Adjustment exceeds the available paid balance of {source.label} "
                f"({available})."
            )

        adjustment = await self._repo.create(
            source_tranche_id=source.id,
            destination_tranche_id=destination.id,
            amount=data.amount,
            reason=data.reason,
            status=AdjustmentStatus.COMPLETED,
            performed_by=user_id,
        )

        # Audit: the adjustment itself plus a trace on BOTH requests so the
        # reallocation is visible from either side's request-level history.
        await self._audit.record_create(
            "invoice_adjustments", adjustment.id, user_id,
            new_value=(
                f"{data.amount} from {source.label} of {source_request.request_number} "
                f"to {destination.label} of {dest_request.request_number}"
            ),
            ip_address=ip_address, user_agent=user_agent,
        )
        await self._audit.record_update(
            "deposit_requests", source_request.id, user_id,
            field_name="invoice_adjustment_out",
            old_value=None,
            new_value=(
                f"{data.amount} reallocated from {source.label} to "
                f"{dest_request.request_number} / {destination.label}"
            ),
            ip_address=ip_address, user_agent=user_agent,
        )
        await self._audit.record_update(
            "deposit_requests", dest_request.id, user_id,
            field_name="invoice_adjustment_in",
            old_value=None,
            new_value=(
                f"{data.amount} received on {destination.label} from "
                f"{source_request.request_number} / {source.label}"
            ),
            ip_address=ip_address, user_agent=user_agent,
        )
        return adjustment

    # ── Reads ─────────────────────────────────────────────────────────────────

    async def list_for_request(self, request_id: UUID) -> list[AdjustmentResponse]:
        """All adjustments where this request's tranches are source or
        destination — traceable from both the original request and the
        destination invoice."""
        tranche_ids = [
            t.id for t in await self._tranche_repo.list_for_request(request_id)
        ]
        adjustments = await self._repo.list_for_tranche_ids(tranche_ids)
        return [await self.to_response(a) for a in adjustments]

    async def list_recent(self, limit: int = 100) -> list[AdjustmentResponse]:
        result = await self._session.execute(
            select(InvoiceAdjustment)
            .order_by(InvoiceAdjustment.created_at.desc())
            .limit(limit)
        )
        return [await self.to_response(a) for a in result.scalars().all()]

    async def supplier_tranche_options(
        self, supplier_id: UUID
    ) -> tuple[list[TrancheResponse], list[TrancheResponse]]:
        """(paid sources with remaining balance, unpaid destinations) across
        the supplier's active requests."""
        stmt = (
            select(PaymentTranche)
            .join(DepositRequest, PaymentTranche.deposit_request_id == DepositRequest.id)
            .where(
                DepositRequest.supplier_id == supplier_id,
                DepositRequest.is_deleted.is_(False),
            )
            .options(selectinload(PaymentTranche.deposit_request))
            .order_by(DepositRequest.created_at.desc(), PaymentTranche.tranche_number)
        )
        tranches = list((await self._session.execute(stmt)).scalars().all())

        paid_sources: list[TrancheResponse] = []
        unpaid_destinations: list[TrancheResponse] = []
        for t in tranches:
            resp = TrancheResponse.model_validate(t)
            resp.with_percentage(Decimal(str(t.deposit_request.total_supplier_invoice_amount)))
            resp.request_number = t.deposit_request.request_number
            resp.request_currency = (
                t.deposit_request.currency.value if t.deposit_request.currency else None
            )
            resp.supplier_invoice_number = t.deposit_request.supplier_invoice_number
            resp.sunshine_invoice_number = t.deposit_request.sunshine_invoice_number
            if t.status == TrancheStatus.PAID:
                out_total = await self._repo.adjusted_out_total(t.id)
                resp.adjusted_out_total = out_total
                resp.available_paid_balance = Decimal(str(t.amount)) - out_total
                if resp.available_paid_balance > 0:
                    paid_sources.append(resp)
            else:
                resp.adjusted_in_total = await self._repo.adjusted_in_total(t.id)
                unpaid_destinations.append(resp)
        return paid_sources, unpaid_destinations

    async def to_response(self, adjustment: InvoiceAdjustment) -> AdjustmentResponse:
        resp = AdjustmentResponse.model_validate(adjustment)
        source = await self._tranche_repo.get_with_request(adjustment.source_tranche_id)
        destination = await self._tranche_repo.get_with_request(adjustment.destination_tranche_id)
        performer = await self._session.get(User, adjustment.performed_by)
        if performer:
            resp.performed_by_name = performer.full_name
        if source:
            resp.source_tranche_label = source.label
            resp.source_request_id = source.deposit_request_id
            resp.source_request_number = source.deposit_request.request_number
            from app.models.masters import Supplier
            supplier = await self._session.get(Supplier, source.deposit_request.supplier_id)
            if supplier:
                resp.supplier_name = supplier.name
        if destination:
            resp.destination_tranche_label = destination.label
            resp.destination_request_id = destination.deposit_request_id
            resp.destination_request_number = destination.deposit_request.request_number
        return resp
