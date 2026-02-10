# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.api


def _create_count_item(client: TestClient, name: str, price: float = 2.50) -> int:
    r = client.post(
        "/app/items",
        json={"name": name, "dimension": "count", "uom": "ea", "price": price},
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    # Support both shapes:
    # - {"item": {...}}
    # - direct item object {...}
    item_obj = payload.get("item") if isinstance(payload, dict) else None
    if item_obj is None and isinstance(payload, dict) and "id" in payload:
        item_obj = payload
    assert item_obj is not None, f"Unexpected item create response: {payload}"
    return int(item_obj["id"])


def _purchase_count_stock(client: TestClient, item_id: int, qty_each: str, unit_cost_cents: int):
    # Count items use base units (1 ea == 1000 base units). Buying N ea == N*1000 base.
    qty_base = int(qty_each) * 1000
    r = client.post(
        "/app/purchase",
        json={
            "item_id": int(item_id),
            "qty": qty_base,
            "unit_cost_cents": int(unit_cost_cents),
            "meta": {},
            "note": "seed",
        },
    )
    assert r.status_code == 200, r.text


def test_sale_records_cash_event_and_links_source_id(bus_client):
    client = bus_client["client"]
    engine_module = bus_client["engine"]
    models = bus_client["models"]

    item_id = _create_count_item(client, "CountItem", price=2.50)
    _purchase_count_stock(client, item_id, qty_each="10", unit_cost_cents=5)

    # Sell 2 ea = 2000 base units; unit price 300 cents => amount 600 cents
    r = client.post(
        "/app/stock/out",
        json={
            "item_id": item_id,
            "qty": 2000,
            "reason": "sold",
            "note": "sale",
            "record_cash_event": True,
            "sell_unit_price_cents": 300,
        },
    )
    assert r.status_code == 200, r.text

    from sqlalchemy.orm import sessionmaker

    SessionLocal = sessionmaker(bind=engine_module.get_engine(), future=True)
    db = SessionLocal()
    try:
        ce = (
            db.query(models.CashEvent)
            .filter(models.CashEvent.kind == "sale")
            .order_by(models.CashEvent.id.desc())
            .first()
        )
        assert ce is not None
        assert int(ce.item_id) == int(item_id)
        assert int(ce.qty_base) == 2000
        assert int(ce.unit_price_cents) == 300
        assert int(ce.amount_cents) == 600
        assert ce.source_id

        moves = db.query(models.ItemMovement).filter(models.ItemMovement.source_id == ce.source_id).all()
        assert moves
        total_qty = sum(int(m.qty_change) for m in moves)
        assert total_qty == -2000
    finally:
        db.close()


def test_refund_requires_cost_when_restock_true_and_no_related_source_id(bus_client):
    client = bus_client["client"]
    item_id = _create_count_item(client, "RefundItem", price=1.00)

    r = client.post(
        "/app/finance/refund",
        json={
            "item_id": item_id,
            "refund_amount_cents": 100,
            "qty_base": 1000,
            "restock_inventory": True,
            "related_source_id": None,
            "restock_unit_cost_cents": None,
        },
    )
    assert r.status_code in (400, 422)


def test_refund_without_restock_records_cash_event_only(bus_client):
    client = bus_client["client"]
    engine_module = bus_client["engine"]
    models = bus_client["models"]
    item_id = _create_count_item(client, "RefundCashOnly", price=1.00)

    refund = client.post(
        "/app/finance/refund",
        json={
            "item_id": item_id,
            "refund_amount_cents": 250,
            "qty_base": 1000,
            "restock_inventory": False,
            "related_source_id": None,
            "restock_unit_cost_cents": None,
        },
    )
    assert refund.status_code == 200, refund.text

    with engine_module.SessionLocal() as db:
        cash_events = db.query(models.CashEvent).filter(models.CashEvent.kind == "refund").all()
        movements = db.query(models.ItemMovement).filter(models.ItemMovement.source_kind == "refund").all()

    assert len(cash_events) == 1
    assert int(cash_events[0].amount_cents) == -250
    assert movements == []


def test_profit_window_exclusive_upper_bound(bus_client):
    from sqlalchemy.orm import sessionmaker
    engine_module = bus_client["engine"]
    models = bus_client["models"]

    SessionLocal = sessionmaker(bind=engine_module.get_engine(), future=True)

    day = datetime.utcnow().date()
    from_dt = datetime(day.year, day.month, day.day, 0, 0, 0)
    next_dt = from_dt + timedelta(days=1)

    db = SessionLocal()
    try:
        db.add(
            models.CashEvent(
                kind="sale",
                category=None,
                amount_cents=111,
                item_id=None,
                qty_base=None,
                unit_price_cents=None,
                source_kind="sold",
                source_id="t_from",
                related_source_id=None,
                notes=None,
                created_at=from_dt,
            )
        )
        db.add(
            models.CashEvent(
                kind="sale",
                category=None,
                amount_cents=222,
                item_id=None,
                qty_base=None,
                unit_price_cents=None,
                source_kind="sold",
                source_id="t_next",
                related_source_id=None,
                notes=None,
                created_at=next_dt,
            )
        )
        db.commit()
    finally:
        db.close()

    s = day.strftime("%Y-%m-%d")
    pr = bus_client["client"].get(f"/app/finance/profit?from={s}&to={s}")
    assert pr.status_code == 200, pr.text
    j = pr.json()
    assert int(j["gross_sales_cents"]) == 111
