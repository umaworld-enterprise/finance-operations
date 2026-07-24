"""Unit tests for PaymentService.set_ship_date — the post-lock "final date" path.

Recording the ship date is the designed action that stops Cost of Fund accrual
on locked (payment_processed) records, so unlike the rest of the payment write
path it must work while is_locked=True and must be open to Finance Admin too.
Repos are stubbed — these tests cover the service's role guard, lock bypass,
audit values and get-or-create behaviour, not the database layer.
"""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import AuthorizationError, NotFoundError
from app.models.enums import UserRole
from app.services.payment_service import PaymentService


def _make_service(*, request_exists=True, is_locked=True, existing_ship_date="unset"):
    svc = PaymentService(MagicMock())

    request = SimpleNamespace(is_locked=is_locked) if request_exists else None
    svc._request_repo = MagicMock()
    svc._request_repo.get_for_validation = AsyncMock(return_value=request)

    if existing_ship_date == "unset":
        existing = None
    else:
        existing = SimpleNamespace(id=uuid4(), ship_date=existing_ship_date)

    payment = existing or SimpleNamespace(id=uuid4(), ship_date=None)
    svc._payment_repo = MagicMock()
    svc._payment_repo.get_by_request_id = AsyncMock(return_value=existing)
    svc._payment_repo.update = AsyncMock(return_value=payment)
    svc._payment_repo.create = AsyncMock(return_value=payment)

    svc._audit = MagicMock()
    svc._audit.record_update = AsyncMock()
    return svc


@pytest.mark.parametrize(
    "role", [UserRole.SUPER_ADMIN, UserRole.FINANCE_ADMIN, UserRole.ACCOUNTS_TEAM]
)
async def test_allowed_roles_can_set_ship_date_on_locked_record(role):
    svc = _make_service(is_locked=True, existing_ship_date=None)
    await svc.set_ship_date(uuid4(), date(2026, 7, 20), uuid4(), role)
    svc._payment_repo.update.assert_awaited_once()
    assert svc._payment_repo.update.await_args.kwargs["ship_date"] == date(2026, 7, 20)


@pytest.mark.parametrize(
    "role", [UserRole.MERCHANDISER, UserRole.HEAD_OF_MERCHANDISER]
)
async def test_other_roles_are_rejected(role):
    svc = _make_service()
    with pytest.raises(AuthorizationError):
        await svc.set_ship_date(uuid4(), date(2026, 7, 20), uuid4(), role)
    svc._payment_repo.update.assert_not_awaited()
    svc._payment_repo.create.assert_not_awaited()


async def test_missing_request_raises_not_found():
    svc = _make_service(request_exists=False)
    with pytest.raises(NotFoundError):
        await svc.set_ship_date(
            uuid4(), date(2026, 7, 20), uuid4(), UserRole.ACCOUNTS_TEAM
        )


async def test_correction_overwrites_and_audits_before_after():
    svc = _make_service(existing_ship_date=date(2026, 7, 15))
    await svc.set_ship_date(
        uuid4(), date(2026, 7, 22), uuid4(), UserRole.SUPER_ADMIN
    )
    audit_kwargs = svc._audit.record_update.await_args.kwargs
    assert audit_kwargs["field_name"] == "ship_date"
    assert audit_kwargs["old_value"] == "2026-07-15"
    assert audit_kwargs["new_value"] == "2026-07-22"


async def test_creates_payment_row_when_none_exists():
    svc = _make_service(existing_ship_date="unset")
    request_id = uuid4()
    await svc.set_ship_date(
        request_id, date(2026, 7, 20), uuid4(), UserRole.FINANCE_ADMIN
    )
    svc._payment_repo.create.assert_awaited_once()
    assert (
        svc._payment_repo.create.await_args.kwargs["deposit_request_id"] == request_id
    )
    audit_kwargs = svc._audit.record_update.await_args.kwargs
    assert audit_kwargs["old_value"] is None
