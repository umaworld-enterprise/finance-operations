"""ORM models for integration tables: DefaultedSupplier, GoogleFormSubmission, SyncLog."""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import CurrencyCode, SubmissionSource, SyncStatus, pg_enum


class DefaultedSupplier(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "defaulted_suppliers"

    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=False
    )
    outstanding_amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[CurrencyCode] = mapped_column(
        pg_enum(CurrencyCode, "currency_code"), nullable=False, default=CurrencyCode.USD
    )
    default_reason: Mapped[str] = mapped_column(Text, nullable=False)
    flagged_date: Mapped[date] = mapped_column(Date, nullable=False)
    flagged_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    resolved_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # FALSE = resolved/inactive; prevents duplicate active flags per supplier
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # True when the flag was created by the auto-flagging engine (not manually by a user)
    is_auto_flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    supplier: Mapped["Supplier"] = relationship(back_populates="default_flags")
    flagged_by_user: Mapped["User | None"] = relationship(
        back_populates="flags_raised", foreign_keys=[flagged_by]
    )
    resolved_by_user: Mapped["User | None"] = relationship(
        back_populates="flags_resolved", foreign_keys=[resolved_by]
    )

    __table_args__ = (
        # Only one active flag per supplier at a time
        UniqueConstraint("supplier_id", "is_active", name="uq_defaulted_supplier_active"),
    )


class GoogleFormSubmission(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "google_form_submissions"

    google_response_id: Mapped[str | None] = mapped_column(
        String(200), unique=True, nullable=True
    )
    submitted_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deposit_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deposit_requests.id"), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    deposit_request: Mapped["DepositRequest | None"] = relationship(
        back_populates="google_form_submission"
    )


class SyncLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "sync_logs"

    source_type: Mapped[SubmissionSource] = mapped_column(pg_enum(SubmissionSource, "submission_source"), nullable=False)
    source_reference: Mapped[str | None] = mapped_column(String(300), nullable=True)
    sync_status: Mapped[SyncStatus] = mapped_column(pg_enum(SyncStatus, "sync_status"), nullable=False)
    records_synced: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


from app.models.deposit_request import DepositRequest  # noqa: E402, F401
from app.models.masters import Supplier, User  # noqa: E402, F401
