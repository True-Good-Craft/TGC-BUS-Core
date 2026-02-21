# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from core.api.read_models import get_finance_summary, get_inventory_value, get_units_produced

pytestmark = pytest.mark.api


def _create_item(client, name: str = "Item") -> int:
    r = client.post("/app/items", json={"name": name, "dimension": "count", "uom": "ea", "price": 1.0})
    assert r.status_code == 200, r.text
    payload = r.json()
    item = payload.get("item", payload)
    return int(item["id"])


def _purchase(client, item_id: int, qty_each: str, unit_cost_cents: int):
    r = client.post(
        "/app/purchase",
        json={
            "item_id": int(item_id),
            "quantity_decimal": str(qty_each),
            "uom": "ea",
            "unit_cost_decimal": f"{Decimal(unit_cost_cents):.2f}",
            "cost_uom": "ea",
            "meta": {},
            "note": "seed",
        },
    )
    assert r.status_code == 200, r.text


def _sale(client, item_id: int, qty_each: str, price_cents: int):
    r = client.post(
        "/app/stock/out",
        json={
            "item_id": int(item_id),
            "quantity_decimal": str(qty_each),
            "uom": "ea",
            "reason": "sold",
            "note": "sale",
            "record_cash_event": True,
            "sell_unit_price_cents": int(price_cents),
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_inventory_value_simple(bus_client):
    client = bus_client["client"]
    item_id = _create_item(client, "InventorySimple")
    _purchase(client, item_id, qty_each="3", unit_cost_cents=25)

    with bus_client["engine"].SessionLocal() as db:
        assert get_inventory_value(db) == 9000


def test_inventory_value_with_zero_cost(bus_client):
    client = bus_client["client"]
    item_id = _create_item(client, "InventoryZeroCost")
    _purchase(client, item_id, qty_each="2", unit_cost_cents=100)
    _purchase(client, item_id, qty_each="1", unit_cost_cents=0)

    with bus_client["engine"].SessionLocal() as db:
        assert get_inventory_value(db) == 20000


def test_units_produced_window(bus_client):
    models = bus_client["models"]
    now = datetime.utcnow()

    with bus_client["engine"].SessionLocal() as db:
        db.add(models.ManufacturingRun(output_item_id=1, output_qty=10, status="completed", executed_at=now - timedelta(days=2)))
        db.add(models.ManufacturingRun(output_item_id=1, output_qty=5, status="completed", executed_at=now - timedelta(days=40)))
        db.commit()

        total = get_units_produced(db, start_dt=now - timedelta(days=30), end_dt=now)
        assert total == 10


def test_finance_summary_basic_sale(bus_client):
    client = bus_client["client"]
    item_id = _create_item(client, "FinanceBasicSale")
    _purchase(client, item_id, qty_each="10", unit_cost_cents=5)
    _sale(client, item_id, qty_each="2", price_cents=300)

    with bus_client["engine"].SessionLocal() as db:
        now = datetime.utcnow()
        summary = get_finance_summary(db, start_dt=now - timedelta(days=1), end_dt=now + timedelta(days=1))

    assert summary.gross_revenue_cents == 600
    assert summary.refunds_cents == 0
    assert summary.net_revenue_cents == 600
    assert summary.cogs_cents == 2000
    assert summary.gross_profit_cents == -1400


def test_finance_summary_refund(bus_client):
    client = bus_client["client"]
    item_id = _create_item(client, "FinanceRefund")
    _purchase(client, item_id, qty_each="5", unit_cost_cents=10)
    _sale(client, item_id, qty_each="1", price_cents=500)
    refund = client.post(
        "/app/finance/refund",
        json={
            "item_id": int(item_id),
            "refund_amount_cents": 200,
            "quantity_decimal": "1",
            "uom": "ea",
            "restock_inventory": False,
        },
    )
    assert refund.status_code == 200, refund.text

    with bus_client["engine"].SessionLocal() as db:
        now = datetime.utcnow()
        summary = get_finance_summary(db, start_dt=now - timedelta(days=1), end_dt=now + timedelta(days=1))

    assert summary.gross_revenue_cents == 500
    assert summary.refunds_cents == 200
    assert summary.net_revenue_cents == 300


def test_finance_summary_no_sales(bus_client):
    with bus_client["engine"].SessionLocal() as db:
        now = datetime.utcnow()
        summary = get_finance_summary(db, start_dt=now - timedelta(days=1), end_dt=now + timedelta(days=1))

    assert summary.gross_revenue_cents == 0
    assert summary.refunds_cents == 0
    assert summary.net_revenue_cents == 0
    assert summary.cogs_cents == 0
    assert summary.gross_profit_cents == 0
    assert summary.margin_percent == 0.0


def test_finance_summary_orphan_cash_event(bus_client):
    models = bus_client["models"]
    now = datetime.utcnow()
    with bus_client["engine"].SessionLocal() as db:
        db.add(models.CashEvent(kind="sale", amount_cents=1234, source_id="orphan", created_at=now))
        db.commit()
        summary = get_finance_summary(db, start_dt=now - timedelta(days=1), end_dt=now + timedelta(days=1))

    assert summary.gross_revenue_cents == 1234
    assert summary.cogs_cents == 0


def test_finance_summary_cogs_linked(bus_client):
    models = bus_client["models"]
    client = bus_client["client"]
    item_id = _create_item(client, "CogsLinked")
    now = datetime.utcnow()
    with bus_client["engine"].SessionLocal() as db:
        db.add(models.CashEvent(kind="sale", amount_cents=1000, source_id="sale-1", created_at=now))
        db.add(models.ItemMovement(item_id=item_id, qty_change=-10, unit_cost_cents=7, source_kind="sold", source_id="other-source"))
        db.commit()
        summary = get_finance_summary(db, start_dt=now - timedelta(days=1), end_dt=now + timedelta(days=1))

    assert summary.cogs_cents == 0


def test_margin_divide_by_zero_guard(bus_client):
    models = bus_client["models"]
    now = datetime.utcnow()
    with bus_client["engine"].SessionLocal() as db:
        db.add(models.CashEvent(kind="sale", amount_cents=100, source_id="s1", created_at=now))
        db.add(models.CashEvent(kind="refund", amount_cents=-100, source_id="r1", created_at=now))
        db.commit()
        summary = get_finance_summary(db, start_dt=now - timedelta(days=1), end_dt=now + timedelta(days=1))

    assert summary.net_revenue_cents == 0
    assert summary.margin_percent == 0.0


def test_dashboard_summary_default_window(bus_client):
    models = bus_client["models"]
    now = datetime.utcnow()
    with bus_client["engine"].SessionLocal() as db:
        db.add(models.CashEvent(kind="sale", amount_cents=111, source_id="in-window", created_at=now - timedelta(days=10)))
        db.add(models.CashEvent(kind="sale", amount_cents=222, source_id="out-window", created_at=now - timedelta(days=40)))
        db.commit()

    r = bus_client["client"].get("/app/dashboard/summary")
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["gross_revenue_cents"] == 111
