# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import pytest

pytestmark = pytest.mark.api


def _create_count_item(client, name: str) -> int:
    resp = client.post("/app/items", json={"name": name, "dimension": "count", "uom": "ea"})
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    item = payload.get("item") if isinstance(payload, dict) and "item" in payload else payload
    return int(item["id"])


def _insert_movement(bus_client, item_id: int, qty_change: int):
    models = bus_client["models"]
    with bus_client["engine"].SessionLocal() as db:
        db.add(
            models.ItemMovement(
                item_id=int(item_id),
                batch_id=None,
                qty_change=int(qty_change),
                unit_cost_cents=10,
                source_kind="test",
                source_id="test-movement",
                is_oversold=False,
            )
        )
        db.commit()


def test_ledger_history_returns_v2_fields_and_hides_base_by_default(bus_client):
    client = bus_client["client"]
    item_id = _create_count_item(client, "History Item")

    _insert_movement(bus_client, item_id, 2000)

    history = client.get(f"/app/ledger/history?item_id={item_id}&limit=10")
    assert history.status_code == 200, history.text
    payload = history.json()
    assert payload["movements"]
    movement = payload["movements"][0]
    assert "quantity_decimal" in movement
    assert "uom" in movement
    assert "qty_change" not in movement


def test_ledger_history_include_base_adds_qty_change(bus_client):
    client = bus_client["client"]
    item_id = _create_count_item(client, "History Item Include Base")

    _insert_movement(bus_client, item_id, 1000)

    history = client.get(f"/app/ledger/history?item_id={item_id}&limit=10&include_base=1")
    assert history.status_code == 200, history.text
    payload = history.json()
    assert payload["movements"]
    movement = payload["movements"][0]
    assert "quantity_decimal" in movement
    assert "uom" in movement
    assert "qty_change" in movement
