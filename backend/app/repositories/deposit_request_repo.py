"""Repository for DepositRequest with role-scoped queries."""

from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.deposit_request import DepositRequest
from app.models.enums import RequestStatus, UserRole
from app.models.masters import Customer, Supplier, User
from app.repositories.base import BaseRepository

_StatusArg = RequestStatus | list[RequestStatus] | None


class DepositRequestRepository(BaseRepository[DepositRequest]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, DepositRequest)

    def _base_query(self) -> select:
        return (
            select(DepositRequest)
            .where(DepositRequest.is_deleted == False)  # noqa: E712
            .options(
                selectinload(DepositRequest.supplier),
                selectinload(DepositRequest.customer),
                selectinload(DepositRequest.vertical),
                selectinload(DepositRequest.creator),
                selectinload(DepositRequest.payment),
                selectinload(DepositRequest.tranches),
            )
        )

    def _apply_filters(
        self,
        stmt,
        role: UserRole,
        user_id: UUID,
        status: _StatusArg = None,
        supplier_id: UUID | None = None,
        customer_id: UUID | None = None,
        vertical_id: UUID | None = None,
        created_by: UUID | None = None,
        search: str | None = None,
    ):
        if role == UserRole.MERCHANDISER:
            # Include: requests the user created in-app OR submitted via the
            # public form using their registered email (legacy records where
            # created_by was NULL before the email-lookup fix).
            user_email_sq = select(User.email).where(User.id == user_id).scalar_subquery()
            stmt = stmt.where(
                or_(
                    DepositRequest.created_by == user_id,
                    and_(
                        DepositRequest.created_by.is_(None),
                        DepositRequest.submitter_email == user_email_sq,
                    ),
                )
            )
        if status is not None:
            if isinstance(status, list):
                stmt = stmt.where(DepositRequest.current_status.in_(status))
            else:
                stmt = stmt.where(DepositRequest.current_status == status)
        if supplier_id:
            stmt = stmt.where(DepositRequest.supplier_id == supplier_id)
        if customer_id:
            stmt = stmt.where(DepositRequest.customer_id == customer_id)
        if vertical_id:
            stmt = stmt.where(DepositRequest.vertical_id == vertical_id)
        if created_by:
            stmt = stmt.where(DepositRequest.created_by == created_by)
        if search and search.strip():
            # Relations are selectinload'ed (separate SELECTs), so name search
            # needs explicit joins here. Inner joins are safe — supplier_id and
            # customer_id are non-nullable FKs on every request.
            term = f"%{search.strip()}%"
            stmt = stmt.join(DepositRequest.supplier).join(DepositRequest.customer).where(
                or_(
                    DepositRequest.request_number.ilike(term),
                    DepositRequest.sunshine_invoice_number.ilike(term),
                    DepositRequest.supplier_invoice_number.ilike(term),
                    Supplier.name.ilike(term),
                    Customer.name.ilike(term),
                )
            )
        return stmt

    async def list_for_role(
        self,
        role: UserRole,
        user_id: UUID,
        status: _StatusArg = None,
        supplier_id: UUID | None = None,
        customer_id: UUID | None = None,
        vertical_id: UUID | None = None,
        created_by: UUID | None = None,
        search: str | None = None,
        sort: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DepositRequest]:
        stmt = self._apply_filters(
            self._base_query(), role, user_id,
            status=status, supplier_id=supplier_id,
            customer_id=customer_id, vertical_id=vertical_id, created_by=created_by,
            search=search,
        )
        # created_at tiebreak keeps amount sorts stable across pages.
        _SORTS = {
            "oldest": (DepositRequest.created_at.asc(),),
            "amount_desc": (DepositRequest.deposit_amount.desc(), DepositRequest.created_at.desc()),
            "amount_asc": (DepositRequest.deposit_amount.asc(), DepositRequest.created_at.desc()),
        }
        order = _SORTS.get(sort or "", (DepositRequest.created_at.desc(),))
        stmt = stmt.order_by(*order).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_for_role(
        self,
        role: UserRole,
        user_id: UUID,
        status: _StatusArg = None,
        supplier_id: UUID | None = None,
        customer_id: UUID | None = None,
        vertical_id: UUID | None = None,
        created_by: UUID | None = None,
        search: str | None = None,
    ) -> int:
        stmt = self._apply_filters(
            select(func.count(DepositRequest.id)).where(DepositRequest.is_deleted == False),  # noqa: E712
            role, user_id,
            status=status, supplier_id=supplier_id,
            customer_id=customer_id, vertical_id=vertical_id, created_by=created_by,
            search=search,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def get_for_validation(self, id: UUID) -> DepositRequest | None:
        """Fetch only scalar columns — no relationship joins.

        Used in mutation hot-paths (transition, update, delete) where only
        current_status / is_locked / created_by are needed for guards.
        Cuts 9 selectinload subqueries down to a single SELECT.
        """
        result = await self._session.execute(
            select(DepositRequest).where(
                DepositRequest.id == id,
                DepositRequest.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_with_core_relations(self, id: UUID) -> DepositRequest | None:
        """Fetch with only the relations DepositRequestResponse serializes
        (supplier, customer, vertical, creator, tranches).
        Use for mutation responses; use get_with_relations for detail views."""
        result = await self._session.execute(
            select(DepositRequest)
            .where(
                DepositRequest.id == id,
                DepositRequest.is_deleted.is_(False),
            )
            .options(
                selectinload(DepositRequest.supplier),
                selectinload(DepositRequest.customer),
                selectinload(DepositRequest.vertical),
                selectinload(DepositRequest.creator),
                selectinload(DepositRequest.tranches),
            )
        )
        return result.scalar_one_or_none()

    async def get_with_relations(self, id: UUID) -> DepositRequest | None:
        result = await self._session.execute(
            self._base_query()
            .where(DepositRequest.id == id)
            .options(
                selectinload(DepositRequest.status_history),
                selectinload(DepositRequest.merchandiser_actions),
                selectinload(DepositRequest.accounts_actions),
                selectinload(DepositRequest.analytics_snapshot),
            )
        )
        return result.scalar_one_or_none()

    async def get_pending_payment_queue(
        self, created_by: UUID | None = None, limit: int = 500
    ) -> list[DepositRequest]:
        """Pending requests sorted latest first (19 Aug 2026 — matches every
        other request table; was oldest-first 'process in order')."""
        stmt = (
            self._base_query()
            .where(DepositRequest.current_status == RequestStatus.PENDING_PAYMENT)
            .order_by(DepositRequest.created_at.desc())
            .limit(limit)
        )
        if created_by is not None:
            stmt = stmt.where(DepositRequest.created_by == created_by)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def generate_request_number(self) -> str:
        """Generate next sequential request number: Dep-YYYY-0001.

        The sequence restarts every calendar year. Historical ADT-YYYY-NNNNN
        numbers remain valid and untouched — they simply never match the new
        prefix, so both formats coexist.
        """
        from datetime import datetime, timezone
        from sqlalchemy import text

        year = datetime.now(timezone.utc).year
        prefix = f"Dep-{year}-"
        # Serialise concurrent submits for the rest of this transaction —
        # otherwise two requests read the same MAX and the second INSERT
        # violates the request_number UNIQUE constraint. (Advisory locks are
        # PostgreSQL-only; the unit-test SQLite database serialises writes on
        # its own.)
        if self._session.bind is not None and self._session.bind.dialect.name == "postgresql":
            await self._session.execute(text("SELECT pg_advisory_xact_lock(874512)"))
        # Highest existing number for the year — avoids collisions when gaps
        # exist (e.g. seeded data). Length-first ordering keeps the comparison
        # numeric once the padded sequence grows past 4 digits.
        result = await self._session.execute(
            select(DepositRequest.request_number)
            .where(DepositRequest.request_number.like(f"{prefix}%"))
            .order_by(
                func.length(DepositRequest.request_number).desc(),
                DepositRequest.request_number.desc(),
            )
            .limit(1)
        )
        max_num = result.scalar_one_or_none()
        last_seq = int(max_num.split("-")[-1]) if max_num else 0
        return f"{prefix}{last_seq + 1:04d}"
