"""When each user last OPENED each sidebar section (29 Sep 2026).

Drives the sidebar badge: the count is what arrived or changed in a section
since the user's row here, so opening the page clears it.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class SectionView(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "section_views"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    section: Mapped[str] = mapped_column(String(40), nullable=False)
    viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("user_id", "section", name="uq_section_views_user_section"),
        Index("idx_section_views_user", "user_id"),
    )
