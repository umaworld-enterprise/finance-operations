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
    """Parse an ISO date/datetime string into a date; None or malformed input
    passes through as None (a bad filter must not 500 the report)."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


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
        date_field: str = "created",
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
                selectinload(DepositRequest.payment),
                selectinload(DepositRequest.analytics_snapshot),
            )
            .order_by(DepositRequest.created_at.desc())
        )
        if role == UserRole.MERCHANDISER:
            stmt = stmt.where(DepositRequest.created_by == user_id)

        if date_field == "modified":
            stmt = self._apply_date_range(stmt, DepositRequest.updated_at, date_from, date_to)
        elif date_field == "payment_date":
            stmt = stmt.join(PaymentDetails, PaymentDetails.deposit_request_id == DepositRequest.id, isouter=True)
            stmt = self._apply_date_range(stmt, PaymentDetails.payment_date, date_from, date_to)
        else:
            stmt = self._apply_date_range(stmt, DepositRequest.created_at, date_from, date_to)

        result = await self._session.execute(stmt)
        requests = list(result.scalars().all())

        headers = [
            "Key", "Request Date", "Select Supplier", "Select Customer", "Vertical/Category",
            "Currency", "Deposit Amount", "Deposit (%)", "Total Supplier Proforma Invoice Amount",
            "Estimated ETD", "Payment Terms", "Payment Status", "Staff",
            "Supplier Invoice Number", "Sunshine Invoice Number", "Rate",
            "Remarks", "Staff Email",
            "Payment Date", "Bank", "Payment Ref #", "Bank Payment Status",
            "Ship Date", "Actual ETD", "Accounts Remarks",
            "ETD (Grace) Overdue Days", "Cost of Fund",
        ]
        rows = [
            [
                r.request_number,
                r.created_at.date(),
                r.supplier.name if r.supplier else "—",
                r.customer.name if r.customer else "—",
                r.vertical.name if r.vertical else "—",
                r.currency.value if r.currency else "—",
                r.deposit_amount,
                r.deposit_percentage,
                r.total_supplier_invoice_amount,
                r.estimated_etd,
                r.payment_terms or "—",
                r.current_status.value,
                r.creator.full_name if r.creator else "—",
                r.supplier_invoice_number or "—",
                r.sunshine_invoice_number or "—",
                r.exchange_rate,
                r.remarks or "—",
                r.submitter_email or "—",
                r.payment.payment_date if r.payment else "—",
                r.payment.bank if r.payment else "—",
                r.payment.payment_reference_number if r.payment else "—",
                r.payment.payment_status if r.payment else "—",
                r.payment.ship_date if r.payment else "—",
                r.payment.actual_etd if r.payment else "—",
                r.payment.accounts_remarks or "—" if r.payment else "—",
                r.analytics_snapshot.etd_grace_overdue_days if r.analytics_snapshot else "—",
                r.analytics_snapshot.cost_of_fund_amount if r.analytics_snapshot else "—",
            ]
            for r in requests
        ]
        return self._render("Supplier Advance Payment Request Report", headers, rows, fmt,
                            col_widths=[6, 5, 9, 8, 7, 5, 6, 4, 6, 6, 6, 8, 8, 8, 8, 5, 10, 10,
                                        6, 8, 8, 8, 6, 6, 10, 5, 6])

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
        # Req#, PayDate, Bank, Ref#, PayStatus, ShipDate, Remarks
        return self._render("Payment Report", headers, rows, fmt,
                            col_widths=[7, 6, 10, 10, 8, 6, 13])

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
                s.deposit_request.request_number if s.deposit_request else "—",
                s.deposit_request.supplier.name if (s.deposit_request and s.deposit_request.supplier) else "—",
                s.deposit_request.customer.name if (s.deposit_request and s.deposit_request.customer) else "—",
                s.grace_etd,
                s.etd_grace_overdue_days,
                s.payment_to_ship_days,
                s.default_status,
            ]
            for s in snaps
        ]
        # Req#, Supplier, Customer, GraceETD, OverdueDays, Pay2Ship, Status
        return self._render("Delay Report", headers, rows, fmt,
                            col_widths=[7, 11, 10, 7, 7, 7, 9])

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
            "Currency", "CoF Amount", "Delay Days",
        ]
        rows = [
            [
                s.deposit_request.request_number if s.deposit_request else "—",
                s.deposit_request.supplier.name if (s.deposit_request and s.deposit_request.supplier) else "—",
                s.deposit_request.deposit_amount if s.deposit_request else 0,
                s.deposit_request.currency.value if s.deposit_request else "—",
                s.cost_of_fund_amount,
                s.etd_grace_overdue_days,
            ]
            for s in snaps
        ]
        # Req#, Supplier, DepAmt, Currency, CofAmt, DelayDays (past grace ETD)
        return self._render("Cost of Fund Report", headers, rows, fmt,
                            col_widths=[7, 13, 8, 5, 8, 7])

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
                r.supplier.name if r.supplier else "—",
                r.request_number,
                r.deposit_amount,
                r.currency.value,
                r.current_status.value,
                r.created_at.date(),
            ]
            for r in requests
        ]
        # Supplier, Req#, DepAmt, Currency, Status, Date
        return self._render("Supplier Report", headers, rows, fmt,
                            col_widths=[13, 7, 7, 5, 8, 6])

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
        self,
        title: str,
        headers: list[str],
        rows: list,
        fmt: ReportFormat,
        col_widths: list[float] | None = None,
    ) -> tuple[bytes, str]:
        if fmt == "excel":
            return build_excel(title, headers, rows), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        elif fmt == "csv":
            return build_csv(headers, rows), "text/csv"
        else:
            return build_pdf(title, headers, rows, col_widths=col_widths), "application/pdf"
