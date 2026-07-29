"""Development auth bypass must yield a persisted users row.

Regression: the old in-memory dev identity broke every write path that
references users.id (audit logs, tranche payments, invoice adjustments) with
a ForeignKeyViolation, surfacing as an opaque 409 CONFLICT.
"""

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.dependencies import _DEV_USER_ID, get_current_user
from app.models.enums import UserRole
from app.models.masters import User

pytestmark = pytest.mark.asyncio


async def test_dev_bypass_persists_real_user_row(db_session, monkeypatch):
    monkeypatch.setattr(get_settings(), "app_env", "development")

    current = await get_current_user(authorization=None, db=db_session)
    assert current.id == _DEV_USER_ID
    assert current.role == UserRole.SUPER_ADMIN

    row = (
        await db_session.execute(select(User).where(User.id == _DEV_USER_ID))
    ).scalar_one_or_none()
    assert row is not None, "dev user must exist in users so FK writes succeed"
    assert row.is_active is True

    # Second call reuses the same row instead of duplicating it.
    again = await get_current_user(authorization=None, db=db_session)
    assert again.id == _DEV_USER_ID
