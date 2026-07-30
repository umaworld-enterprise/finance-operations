"""Adjust Invoices — reallocate value from a paid tranche to another invoice.

A paid tranche is never edited, deleted, or overwritten. Each adjustment is
an additive, linked transaction: source paid tranche → destination tranche on
ANOTHER request (invoice) of the SAME supplier, with amount, actor, timestamp
and reason. Reallocations can never exceed the source tranche's remaining
paid balance (original amount minus prior adjustments), validated under a
row-level lock.

Approval (14 Jul 2026 change note, B3): merchandisers may RAISE adjustment
requests — created as PENDING_APPROVAL with a mandatory reason — which land
in the Accounts queue. Accounts Team / Super Admin decide them (approve or
reject, reason mandatory) and their own adjustments remain immediate
(COMPLETED). PENDING_APPROVAL rows do not consume paid-tranche balance;
approval re-validates everything under a row lock, since state may have
changed since the request was raised.
"""

from decimal import Decimal
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
from app.models.enums import AdjustmentStatus, TrancheStatus, UserRole
from app.models.masters import User
from app.models.payment import PaymentDetails
from app.models.tranche import InvoiceAdjustment, PaymentTranche
from app.repositories.tranche_repo import AdjustmentRepository, TrancheRepository
from app.schemas.tranche import AdjustmentCreate, AdjustmentResponse, TrancheResponse
from app.services.audit_service import AuditService

# Deciders: create immediately-completed adjustments and approve/reject the
# pending queue. Requesters additionally include merchandisers, whose
# adjustments are created PENDING_APPROVAL.
_DECIDER_ROLES = {UserRole.ACCOUNTS_TEAM, UserRole.SUPER_ADMIN}
_REQUESTER_ROLES = _DECIDER_ROLES | {UserRole.MERCHANDISER}


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
        if role not in _REQUESTER_ROLES:
            raise AuthorizationError(
                "Only Accounts Team, Super Admin or a merchandiser can raise invoice adjustments."
            )
        if role == UserRole.MERCHANDISER and not (data.reason and data.reason.strip()):
            raise ValidationError(
                "A reason is mandatory for merchandiser-raised adjustment requests."
            )
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

        source_request, dest_request = await self._validate_pair(source, destination)
        await self._assert_within_balance(source, Decimal(str(data.amount)))

        # Merchandiser-raised adjustments queue for Accounts approval; a
        # decider's own adjustments remain immediate.
        status = (
            AdjustmentStatus.PENDING_APPROVAL
            if role == UserRole.MERCHANDISER
            else AdjustmentStatus.COMPLETED
        )

        adjustment = await self._repo.create(
            source_tranche_id=source.id,
            destination_tranche_id=destination.id,
            amount=data.amount,
            reason=data.reason,
            status=status,
            performed_by=user_id,
        )

        # Audit: the adjustment itself plus a trace on BOTH requests so the
        # reallocation is visible from either side's request-level history.
        verb = "requested" if status == AdjustmentStatus.PENDING_APPROVAL else "reallocated"
        await self._audit.record_create(
            "invoice_adjustments", adjustment.id, user_id,
            new_value=(
                f"{verb} {data.amount} from {source.label} of {source_request.request_number} "
                f"to {destination.label} of {dest_request.request_number}"
            ),
            ip_address=ip_address, user_agent=user_agent,
        )
        await self._audit.record_update(
            "deposit_requests", source_request.id, user_id,
            field_name="invoice_adjustment_out",
            old_value=None,
            new_value=(
                f"{data.amount} {verb} from {source.label} to "
                f"{dest_request.request_number} / {destination.label}"
            ),
            ip_address=ip_address, user_agent=user_agent,
        )
        await self._audit.record_update(
            "deposit_requests", dest_request.id, user_id,
            field_name="invoice_adjustment_in",
            old_value=None,
            new_value=(
                f"{data.amount} {verb} on {destination.label} from "
                f"{source_request.request_number} / {source.label}"
            ),
            ip_address=ip_address, user_agent=user_agent,
        )
        return adjustment

    async def approve(
        self,
        adjustment_id: UUID,
        user_id: UUID,
        role: UserRole,
        reason: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> InvoiceAdjustment:
        """Approve a pending adjustment — re-runs EVERY create-time validation
        (paid source, unpaid destination, same supplier, not shipped, balance)
        because state may have changed since the request was raised. Balance
        only starts counting against the source tranche here."""
        adjustment, source, destination = await self._pending_or_conflict(
            adjustment_id, role, "approve"
        )
        source_request, dest_request = await self._validate_pair(source, destination)
        await self._assert_within_balance(source, Decimal(str(adjustment.amount)))

        adjustment = await self._repo.update(adjustment, status=AdjustmentStatus.COMPLETED)
        await self._record_decision_audit(
            adjustment, source, destination, source_request, dest_request,
            user_id, "approved", reason, ip_address, user_agent,
        )
        return adjustment

    async def reject(
        self,
        adjustment_id: UUID,
        user_id: UUID,
        role: UserRole,
        reason: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> InvoiceAdjustment:
        """Reject a pending adjustment with a mandatory reason. No balance is
        released — pending rows never consumed any."""
        adjustment, source, destination = await self._pending_or_conflict(
            adjustment_id, role, "reject"
        )
        source_request = await self._session.get(DepositRequest, source.deposit_request_id)
        dest_request = destination.deposit_request

        adjustment = await self._repo.update(adjustment, status=AdjustmentStatus.REJECTED)
        await self._record_decision_audit(
            adjustment, source, destination, source_request, dest_request,
            user_id, "rejected", reason, ip_address, user_agent,
        )
        return adjustment

    # ── Shared validation / audit internals ───────────────────────────────────

    async def _pending_or_conflict(
        self, adjustment_id: UUID, role: UserRole, action: str
    ) -> tuple[InvoiceAdjustment, PaymentTranche, PaymentTranche]:
        if role not in _DECIDER_ROLES:
            raise AuthorizationError(
                f"Only Accounts Team or Super Admin can {action} adjustment requests."
            )
        adjustment = await self._repo.get_by_id(adjustment_id)
        if not adjustment:
            raise NotFoundError("Adjustment not found.")
        if adjustment.status != AdjustmentStatus.PENDING_APPROVAL:
            raise ConflictError(
                f"Only pending adjustments can be {action}d "
                f"(current status: {adjustment.status.value})."
            )
        # Lock the source — decisions must serialise with concurrent
        # adjustments/approvals against the same paid tranche.
        source = await self._tranche_repo.get_with_lock(adjustment.source_tranche_id)
        destination = await self._tranche_repo.get_with_request(
            adjustment.destination_tranche_id
        )
        if not source or not destination:
            raise NotFoundError("The related tranches no longer exist.")
        return adjustment, source, destination

    async def _validate_pair(
        self, source: PaymentTranche, destination: PaymentTranche
    ) -> tuple[DepositRequest, DepositRequest]:
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

        # Shipped requests are out of scope for Adjust Invoice (change note B1):
        # once the shipment date is recorded, that Advance Payment Request is no
        # longer adjustable — on either side. Re-asserted here so the API cannot
        # be driven around the filtered option lists.
        for req in (source_request, dest_request):
            await self._assert_not_shipped(req)
        return source_request, dest_request

    async def _assert_within_balance(self, source: PaymentTranche, amount: Decimal) -> None:
        available = Decimal(str(source.amount)) - await self._repo.adjusted_out_total(source.id)
        if amount > available:
            raise ValidationError(
                f"Adjustment exceeds the available paid balance of {source.label} "
                f"({available})."
            )

    async def _record_decision_audit(
        self,
        adjustment: InvoiceAdjustment,
        source: PaymentTranche,
        destination: PaymentTranche,
        source_request: DepositRequest | None,
        dest_request: DepositRequest,
        user_id: UUID,
        decision: str,
        reason: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        """§8 of the note: decisions must be visible in the module AND from
        both requests' audit trails, like create already is."""
        summary = (
            f"{decision} {adjustment.amount} from {source.label} of "
            f"{source_request.request_number if source_request else '?'} to "
            f"{destination.label} of {dest_request.request_number}. Reason: {reason}"
        )
        await self._audit.record_update(
            "invoice_adjustments", adjustment.id, user_id,
            field_name="status",
            old_value=AdjustmentStatus.PENDING_APPROVAL.value,
            new_value=f"{adjustment.status.value} — {reason}",
            ip_address=ip_address, user_agent=user_agent,
        )
        if source_request is not None:
            await self._audit.record_update(
                "deposit_requests", source_request.id, user_id,
                field_name=f"invoice_adjustment_{decision}",
                old_value=None, new_value=summary,
                ip_address=ip_address, user_agent=user_agent,
            )
        await self._audit.record_update(
            "deposit_requests", dest_request.id, user_id,
            field_name=f"invoice_adjustment_{decision}",
            old_value=None, new_value=summary,
            ip_address=ip_address, user_agent=user_agent,
        )

    async def _assert_not_shipped(self, request: DepositRequest) -> None:
        """B1: `payment_details.ship_date IS NOT NULL` removes a request from
        the Adjust Invoice function entirely."""
        ship_date = await self._session.scalar(
            select(PaymentDetails.ship_date).where(
                PaymentDetails.deposit_request_id == request.id
            )
        )
        if ship_date is not None:
            raise BusinessRuleError(
                f"Request {request.request_number} has already shipped "
                f"(ship date {ship_date}) and is no longer available for "
                "invoice adjustments."
            )

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

    async def list_recent(
        self, limit: int = 100, performed_by: UUID | None = None
    ) -> list[AdjustmentResponse]:
        """Recent adjustments; merchandisers pass performed_by to see only
        their own."""
        stmt = select(InvoiceAdjustment).order_by(InvoiceAdjustment.created_at.desc())
        if performed_by is not None:
            stmt = stmt.where(InvoiceAdjustment.performed_by == performed_by)
        result = await self._session.execute(stmt.limit(limit))
        return [await self.to_response(a) for a in result.scalars().all()]

    async def list_pending(self) -> list[AdjustmentResponse]:
        """The Accounts queue — merchandiser-raised adjustments awaiting a
        decision, oldest first."""
        result = await self._session.execute(
            select(InvoiceAdjustment)
            .where(InvoiceAdjustment.status == AdjustmentStatus.PENDING_APPROVAL)
            .order_by(InvoiceAdjustment.created_at.asc())
        )
        return [await self.to_response(a) for a in result.scalars().all()]

    async def supplier_tranche_options(
        self, supplier_id: UUID
    ) -> tuple[list[TrancheResponse], list[TrancheResponse]]:
        """(paid sources with remaining balance, unpaid destinations) across
        the supplier's active requests.

        Requests whose shipment date has been recorded
        (payment_details.ship_date IS NOT NULL) are excluded from BOTH lists —
        once goods ship, that request is out of scope for Adjust Invoice (B1).
        The outer join keeps requests with no payment_details row at all.
        """
        stmt = (
            select(PaymentTranche)
            .join(DepositRequest, PaymentTranche.deposit_request_id == DepositRequest.id)
            .outerjoin(
                PaymentDetails, PaymentDetails.deposit_request_id == DepositRequest.id
            )
            .where(
                DepositRequest.supplier_id == supplier_id,
                DepositRequest.is_deleted.is_(False),
                PaymentDetails.ship_date.is_(None),
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
