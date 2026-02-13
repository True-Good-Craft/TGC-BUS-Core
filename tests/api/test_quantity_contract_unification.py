# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import pytest

from core.api.quantity_contract import normalize_quantity_to_base_int

pytestmark = pytest.mark.api


def _create_item(client, name: str, dimension: str, uom: str) -> int:
    r = client.post("/app/items", json={"name": name, "dimension": dimension, "uom": uom, "price": 1.0})
    assert r.status_code == 200, r.text
    payload = r.json()
    obj = payload.get("item") if isinstance(payload, dict) else payload
    if obj is None:
        obj = payload
    return int(obj["id"])


def test_normalize_quantity_to_base_int_valid_and_string_stability():
    assert normalize_quantity_to_base_int("count", "ea", "2") == 2000
    assert normalize_quantity_to_base_int("weight", "kg", "0.001") == 1000
    assert normalize_quantity_to_base_int("length", "cm", ".5") == 5


def test_normalize_quantity_to_base_int_invalid_uom_and_fractional_rejected():
    with pytest.raises(Exception):
        normalize_quantity_to_base_int("weight", "ml", "1")
    with pytest.raises(Exception):
        normalize_quantity_to_base_int("count", "ea", "0.0005")


def test_consume_accepts_decimal_uom_and_writes_base_int(bus_client):
    client = bus_client["client"]
    models = bus_client["models"]
    engine = bus_client["engine"]

    item_id = _create_item(client, "ConsumeItem", "count", "ea")
    purchase = client.post(
        "/app/purchase",
        json={"item_id": item_id, "quantity_decimal": "3", "uom": "ea", "unit_cost_cents": 10},
    )
    assert purchase.status_code == 200, purchase.text

    resp = client.post(
        "/app/consume",
        json={"item_id": item_id, "quantity_decimal": "1", "uom": "ea", "source_kind": "consume"},
    )
    assert resp.status_code == 200, resp.text

    with engine.SessionLocal() as db:
        moves = db.query(models.ItemMovement).filter(models.ItemMovement.item_id == item_id).all()
        qty_total = sum(int(m.qty_change) for m in moves)
    assert qty_total == 2000


def test_stock_in_rejects_fractional_base_quantity(bus_client):
    client = bus_client["client"]
    item_id = _create_item(client, "FractionalReject", "count", "ea")

    resp = client.post(
        "/app/stock_in",
        json={"item_id": item_id, "uom": "ea", "quantity_decimal": "0.0005", "unit_cost_decimal": "1.00"},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["message"] == "fractional_base_quantity_not_allowed"
