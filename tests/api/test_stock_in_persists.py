# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from decimal import Decimal

import pytest

pytestmark = pytest.mark.api


def _create_count_item(client, name: str) -> int:
    resp = client.post("/app/items", json={"name": name, "dimension": "count", "uom": "ea"})
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    item = payload.get("item") if isinstance(payload, dict) and "item" in payload else payload
    return int(item["id"])


def test_stock_in_persists_inventory_and_ledger(bus_client):
    client = bus_client["client"]
    item_id = _create_count_item(client, "Stock In Persist Item")

    source_id = "test-seedA"
    stock_in = client.post(
        "/app/stock/in",
        json={
            "item_id": item_id,
            "quantity_decimal": "30",
            "uom": "ea",
            "unit_cost_cents": 100,
            "source_id": source_id,
        },
    )
    assert stock_in.status_code == 200, stock_in.text
    payload = stock_in.json()
    assert payload.get("ok") is True
    assert payload.get("batch_id")

    history = client.get("/app/ledger/history?limit=200")
    assert history.status_code == 200, history.text
    movements = history.json().get("movements", [])

    matching = [m for m in movements if m.get("source_id") == source_id and int(m.get("item_id")) == item_id]
    assert matching, "stock/in returned ok but no ledger movement was persisted for source_id"

    entry = matching[0]
    assert Decimal(str(entry.get("quantity_decimal"))) == Decimal("30")
    assert entry.get("uom") == "ea"

    items = client.get("/app/items")
    assert items.status_code == 200, items.text
    item_row = next((it for it in items.json() if int(it.get("id")) == item_id), None)
    assert item_row is not None
    assert int(item_row.get("qty_stored") or 0) > 0
