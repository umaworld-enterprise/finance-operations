"""ORM models: StatusHistory, MerchandiserAction, AccountsAction."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import AccountsActionType, MerchandiserActionType, RequestStatus, pg_enum


class StatusHistory(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "status_history"

    deposit_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deposit_requests.id"), nullable=False
    )
    old_status: Mapped[RequestStatus | None] = mapped_column(pg_enum(RequestStatus, "request_status"), nullable=True)
    new_status: Mapped[RequestStatus] = mapped_column(pg_enum(RequestStatus, "request_status"), nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    deposit_request: Mapped["DepositRequest"] = relationship(back_populates="status_history")
    changed_by_user: Mapped["User"] = relationship(back_populates="status_changes")

    __table_args__ = (
        Index("idx_status_history_request", "deposit_request_id", "changed_at"),
    )


class MerchandiserAction(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "merchandiser_actions"

    deposit_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deposit_requests.id"), nullable=False
    )
    action_type: Mapped[MerchandiserActionType] = mapped_column(
        pg_enum(MerchandiserActionType, "merchandiser_action_type"), nullable=False
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    performed_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    deposit_request: Mapped["DepositRequest"] = relationship(back_populates="merchandiser_actions")
    performer: Mapped["User"] = relationship(back_populates="merchandiser_actions")


class AccountsAction(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "accounts_actions"

    deposit_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deposit_requests.id"), nullable=False
    )
    action_type: Mapped[AccountsActionType] = mapped_column(
        pg_enum(AccountsActionType, "accounts_action_type"), nullable=False
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    performed_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    deposit_request: Mapped["DepositRequest"] = relationship(back_populates="accounts_actions")
    performer: Mapped["User"] = relationship(back_populates="accounts_actions")


from app.models.deposit_request import DepositRequest  # noqa: E402, F401
from app.models.masters import User  # noqa: E402, F401
