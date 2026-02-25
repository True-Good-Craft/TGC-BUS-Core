# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import pytest

pytestmark = pytest.mark.api


def _create_item(client, name: str, dimension: str, uom: str):
    resp = client.post("/app/items", json={"name": name, "dimension": dimension, "uom": uom})
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    item = payload.get("item") if isinstance(payload, dict) and "item" in payload else payload
    return int(item["id"])


def test_recipes_accept_v2_payload_and_respond_without_legacy_qty_keys(bus_client):
    client = bus_client["client"]

    output_item_id = _create_item(client, "Recipe Output", "count", "ea")
    component_item_id = _create_item(client, "Recipe Input", "count", "ea")

    payload = {
        "name": "Cookie Dough",
        "output_item_id": output_item_id,
        "quantity_decimal": "1",
        "uom": "ea",
        "items": [
            {
                "item_id": component_item_id,
                "quantity_decimal": "2",
                "uom": "ea",
                "optional": False,
                "sort": 0,
            }
        ],
    }
    resp = client.post("/app/recipes", json=payload)
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert "quantity_decimal" in data
    assert "uom" in data
    assert "output_qty" not in data
    assert data["items"]
    assert "quantity_decimal" in data["items"][0]
    assert "uom" in data["items"][0]
    assert "qty_required" not in data["items"][0]


def test_recipes_reject_legacy_nested_qty_keys(bus_client):
    client = bus_client["client"]

    output_item_id = _create_item(client, "Legacy Out", "count", "ea")
    component_item_id = _create_item(client, "Legacy In", "count", "ea")

    payload = {
        "name": "Legacy Recipe",
        "output_item_id": output_item_id,
        "quantity_decimal": "1",
        "uom": "ea",
        "items": [
            {
                "item_id": component_item_id,
                "qty_required": 1000,
                "quantity_decimal": "1",
                "uom": "ea",
            }
        ],
    }
    resp = client.post("/app/recipes", json=payload)
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["detail"]["error"] == "legacy_quantity_keys_forbidden"
    assert "qty_required" in body["detail"]["keys"]
