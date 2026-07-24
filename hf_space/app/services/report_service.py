"""Report generation service — builds Excel/CSV/PDF for all 5 report types."""

from datetime import date, datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.analytics import AnalyticsSnapshot
from app.models.deposit_request import DepositRequest
from app.models.enums import UserRole
from app.models.payment import PaymentDetails
from app.reports.csv_builder import build_csv
from app.reports.excel_builder import build_excel
from app.reports.pdf_builder import build_pdf

ReportFormat = Literal["excel", "csv", "pdf"]


def _parse_date(value: str | None) -> date | None:
    """Parse an ISO date/datetime string into a date; None passes through."""
    if not value:
        return None
    return datetime.fromisoformat(value).date()


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def request_report(
        self,
        role: UserRole,
        user_id: UUID,
        fmt: ReportFormat,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> tuple[bytes, str]:
        """Request report — all requests scoped by role."""
        stmt = (
            select(DepositRequest)
            .where(DepositRequest.is_deleted == False)  # noqa: E712
            .options(
                selectinload(DepositRequest.supplier),
                selectinload(DepositRequest.customer),
                selectinload(DepositRequest.vertical),
                selectinload(DepositRequest.creator),
            )
            .order_by(DepositRequest.created_at.desc())
        )
        if role == UserRole.MERCHANDISER:
            stmt = stmt.where(DepositRequest.created_by == user_id)
        stmt = self._apply_date_range(stmt, DepositRequest.created_at, date_from, date_to)

        result = await self._session.execute(stmt)
        requests = list(result.scalars().all())

        headers = [
            "Request #", "Date", "Supplier", "Customer", "Vertical",
            "Currency", "Deposit Amount", "Deposit %", "Total Invoice",
            "Est. Shipment Date", "Status", "Submitted By",
        ]
        rows = [
            [
                r.request_number,
                r.created_at.date(),
                r.supplier.name,
                r.customer.name,
                r.vertical.name,
                r.currency.value,
                r.deposit_amount,
                r.deposit_percentage,
                r.total_supplier_invoice_amount,
                r.estimated_shipment_date,
                r.current_status.value,
                r.creator.full_name,
            ]
            for r in requests
        ]
        return self._render("Deposit Request Report", headers, rows, fmt)

    async def payment_report(
        self, fmt: ReportFormat, date_from: str | None = None, date_to: str | None = None
    ) -> tuple[bytes, str]:
        """Payments report."""
        stmt = (
            select(PaymentDetails)
            .join(DepositRequest, PaymentDetails.deposit_request_id == DepositRequest.id)
            .where(DepositRequest.is_deleted == False)  # noqa: E712
            .options(selectinload(PaymentDetails.deposit_request))
            .order_by(PaymentDetails.payment_date.desc())
        )
        stmt = self._apply_date_range(stmt, PaymentDetails.payment_date, date_from, date_to)
        result = await self._session.execute(stmt)
        payments = list(result.scalars().all())

        headers = [
            "Request #", "Payment Date", "Bank", "Reference #",
            "Payment Status", "Ship Date", "Remarks",
        ]
        rows = [
            [
                p.deposit_request.request_number,
                p.payment_date,
                p.bank,
                p.payment_reference_number,
                p.payment_status,
                p.ship_date,
                p.accounts_remarks,
            ]
            for p in payments
        ]
        return self._render("Payment Report", headers, rows, fmt)

    async def delay_report(
        self, fmt: ReportFormat, date_from: str | None = None, date_to: str | None = None
    ) -> tuple[bytes, str]:
        """Delayed shipments report."""
        stmt = (
            select(AnalyticsSnapshot)
            .join(DepositRequest, AnalyticsSnapshot.deposit_request_id == DepositRequest.id)
            .where(
                DepositRequest.is_deleted == False,  # noqa: E712
                AnalyticsSnapshot.etd_grace_overdue_days > 0,
            )
            .options(
                selectinload(AnalyticsSnapshot.deposit_request).selectinload(DepositRequest.supplier),
                selectinload(AnalyticsSnapshot.deposit_request).selectinload(DepositRequest.customer),
            )
            .order_by(AnalyticsSnapshot.etd_grace_overdue_days.desc())
        )
        stmt = self._apply_date_range(stmt, DepositRequest.created_at, date_from, date_to)
        result = await self._session.execute(stmt)
        snaps = list(result.scalars().all())

        headers = [
            "Request #", "Supplier", "Customer",
            "Grace ETD", "ETD Grace Overdue Days", "Pay-to-Ship Days", "Status",
        ]
        rows = [
            [
                s.deposit_request.request_number,
                s.deposit_request.supplier.name,
                s.deposit_request.customer.name,
                s.grace_etd,
                s.etd_grace_overdue_days,
                s.payment_to_ship_days,
                s.default_status,
            ]
            for s in snaps
        ]
        return self._render("Delay Report", headers, rows, fmt)

    async def cost_of_fund_report(
        self, fmt: ReportFormat, date_from: str | None = None, date_to: str | None = None
    ) -> tuple[bytes, str]:
        """Cost of fund report."""
        stmt = (
            select(AnalyticsSnapshot)
            .join(DepositRequest, AnalyticsSnapshot.deposit_request_id == DepositRequest.id)
            .where(
                DepositRequest.is_deleted == False,  # noqa: E712
                AnalyticsSnapshot.cost_of_fund_applicable == True,  # noqa: E712
            )
            .options(
                selectinload(AnalyticsSnapshot.deposit_request).selectinload(DepositRequest.supplier),
            )
            .order_by(AnalyticsSnapshot.cost_of_fund_amount.desc())
        )
        stmt = self._apply_date_range(stmt, DepositRequest.created_at, date_from, date_to)
        result = await self._session.execute(stmt)
        snaps = list(result.scalars().all())

        headers = [
            "Request #", "Supplier", "Deposit Amount",
            "Currency", "CoF Amount", "Pay-to-Ship Days",
        ]
        rows = [
            [
                s.deposit_request.request_number,
                s.deposit_request.supplier.name,
                s.deposit_request.deposit_amount,
                s.deposit_request.currency.value,
                s.cost_of_fund_amount,
                s.payment_to_ship_days,
            ]
            for s in snaps
        ]
        return self._render("Cost of Fund Report", headers, rows, fmt)

    async def supplier_report(
        self, fmt: ReportFormat, date_from: str | None = None, date_to: str | None = None
    ) -> tuple[bytes, str]:
        """Per-supplier summary."""
        stmt = (
            select(DepositRequest)
            .where(DepositRequest.is_deleted == False)  # noqa: E712
            .options(selectinload(DepositRequest.supplier))
            .order_by(DepositRequest.supplier_id, DepositRequest.created_at.desc())
        )
        stmt = self._apply_date_range(stmt, DepositRequest.created_at, date_from, date_to)
        result = await self._session.execute(stmt)
        requests = list(result.scalars().all())

        headers = ["Supplier", "Request #", "Deposit Amount", "Currency", "Status", "Date"]
        rows = [
            [
                r.supplier.name,
                r.request_number,
                r.deposit_amount,
                r.currency.value,
                r.current_status.value,
                r.created_at.date(),
            ]
            for r in requests
        ]
        return self._render("Supplier Report", headers, rows, fmt)

    @staticmethod
    def _apply_date_range(stmt, column, date_from: str | None, date_to: str | None):  # type: ignore[no-untyped-def]
        """Filter `stmt` so `column` falls within [date_from, date_to] (inclusive).

        Accepts ISO date/datetime strings; None means no bound. The upper bound is
        applied as an exclusive '< date_to + 1 day' so timestamp columns include the
        whole `date_to` day.
        """
        df = _parse_date(date_from)
        dt = _parse_date(date_to)
        if df is not None:
            stmt = stmt.where(column >= df)
        if dt is not None:
            stmt = stmt.where(column < dt + timedelta(days=1))
        return stmt

    def _render(
        self, title: str, headers: list[str], rows: list, fmt: ReportFormat
    ) -> tuple[bytes, str]:
        if fmt == "excel":
            return build_excel(title, headers, rows), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        elif fmt == "csv":
            return build_csv(headers, rows), "text/csv"
        else:
            return build_pdf(title, headers, rows), "application/pdf"
