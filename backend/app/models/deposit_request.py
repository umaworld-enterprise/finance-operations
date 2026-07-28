"""ORM model for the core DepositRequest entity."""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import CurrencyCode, RequestStatus, SubmissionSource, pg_enum


class DepositRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "deposit_requests"

    request_number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)

    # Foreign keys to master data
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False
    )
    vertical_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("verticals.id"), nullable=True
    )

    # Invoice reference
    supplier_invoice_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sunshine_invoice_number: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Financial data
    currency: Mapped[CurrencyCode | None] = mapped_column(pg_enum(CurrencyCode, "currency_code"), nullable=True)
    exchange_rate: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    deposit_amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    deposit_percentage: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    total_supplier_invoice_amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)

    # Dates
    estimated_shipment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    estimated_etd: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Payment terms
    payment_terms: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Public form submitter (set when submission_source = PUBLIC_FORM)
    submitter_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Meta
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    submission_source: Mapped[SubmissionSource] = mapped_column(
        pg_enum(SubmissionSource, "submission_source"), nullable=False, default=SubmissionSource.IN_APP
    )
    current_status: Mapped[RequestStatus] = mapped_column(
        pg_enum(RequestStatus, "request_status"), nullable=False, default=RequestStatus.PENDING_PAYMENT
    )
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Soft delete
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Ownership (nullable for public_form submissions)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    # Relationships
    supplier: Mapped["Supplier"] = relationship(back_populates="deposit_requests")
    customer: Mapped["Customer"] = relationship(back_populates="deposit_requests")
    vertical: Mapped["Vertical"] = relationship(back_populates="deposit_requests")
    creator: Mapped["User"] = relationship(
        back_populates="created_requests", foreign_keys=[created_by]
    )
    deleter: Mapped["User | None"] = relationship(
        back_populates="deleted_requests", foreign_keys=[deleted_by]
    )
    payment: Mapped["PaymentDetails | None"] = relationship(
        back_populates="deposit_request", uselist=False
    )
    status_history: Mapped[list["StatusHistory"]] = relationship(
        back_populates="deposit_request", order_by="StatusHistory.changed_at"
    )
    merchandiser_actions: Mapped[list["MerchandiserAction"]] = relationship(
        back_populates="deposit_request", order_by="MerchandiserAction.performed_at"
    )
    accounts_actions: Mapped[list["AccountsAction"]] = relationship(
        back_populates="deposit_request", order_by="AccountsAction.performed_at"
    )
    analytics_snapshot: Mapped["AnalyticsSnapshot | None"] = relationship(
        back_populates="deposit_request", uselist=False
    )
    tranches: Mapped[list["PaymentTranche"]] = relationship(
        back_populates="deposit_request", order_by="PaymentTranche.tranche_number"
    )

    __table_args__ = (
        Index("idx_deposit_requests_status", "current_status"),
        Index("idx_deposit_requests_supplier", "supplier_id"),
        Index("idx_deposit_requests_created_by", "created_by"),
        Index("idx_deposit_requests_created_at", "created_at"),
        Index("idx_deposit_requests_is_deleted", "is_deleted"),
    )


# Deferred imports
from app.models.masters import Customer, Supplier, User, Vertical  # noqa: E402, F401
from app.models.payment import PaymentDetails  # noqa: E402, F401
from app.models.workflow import AccountsAction, MerchandiserAction, StatusHistory  # noqa: E402, F401
from app.models.analytics import AnalyticsSnapshot  # noqa: E402, F401
from app.models.tranche import PaymentTranche  # noqa: E402, F401
