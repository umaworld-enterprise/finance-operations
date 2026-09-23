"""When each user last OPENED each deposit request (23 Sep 2026).

Drives the Accounts seen/unseen red dot: a request is "unseen" while its
latest activity is newer than the viewer's row here (or, when never opened,
newer than the user's ``unseen_since`` baseline).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class RequestView(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "request_views"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    deposit_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deposit_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("user_id", "deposit_request_id", name="uq_request_views_user_request"),
        Index("idx_request_views_user", "user_id", "viewed_at"),
    )
