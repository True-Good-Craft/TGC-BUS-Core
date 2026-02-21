# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import pytest

pytestmark = pytest.mark.api


def _create_item(client, name: str = "DeprecationItem") -> int:
    resp = client.post("/app/items", json={"name": name, "dimension": "count", "uom": "ea", "price": 1.0})
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    item = payload.get("item") if isinstance(payload, dict) else None
    if item is None:
        item = payload
    return int(item["id"])


def test_stock_in_legacy_emits_deprecation(bus_client):
    client = bus_client["client"]
    item_id = _create_item(client)

    resp = client.post(
        "/app/stock_in",
        json={"item_id": item_id, "uom": "ea", "quantity_decimal": "1", "unit_cost_decimal": "1.00", "cost_uom": "ea"},
    )

    assert resp.status_code == 200, resp.text
    assert dict(resp.headers).get("x-bus-deprecation") == "/app/stock/in"


def test_movements_legacy_emits_deprecation(bus_client):
    client = bus_client["client"]

    resp = client.get("/app/movements")

    assert resp.status_code == 200, resp.text
    assert dict(resp.headers).get("x-bus-deprecation") == "/app/ledger/history"


def test_ledger_movements_legacy_emits_deprecation(bus_client):
    client = bus_client["client"]

    resp = client.get("/app/ledger/movements")

    assert resp.status_code == 200, resp.text
    assert dict(resp.headers).get("x-bus-deprecation") == "/app/ledger/history"


def test_manufacturing_run_legacy_emits_deprecation(bus_client):
    client = bus_client["client"]
    engine = bus_client["engine"]
    models = bus_client["models"]
    recipes = bus_client["recipes"]

    with engine.SessionLocal() as db:
        output_item = models.Item(name="DeprecationOutput", uom="ea", qty_stored=0)
        input_item = models.Item(name="DeprecationInput", uom="ea", qty_stored=3)
        db.add_all([output_item, input_item])
        db.flush()

        recipe = recipes.Recipe(name="DeprecationRecipe", output_item_id=output_item.id, output_qty=1.0)
        db.add(recipe)
        db.flush()

        db.add(recipes.RecipeItem(recipe_id=recipe.id, item_id=input_item.id, qty_required=1.0, is_optional=False))
        db.add(
            models.ItemBatch(
                item_id=input_item.id,
                qty_initial=3.0,
                qty_remaining=3.0,
                unit_cost_cents=100,
                source_kind="seed",
                source_id=None,
                is_oversold=False,
            )
        )
        db.commit()
        recipe_id = recipe.id

    resp = client.post("/app/manufacturing/run", json={"recipe_id": recipe_id, "output_qty": 1})

    assert resp.status_code == 200, resp.text
    assert dict(resp.headers).get("x-bus-deprecation") == "/app/manufacture"
