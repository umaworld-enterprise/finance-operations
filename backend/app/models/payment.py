"""ORM model for PaymentDetails — Accounts-owned data."""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin


class PaymentDetails(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "payment_details"

    deposit_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deposit_requests.id"), nullable=False, unique=True
    )
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    bank: Mapped[str | None] = mapped_column(String(200), nullable=True)
    payment_reference_number: Mapped[str | None] = mapped_column(String(200), nullable=True)
    payment_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ship_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_etd: Mapped[date | None] = mapped_column(Date, nullable=True)
    accounts_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    tt_copy_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    tt_copy_file_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tt_copy_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)

    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    deposit_request: Mapped["DepositRequest"] = relationship(back_populates="payment")
    updated_by_user: Mapped["User | None"] = relationship(back_populates="payment_updates")


from app.models.deposit_request import DepositRequest  # noqa: E402, F401
from app.models.masters import User  # noqa: E402, F401
