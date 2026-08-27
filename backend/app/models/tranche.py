"""ORM models for Advance Payment Tranches and Invoice Adjustments.

A deposit request carries one or more payment tranches (Tranche 1, 2, …).
Accounts pays tranche-by-tranche; a paid tranche is immutable. Value from a
paid tranche can be reallocated to a tranche on another invoice of the same
supplier through an InvoiceAdjustment — an additive, linked record that never
mutates the source tranche.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import AdjustmentStatus, TrancheStatus, pg_enum

def tranche_label(number: int) -> str:
    """1 → 'Deposit - Tranche 1', 2 → 'Deposit - Tranche 2', …

    Single source for the display label: API responses, notifications, audit
    wording and the adjustment pickers all derive from this. Arithmetic
    numbers per the UAT change note (Aug 2026, item 11) — previously Roman."""
    return f"Deposit - Tranche {number}"


class PaymentTranche(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payment_tranches"

    deposit_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deposit_requests.id"), nullable=False
    )
    tranche_number: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    # Required for new in-app tranches (enforced at the schema layer); nullable
    # here because backfilled legacy tranches have no recorded tentative date.
    tentative_payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[TrancheStatus] = mapped_column(
        pg_enum(TrancheStatus, "tranche_status"), nullable=False, default=TrancheStatus.UNPAID
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # Per-tranche TT copy (bank transfer confirmation) — Google Drive link.
    tt_copy_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    tt_copy_file_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tt_copy_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Per-tranche payment details (Aug 2026, migration 0022). Payment date and
    # bank are required before the tranche can be marked paid; the reference
    # number is optional. Nullable: legacy tranches predate this data.
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    bank: Mapped[str | None] = mapped_column(String(200), nullable=True)
    payment_reference_number: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Required (like payment_date/bank) before the tranche can be marked paid
    # — migration 0023. Nullable: legacy tranches predate the field.
    accounts_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Rejection (Aug 2026, migration 0024): a rejected tranche stays visible
    # for record-keeping; its amount stops counting toward the request total.
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # True for tranches synthesised from pre-tranche records (migration 0018
    # backfill or API compat mode) — these may lack a tentative date.
    is_legacy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Release gate (19 Aug 2026, migration 0032): tranche 2 onwards is a
    # FUTURE payment — it stays "Yet to be Released" (released_at NULL) and
    # Accounts cannot pay it until the merchandiser releases it. Tranche 1
    # is auto-released at creation; existing rows were backfilled released.
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    deposit_request: Mapped["DepositRequest"] = relationship(back_populates="tranches")
    paid_by_user: Mapped["User | None"] = relationship(foreign_keys=[paid_by])
    adjustments_out: Mapped[list["InvoiceAdjustment"]] = relationship(
        back_populates="source_tranche",
        foreign_keys="InvoiceAdjustment.source_tranche_id",
        order_by="InvoiceAdjustment.created_at",
    )
    adjustments_in: Mapped[list["InvoiceAdjustment"]] = relationship(
        back_populates="destination_tranche",
        foreign_keys="InvoiceAdjustment.destination_tranche_id",
        order_by="InvoiceAdjustment.created_at",
    )

    @property
    def label(self) -> str:
        return tranche_label(self.tranche_number)

    __table_args__ = (
        UniqueConstraint("deposit_request_id", "tranche_number", name="uq_tranche_request_number"),
        CheckConstraint("amount > 0", name="ck_tranche_amount_positive"),
        Index("idx_payment_tranches_request", "deposit_request_id"),
        Index("idx_payment_tranches_status", "status"),
    )


class InvoiceAdjustment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "invoice_adjustments"

    source_tranche_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment_tranches.id"), nullable=False
    )
    destination_tranche_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment_tranches.id"), nullable=False
    )
    amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[AdjustmentStatus] = mapped_column(
        pg_enum(AdjustmentStatus, "adjustment_status"),
        nullable=False,
        default=AdjustmentStatus.COMPLETED,
    )
    performed_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    source_tranche: Mapped["PaymentTranche"] = relationship(
        back_populates="adjustments_out", foreign_keys=[source_tranche_id]
    )
    destination_tranche: Mapped["PaymentTranche"] = relationship(
        back_populates="adjustments_in", foreign_keys=[destination_tranche_id]
    )
    performer: Mapped["User"] = relationship(foreign_keys=[performed_by])

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_adjustment_amount_positive"),
        CheckConstraint(
            "source_tranche_id != destination_tranche_id", name="ck_adjustment_distinct_tranches"
        ),
        Index("idx_invoice_adjustments_source", "source_tranche_id"),
        Index("idx_invoice_adjustments_destination", "destination_tranche_id"),
    )


from app.models.deposit_request import DepositRequest  # noqa: E402
from app.models.masters import User  # noqa: E402
