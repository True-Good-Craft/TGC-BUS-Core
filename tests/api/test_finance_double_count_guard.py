# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from datetime import datetime

import pytest

pytestmark = pytest.mark.api


def _create_item(client, name: str) -> int:
    res = client.post("/app/items", json={"name": name, "dimension": "count", "uom": "ea", "price": 1.0})
    assert res.status_code == 200, res.text
    payload = res.json()
    item_obj = payload.get("item") if isinstance(payload, dict) else None
    if item_obj is None:
        item_obj = payload
    return int(item_obj["id"])


def test_finance_summary_double_count_guard(bus_client):
    client = bus_client["client"]
    models = bus_client["models"]
    engine_module = bus_client["engine"]

    item_id = _create_item(client, "Double Count Guard Item")
    created = datetime(2026, 2, 10, 10, 0, 0)

    with engine_module.SessionLocal() as db:
        db.add(
            models.CashEvent(
                kind="sale",
                amount_cents=1200,
                item_id=item_id,
                qty_base=2000,
                unit_price_cents=600,
                source_kind="sold",
                source_id="dcg-sale-1",
                created_at=created,
            )
        )
        db.add(
            models.ItemMovement(
                item_id=item_id,
                qty_change=-2000,
                unit_cost_cents=50,
                source_kind="sold",
                source_id="dcg-sale-1",
                created_at=created,
            )
        )
        db.commit()

    first = client.get("/app/finance/summary?from=2026-02-10&to=2026-02-10")
    second = client.get("/app/finance/summary?from=2026-02-10&to=2026-02-10")

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text

    payload1 = first.json()
    payload2 = second.json()

    assert payload1 == payload2

    sold1 = {int(row["item_id"]): row for row in payload1["units_sold"]}
    sold2 = {int(row["item_id"]): row for row in payload2["units_sold"]}
    assert sold1[item_id]["quantity_decimal"] == "2"
    assert sold2[item_id]["quantity_decimal"] == "2"
