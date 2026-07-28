"""Public form submission — tranches accepted, retired config keys ignored."""

import json
import uuid

import pytest

from app.models.masters import SystemConfig
from tests.factories import make_customer, make_supplier, make_user

pytestmark = pytest.mark.asyncio


async def _seed(db_session, *, config: dict | None = None):
    user = await make_user(db_session)
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    if config is not None:
        db_session.add(
            SystemConfig(
                id=uuid.uuid4(),
                config_key="public_form_fields",
                config_value=json.dumps(config),
            )
        )
        await db_session.flush()
    return user, supplier, customer


def _body(user, supplier, customer, **extra):
    return {
        "submitter_email": user.email,
        "supplier_id": str(supplier.id),
        "customer_id": str(customer.id),
        "currency": "USD",
        "total_supplier_invoice_amount": 10000,
        "tranches": [
            {"amount": 2000, "tentative_payment_date": "2026-08-01"},
            {"amount": 1000, "tentative_payment_date": "2026-09-01"},
        ],
        **extra,
    }


async def test_submit_with_tranches(client, db_session):
    user, supplier, customer = await _seed(db_session)
    res = await client.post("/api/v1/public/submit", json=_body(user, supplier, customer))
    assert res.status_code == 200, res.text
    assert res.json()["request_number"].startswith("Dep-")


async def test_stale_deposit_percentage_required_config_is_ignored(client, db_session):
    """Regression: form configs saved before the tranche change marked the
    retired deposit_percentage field as required — that must not block
    submissions that (correctly) no longer send it."""
    user, supplier, customer = await _seed(
        db_session,
        config={
            "deposit_percentage": {"visible": True, "required": True, "label": "Deposit (%)"},
            "vertical_id": {"visible": True, "required": False, "label": "Vertical"},
        },
    )
    res = await client.post("/api/v1/public/submit", json=_body(user, supplier, customer))
    assert res.status_code == 200, res.text


async def test_configured_required_fields_still_enforced(client, db_session):
    user, supplier, customer = await _seed(
        db_session,
        config={"vertical_id": {"visible": True, "required": True, "label": "Vertical"}},
    )
    res = await client.post("/api/v1/public/submit", json=_body(user, supplier, customer))
    assert res.status_code == 422
    assert "Vertical" in res.json()["message"]


async def test_tranches_exceeding_invoice_rejected(client, db_session):
    user, supplier, customer = await _seed(db_session)
    body = _body(user, supplier, customer)
    body["tranches"] = [{"amount": 20000, "tentative_payment_date": "2026-08-01"}]
    res = await client.post("/api/v1/public/submit", json=body)
    assert res.status_code in (400, 422)


async def test_legacy_deposit_amount_only_still_works(client, db_session):
    user, supplier, customer = await _seed(db_session)
    body = _body(user, supplier, customer)
    del body["tranches"]
    body["deposit_amount"] = 1500
    res = await client.post("/api/v1/public/submit", json=body)
    assert res.status_code == 200, res.text
