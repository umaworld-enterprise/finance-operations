"""ORM model for AnalyticsSnapshot — read-only computed metrics."""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin


class AnalyticsSnapshot(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "analytics_snapshots"

    deposit_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deposit_requests.id"), nullable=False, unique=True
    )

    # Computed date fields
    grace_etd: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Computed integer metrics
    etd_grace_overdue_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payment_to_ship_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payment_to_request_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_etd_overdue_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Cost of fund
    cost_of_fund_applicable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    cost_of_fund_amount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)

    # Delay classification
    default_status: Mapped[str | None] = mapped_column(String(50), nullable=True)

    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    deposit_request: Mapped["DepositRequest"] = relationship(back_populates="analytics_snapshot")


from app.models.deposit_request import DepositRequest  # noqa: E402, F401
