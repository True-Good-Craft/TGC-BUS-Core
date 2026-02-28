# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
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


def test_finance_transactions_surface_expected_kinds(bus_client):
    client = bus_client["client"]
    models = bus_client["models"]
    recipes = bus_client["recipes"]
    engine_module = bus_client["engine"]

    item_id = _create_item(client, "Finance Tx Item")
    created = datetime(2026, 1, 20, 10, 0, 0)

    with engine_module.SessionLocal() as db:
        db.add(models.CashEvent(kind="sale", amount_cents=500, item_id=item_id, qty_base=2000, unit_price_cents=250, source_kind="sold", source_id="sale-a", created_at=created))
        db.add(models.CashEvent(kind="refund", amount_cents=-100, item_id=item_id, qty_base=1000, source_kind="refund", source_id="refund-a", related_source_id="sale-a", created_at=created))
        db.add(models.CashEvent(kind="expense", amount_cents=-75, item_id=None, qty_base=None, source_kind="expense", source_id="expense-a", category="ops", notes="paper", created_at=created))
        db.add(models.ItemMovement(item_id=item_id, qty_change=-2000, unit_cost_cents=40, source_kind="sold", source_id="sale-a", created_at=created))
        db.add(models.ItemMovement(item_id=item_id, qty_change=5000, unit_cost_cents=20, source_kind="purchase", source_id="purchase-a", created_at=created))
        db.add(
            recipes.ManufacturingRun(
                output_item_id=item_id,
                output_qty=3000,
                status="completed",
                created_at=created,
                meta=json.dumps({"cost_inputs_cents": 160, "per_output_cents": 53}),
            )
        )
        db.commit()

    res = client.get("/app/finance/transactions?from=2026-01-20&to=2026-01-20&limit=20")
    assert res.status_code == 200, res.text
    payload = res.json()
    txs = payload["transactions"]

    kinds = {t["kind"] for t in txs}
    assert "sale" in kinds
    assert "refund" in kinds
    assert "expense" in kinds
    assert "manufacturing_run" in kinds
    assert "purchase_inferred" in kinds

    sale = next(t for t in txs if t["kind"] == "sale")
    assert int(sale["amount_cents"]) == 500
    assert int(sale["cogs_cents"]) == 80
    assert int(sale["gross_profit_cents"]) == 420

    purchase = next(t for t in txs if t["kind"] == "purchase_inferred")
    assert int(purchase["amount_cents"]) == 100
    assert purchase["quantity_decimal"] == "5"

    run = next(t for t in txs if t["kind"] == "manufacturing_run")
    assert int(run["cost_inputs_cents"]) == 160
    assert int(run["per_output_cents"]) == 53
    assert run["output_qty_decimal"] == "3"
