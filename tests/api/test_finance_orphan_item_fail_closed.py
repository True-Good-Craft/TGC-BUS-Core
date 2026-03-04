# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import pytest

pytestmark = pytest.mark.api


def _create_item(client, name: str) -> int:
    res = client.post(
        "/app/items",
        json={"name": name, "dimension": "count", "uom": "ea", "price": 2.5},
    )
    assert res.status_code == 200, res.text
    payload = res.json()
    item_obj = payload.get("item") if isinstance(payload, dict) else None
    if item_obj is None:
        item_obj = payload
    return int(item_obj["id"])


def test_finance_endpoints_fail_closed_when_item_deleted_but_history_remains(bus_client):
    client = bus_client["client"]
    engine_module = bus_client["engine"]
    models = bus_client["models"]

    item_id = _create_item(client, "Orphan Finance Item")

    purchase = client.post(
        "/app/purchase",
        json={
            "item_id": item_id,
            "quantity_decimal": "10000",
            "uom": "mc",
            "unit_cost_cents": 7,
            "source_id": "orphan-seed",
        },
    )
    assert purchase.status_code == 200, purchase.text

    sold = client.post(
        "/app/stock/out",
        json={
            "item_id": item_id,
            "quantity_decimal": "2000",
            "uom": "mc",
            "reason": "sold",
            "record_cash_event": True,
            "sell_unit_price_cents": 30,
        },
    )
    assert sold.status_code == 200, sold.text

    with engine_module.SessionLocal() as db:
        item = db.get(models.Item, item_id)
        assert item is not None
        db.delete(item)
        db.commit()

    date_window = "from=2000-01-01&to=2100-01-01"

    summary = client.get(f"/app/finance/summary?{date_window}")
    assert summary.status_code == 400
    assert summary.json() == {"detail": {"error": "bad_request", "message": "item_not_found"}}

    transactions = client.get(f"/app/finance/transactions?{date_window}&limit=100")
    assert transactions.status_code == 400
    assert transactions.json() == {"detail": {"error": "bad_request", "message": "item_not_found"}}
