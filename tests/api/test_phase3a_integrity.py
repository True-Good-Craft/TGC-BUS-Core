# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from core.services.integrity_validator import validate_finance_integrity, validate_inventory_integrity

pytestmark = pytest.mark.api


def _z(dt: datetime) -> str:
    return dt.replace(microsecond=0, tzinfo=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _create_item(client, name: str, price: float = 1.0) -> int:
    r = client.post("/app/items", json={"name": name, "dimension": "count", "uom": "ea", "price": price})
    assert r.status_code == 200, r.text
    payload = r.json()
    item = payload.get("item", payload)
    return int(item["id"])


def _purchase(client, item_id: int, qty_each: str, unit_cost_cents: int):
    r = client.post(
        "/app/purchase",
        json={
            "item_id": item_id,
            "quantity_decimal": qty_each,
            "uom": "ea",
            "unit_cost_decimal": f"{Decimal(unit_cost_cents):.2f}",
            "cost_uom": "ea",
            "meta": {},
            "note": "seed",
        },
    )
    assert r.status_code == 200, r.text


def _sale(client, item_id: int, qty_each: str, unit_price_cents: int):
    r = client.post(
        "/app/stock/out",
        json={
            "item_id": item_id,
            "quantity_decimal": qty_each,
            "uom": "ea",
            "reason": "sold",
            "record_cash_event": True,
            "sell_unit_price_cents": unit_price_cents,
        },
    )
    assert r.status_code == 200, r.text


def test_snapshot_dashboard_summary_30day_default(bus_client):
    client = bus_client["client"]
    item_id = _create_item(client, "DashSnapshot")
    _purchase(client, item_id, "1", 99)

    r = client.get("/app/dashboard/summary")
    assert r.status_code == 200, r.text
    j = r.json()

    start_dt = datetime.fromisoformat(j["window"]["start"].replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(j["window"]["end"].replace("Z", "+00:00"))
    assert end_dt - start_dt == timedelta(days=30)

    assert j == {
        "window": {"start": j["window"]["start"], "end": j["window"]["end"]},
        "inventory_value_cents": 10000,
        "units_produced": 0,
        "gross_revenue_cents": 0,
        "refunds_cents": 0,
        "net_revenue_cents": 0,
        "cogs_cents": 0,
        "gross_profit_cents": 0,
        "margin_percent": 0.0,
    }


def test_snapshot_finance_summary_fixed_window(bus_client):
    client = bus_client["client"]
    models = bus_client["models"]

    now = datetime(2025, 1, 15, 12, 0, 0)
    with bus_client["engine"].SessionLocal() as db:
        db.add(models.CashEvent(kind="sale", amount_cents=700, source_id="sale-fixed", created_at=now))
        db.add(models.CashEvent(kind="refund", amount_cents=-200, source_id="refund-fixed", created_at=now))
        db.add(models.ItemMovement(item_id=1, qty_change=-2, unit_cost_cents=100, source_kind="sold", source_id="sale-fixed"))
        db.commit()

    start = datetime(2025, 1, 1, 0, 0, 0)
    end = datetime(2025, 2, 1, 0, 0, 0)
    r = client.get(f"/app/finance/profit?start={start.isoformat()}Z&end={end.isoformat()}Z")
    assert r.status_code == 200, r.text
    assert r.json() == {
        "window": {"start": _z(start), "end": _z(end)},
        "gross_revenue_cents": 700,
        "refunds_cents": 200,
        "net_revenue_cents": 500,
        "cogs_cents": 200,
        "gross_profit_cents": 300,
        "margin_percent": 60.0,
        "math": {"formula": "Net Revenue (Gross - Refunds) - COGS = Gross Profit"},
    }


def test_snapshot_manufacturing_summary_known_fixture(bus_client):
    client = bus_client["client"]
    component = _create_item(client, "MfgComp")
    output_item = _create_item(client, "MfgOut")
    _purchase(client, component, "3", 7)

    r = client.post(
        "/app/manufacturing/run",
        json={"output_item_id": output_item, "output_qty": 2, "components": [{"item_id": component, "qty_required": 1}]},
    )
    assert r.status_code == 200, r.text
    j = r.json()

    assert j["produced_quantity"] == 2
    assert j["total_batch_cost_cents"] == 1
    assert j["cost_per_unit_cents"] == 0.5
    assert len(j["movements"]) == 2


def test_snapshot_cash_event_trace_response(bus_client):
    client = bus_client["client"]
    item = _create_item(client, "TraceItem")
    _purchase(client, item, "2", 30)
    _sale(client, item, "1", 100)

    with bus_client["engine"].SessionLocal() as db:
        sale = db.query(bus_client["models"].CashEvent).filter(bus_client["models"].CashEvent.kind == "sale").first()
        assert sale is not None
        source_id = sale.source_id

    r = client.get(f"/app/finance/cash-event/{source_id}")
    assert r.status_code == 200, r.text
    j = r.json()

    assert j["cash_event"]["source_id"] == source_id
    assert j["computed_cogs_cents"] == 3000
    assert j["net_profit_cents"] == -2900
    assert len(j["linked_movements"]) >= 1


def test_inventory_drift_parity_dashboard_vs_item_summary(bus_client):
    client = bus_client["client"]
    item = _create_item(client, "ParityItem")
    _purchase(client, item, "2", 45)

    dashboard = client.get("/app/dashboard/summary")
    summary = client.get(f"/app/items/{item}/summary")

    assert dashboard.status_code == 200, dashboard.text
    assert summary.status_code == 200, summary.text
    assert int(dashboard.json()["inventory_value_cents"]) == int(summary.json()["inventory_value_cents"])


def test_inventory_integrity_validator_ok(bus_client):
    with bus_client["engine"].SessionLocal() as db:
        report = validate_inventory_integrity(db).to_dict()
    assert report == {"ok": True, "issues": []}


def test_finance_integrity_validator_detects_sale_without_linked_movement(bus_client):
    models = bus_client["models"]
    now = datetime.utcnow()
    with bus_client["engine"].SessionLocal() as db:
        db.add(models.CashEvent(kind="sale", amount_cents=100, source_id="missing-link", created_at=now))
        db.commit()
        report = validate_finance_integrity(db).to_dict()

    assert report["ok"] is False
    assert any(i["code"] == "sale_missing_negative_movements" for i in report["issues"])
