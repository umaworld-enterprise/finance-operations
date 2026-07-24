"""ORM model for AuditLog — immutable change history."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import AuditAction, pg_enum


class AuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_logs"

    entity_name: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    field_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    action: Mapped[AuditAction] = mapped_column(pg_enum(AuditAction, "audit_action"), nullable=False)
    changed_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    changed_by_user: Mapped["User"] = relationship(back_populates="audit_logs")

    __table_args__ = (
        Index("idx_audit_logs_entity", "entity_name", "entity_id", "changed_at"),
        Index("idx_audit_logs_user", "changed_by", "changed_at"),
    )


from app.models.masters import User  # noqa: E402, F401
