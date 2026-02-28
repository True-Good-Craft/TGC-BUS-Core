# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
from datetime import datetime, timedelta

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


def test_finance_summary_includes_kpis_and_units(bus_client):
    client = bus_client["client"]
    models = bus_client["models"]
    recipes = bus_client["recipes"]
    engine_module = bus_client["engine"]

    item_id = _create_item(client, "Finance KPI Item")

    day = datetime(2026, 1, 15, 12, 0, 0)
    outside = day + timedelta(days=2)

    with engine_module.SessionLocal() as db:
        db.add_all(
            [
                models.CashEvent(kind="sale", amount_cents=1000, item_id=item_id, qty_base=2000, unit_price_cents=500, source_kind="sold", source_id="sale-1", created_at=day),
                models.CashEvent(kind="sale", amount_cents=500, item_id=item_id, qty_base=1000, unit_price_cents=500, source_kind="sold", source_id="sale-2", created_at=day),
                models.CashEvent(kind="refund", amount_cents=-200, item_id=item_id, qty_base=1000, unit_price_cents=None, source_kind="refund", source_id="refund-1", related_source_id="sale-2", created_at=day),
                models.CashEvent(kind="expense", amount_cents=-300, item_id=None, qty_base=None, unit_price_cents=None, source_kind="expense", source_id="exp-1", created_at=day),
                models.CashEvent(kind="sale", amount_cents=9999, item_id=item_id, qty_base=1000, unit_price_cents=9999, source_kind="sold", source_id="sale-outside", created_at=outside),
            ]
        )
        db.add_all(
            [
                models.ItemMovement(item_id=item_id, qty_change=-2000, unit_cost_cents=30, source_kind="sold", source_id="sale-1", created_at=day),
                models.ItemMovement(item_id=item_id, qty_change=-1000, unit_cost_cents=30, source_kind="sold", source_id="sale-2", created_at=day),
            ]
        )
        db.add(
            recipes.ManufacturingRun(
                output_item_id=item_id,
                output_qty=4000,
                status="completed",
                created_at=day,
                meta=json.dumps({"cost_inputs_cents": 120, "per_output_cents": 30}),
            )
        )
        db.commit()

    res = client.get("/app/finance/summary?from=2026-01-15&to=2026-01-15")
    assert res.status_code == 200, res.text
    data = res.json()

    assert int(data["gross_sales_cents"]) == 1500
    assert int(data["returns_cents"]) == -200
    assert int(data["net_sales_cents"]) == 1300
    assert int(data["cogs_cents"]) == 90
    assert int(data["gross_profit_cents"]) == 1210
    assert int(data["expenses_cents"]) == 300
    assert int(data["net_profit_cents"]) == 910
    assert int(data["runs_count"]) == 1

    produced = {int(x["item_id"]): x for x in data["units_produced"]}
    sold = {int(x["item_id"]): x for x in data["units_sold"]}
    assert produced[item_id]["item_name"] == "Finance KPI Item"
    assert produced[item_id]["quantity_decimal"] == "4"
    assert produced[item_id]["uom"] == "ea"
    assert sold[item_id]["item_name"] == "Finance KPI Item"
    assert sold[item_id]["quantity_decimal"] == "3"
    assert sold[item_id]["uom"] == "ea"
