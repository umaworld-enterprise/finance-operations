"""Projections module (4 Sep 2026, migration 0034).

One row per (vertical, year, month): the merchandiser's projected deposit
amounts in USD / EUR / CNY for that month, collected between the 25th and the
end of the PREVIOUS month. Missing projections block the merchandiser from
raising new requests once the target month starts — only the Super Admin's
on-behalf entry unblocks them (submitted_by records who entered the row).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin


class Projection(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "projections"

    vertical_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("verticals.id"), nullable=False
    )
    # The merchandiser the projection belongs to (the vertical's assignee at
    # submission time) — NOT necessarily who typed it (see submitted_by).
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_usd: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    amount_eur: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    amount_cny: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    submitted_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    vertical: Mapped["Vertical"] = relationship()
    user: Mapped["User"] = relationship(foreign_keys=[user_id])

    __table_args__ = (
        CheckConstraint("month BETWEEN 1 AND 12", name="ck_projections_month"),
        UniqueConstraint("vertical_id", "year", "month", name="uq_projection_vertical_period"),
        Index("idx_projections_period", "year", "month"),
        Index("idx_projections_user", "user_id"),
    )


from app.models.masters import User, Vertical  # noqa: E402
