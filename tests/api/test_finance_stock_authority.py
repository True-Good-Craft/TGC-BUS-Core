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


def test_finance_summary_units_sold_uses_stock_movements_authority(bus_client):
    client = bus_client["client"]
    models = bus_client["models"]
    engine_module = bus_client["engine"]

    item_id = _create_item(client, "Stock Authority Item")
    created = datetime(2026, 2, 2, 10, 0, 0)

    with engine_module.SessionLocal() as db:
        db.add(
            models.CashEvent(
                kind="sale",
                amount_cents=700,
                item_id=item_id,
                qty_base=2000,
                unit_price_cents=350,
                source_kind="sold",
                source_id="sale-auth-1",
                created_at=created,
            )
        )
        db.add(
            models.CashEvent(
                kind="refund",
                amount_cents=-100,
                item_id=item_id,
                qty_base=1000,
                source_kind="refund",
                source_id="refund-auth-1",
                related_source_id="sale-auth-1",
                created_at=created,
            )
        )
        db.add(
            models.ItemMovement(
                item_id=item_id,
                qty_change=-3000,
                unit_cost_cents=20,
                source_kind="sold",
                source_id="sale-auth-1",
                created_at=created,
            )
        )
        db.commit()

    summary = client.get("/app/finance/summary?from=2026-02-02&to=2026-02-02")
    assert summary.status_code == 200, summary.text
    payload = summary.json()

    sold = {int(row["item_id"]): row for row in payload["units_sold"]}
    assert sold[item_id]["quantity_decimal"] == "3"


def test_finance_transactions_sale_without_movement_has_zero_cogs(bus_client):
    client = bus_client["client"]
    models = bus_client["models"]
    engine_module = bus_client["engine"]

    item_id = _create_item(client, "Missing Move Cogs Item")
    created = datetime(2026, 2, 3, 10, 0, 0)

    with engine_module.SessionLocal() as db:
        db.add(
            models.CashEvent(
                kind="sale",
                amount_cents=900,
                item_id=item_id,
                qty_base=3000,
                unit_price_cents=300,
                source_kind="sold",
                source_id="sale-no-move",
                created_at=created,
            )
        )
        db.commit()

    tx = client.get("/app/finance/transactions?from=2026-02-03&to=2026-02-03&limit=10")
    assert tx.status_code == 200, tx.text
    payload = tx.json()

    sale = next(row for row in payload["transactions"] if row["kind"] == "sale" and row["source_id"] == "sale-no-move")
    assert int(sale["amount_cents"]) == 900
    assert int(sale["cogs_cents"]) == 0
    assert int(sale["gross_profit_cents"]) == 900
