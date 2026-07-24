"""ORM model for the defaulted-suppliers integration table."""

import uuid
from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import CurrencyCode, pg_enum


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


from app.models.masters import Supplier, User  # noqa: E402, F401
