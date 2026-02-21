# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

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
            "quantity_decimal": "2",
            "uom": "ea",
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
            "quantity_decimal": "1",
            "uom": "ea",
            "restock_inventory": True,
            "related_source_id": None,
            "restock_unit_cost_decimal": None,
            "restock_cost_uom": None,
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
            "quantity_decimal": "1",
            "uom": "ea",
            "restock_inventory": False,
            "related_source_id": None,
            "restock_unit_cost_decimal": None,
            "restock_cost_uom": None,
        },
    )
    assert refund.status_code == 200, refund.text

    with engine_module.SessionLocal() as db:
        cash_events = db.query(models.CashEvent).filter(models.CashEvent.kind == "refund").all()
        movements = db.query(models.ItemMovement).filter(models.ItemMovement.source_kind == "refund").all()

    assert len(cash_events) == 1
    assert int(cash_events[0].amount_cents) == -250
    assert movements == []


def test_old_qty_payload_is_rejected(bus_client):
    client = bus_client["client"]
    item_id = _create_count_item(client, "LegacyQty", price=2.0)

    r = client.post(
        "/app/purchase",
        json={
            "item_id": int(item_id),
            "qty": 1000,
            "unit_cost_decimal": "50.00", "cost_uom": "ea",
        },
    )
    assert r.status_code in (400, 422), r.text
    assert "legacy_qty_field_not_allowed" in r.text


def test_stock_out_legacy_qty_payload_is_rejected(bus_client):
    client = bus_client["client"]
    item_id = _create_count_item(client, "LegacyStockOut", price=2.0)

    r = client.post(
        "/app/stock/out",
        json={
            "item_id": int(item_id),
            "qty": 1,
            "quantity_decimal": "1",
            "uom": "ea",
            "reason": "sold",
        },
    )
    assert r.status_code in (400, 422), r.text
    assert "legacy_qty_field_not_allowed" in r.text


def test_refund_legacy_qty_base_payload_is_rejected(bus_client):
    client = bus_client["client"]
    item_id = _create_count_item(client, "LegacyRefund", price=2.0)

    r = client.post(
        "/app/finance/refund",
        json={
            "item_id": int(item_id),
            "qty_base": 1,
            "quantity_decimal": "1",
            "uom": "ea",
            "refund_amount_cents": 100,
            "restock_inventory": False,
        },
    )
    assert r.status_code in (400, 422), r.text
    assert "legacy_qty_field_not_allowed" in r.text


def test_adjust_legacy_qty_change_payload_is_rejected(bus_client):
    client = bus_client["client"]
    item_id = _create_count_item(client, "LegacyAdjust", price=2.0)

    r = client.post(
        "/app/adjust",
        json={
            "item_id": int(item_id),
            "qty_change": 1,
            "quantity_decimal": "1",
            "uom": "mc",
            "direction": "in",
        },
    )
    assert r.status_code in (400, 422), r.text
    assert "legacy_qty_field_not_allowed" in r.text


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
    assert int(j["gross_revenue_cents"]) == 111


def test_sale_stock_and_cash_event_are_atomic(bus_client, monkeypatch):
    client = bus_client["client"]
    engine_module = bus_client["engine"]
    models = bus_client["models"]
    import core.api.routes.ledger_api as ledger_module

    item_id = _create_count_item(client, "AtomicSale", price=2.0)
    _purchase_count_stock(client, item_id, qty_each="5", unit_cost_cents=10)

    class BoomCashEvent:  # fail after FIFO movements are staged
        def __init__(self, **kwargs):
            raise RuntimeError("forced_cash_event_failure")

    monkeypatch.setattr(ledger_module, "CashEvent", BoomCashEvent)

    with pytest.raises(RuntimeError):
        client.post(
            "/app/stock/out",
            json={
                "item_id": item_id,
                "quantity_decimal": "1",
                "uom": "ea",
                "reason": "sold",
                "record_cash_event": True,
                "sell_unit_price_cents": 250,
            },
        )

    with engine_module.SessionLocal() as db:
        sold_moves = db.query(models.ItemMovement).filter(models.ItemMovement.source_kind == "sold").all()
        sale_events = db.query(models.CashEvent).filter(models.CashEvent.kind == "sale").all()
        qty_remaining = (
            db.query(models.ItemBatch.qty_remaining)
            .filter(models.ItemBatch.item_id == item_id)
            .order_by(models.ItemBatch.id.asc())
            .first()[0]
        )

    assert sold_moves == []
    assert sale_events == []
    assert int(qty_remaining) == 5000


def test_refund_cash_event_and_restock_are_atomic(bus_client, monkeypatch):
    client = bus_client["client"]
    engine_module = bus_client["engine"]
    models = bus_client["models"]

    import core.api.routes.finance_api as finance_module

    item_id = _create_count_item(client, "AtomicRefund", price=1.0)

    def _boom_add_batch(*args, **kwargs):
        raise RuntimeError("forced_restock_failure")

    monkeypatch.setattr(finance_module, "add_batch", _boom_add_batch)

    with pytest.raises(RuntimeError):
        client.post(
            "/app/finance/refund",
            json={
                "item_id": item_id,
                "refund_amount_cents": 100,
                "quantity_decimal": "1",
                "uom": "ea",
                "restock_inventory": True,
                "restock_unit_cost_decimal": "5.00",
                "restock_cost_uom": "ea",
            },
        )

    with engine_module.SessionLocal() as db:
        refund_events = db.query(models.CashEvent).filter(models.CashEvent.kind == "refund").all()
        restock_moves = db.query(models.ItemMovement).filter(models.ItemMovement.source_kind == "refund_restock").all()
    assert refund_events == []
    assert restock_moves == []


def test_profit_math_and_zero_margin_guard(bus_client):
    client = bus_client["client"]
    item_id = _create_count_item(client, "ProfitMath", price=5.0)
    _purchase_count_stock(client, item_id, qty_each="2", unit_cost_cents=100)

    sold = client.post(
        "/app/stock/out",
        json={
            "item_id": item_id,
            "quantity_decimal": "1",
            "uom": "ea",
            "reason": "sold",
            "record_cash_event": True,
            "sell_unit_price_cents": 500,
        },
    )
    assert sold.status_code == 200, sold.text

    refunded = client.post(
        "/app/finance/refund",
        json={
            "item_id": item_id,
            "refund_amount_cents": 500,
            "quantity_decimal": "1",
            "uom": "ea",
            "restock_inventory": False,
        },
    )
    assert refunded.status_code == 200, refunded.text

    day = datetime.utcnow().date().strftime("%Y-%m-%d")
    pr = client.get(f"/app/finance/profit?from={day}&to={day}")
    assert pr.status_code == 200, pr.text
    payload = pr.json()
    assert int(payload["gross_revenue_cents"]) == 500
    assert int(payload["refunds_cents"]) == 500
    assert int(payload["net_revenue_cents"]) == 0
    assert int(payload["cogs_cents"]) == 10000
    assert int(payload["gross_profit_cents"]) == -10000
    assert float(payload["margin_percent"]) == 0.0


def test_cogs_filters_only_sale_linked_movements(bus_client):
    client = bus_client["client"]
    engine_module = bus_client["engine"]
    models = bus_client["models"]

    item_id = _create_count_item(client, "COGSLink", price=1.0)
    now = datetime.utcnow()

    with engine_module.SessionLocal() as db:
        db.add(
            models.CashEvent(
                kind="sale",
                category=None,
                amount_cents=1000,
                item_id=item_id,
                qty_base=10,
                unit_price_cents=100,
                source_kind="sold",
                source_id="sale-link",
                related_source_id=None,
                notes=None,
                created_at=now,
            )
        )
        db.add(
            models.ItemMovement(
                item_id=item_id,
                batch_id=None,
                qty_change=-10,
                unit_cost_cents=3,
                source_kind="sold",
                source_id="sale-link",
                is_oversold=False,
                created_at=now,
            )
        )
        db.add(
            models.ItemMovement(
                item_id=item_id,
                batch_id=None,
                qty_change=-10,
                unit_cost_cents=99,
                source_kind="sold",
                source_id="not-linked",
                is_oversold=False,
                created_at=now,
            )
        )
        db.commit()

    day = now.date().strftime("%Y-%m-%d")
    pr = client.get(f"/app/finance/profit?from={day}&to={day}")
    assert pr.status_code == 200, pr.text
    payload = pr.json()
    assert int(payload["cogs_cents"]) == 30


def test_quantity_routes_use_normalize_quantity_contract(bus_client, monkeypatch):
    client = bus_client["client"]
    import core.api.routes.ledger_api as ledger_module
    import core.api.routes.finance_api as finance_module

    calls: list[tuple[str, str, str]] = []

    def _track_ledger(dimension: str, uom: str, quantity_decimal: str) -> int:
        calls.append(("ledger", dimension, uom))
        return 1000

    def _track_finance(dimension: str, uom: str, quantity_decimal: str) -> int:
        calls.append(("finance", dimension, uom))
        return 1000

    monkeypatch.setattr(ledger_module, "normalize_quantity_to_base_int", _track_ledger)
    monkeypatch.setattr(finance_module, "normalize_quantity_to_base_int", _track_finance)

    item_id = _create_count_item(client, "QuantityContract", price=2.0)

    assert client.post(
        "/app/purchase",
        json={"item_id": item_id, "quantity_decimal": "1", "uom": "ea", "unit_cost_decimal": "10.00", "cost_uom": "ea"},
    ).status_code == 200
    assert client.post(
        "/app/stock/out",
        json={"item_id": item_id, "quantity_decimal": "1", "uom": "ea", "reason": "loss"},
    ).status_code == 200
    assert client.post(
        "/app/stock_in",
        json={"item_id": item_id, "quantity_decimal": "1", "uom": "ea", "unit_cost_decimal": "1.00", "cost_uom": "ea"},
    ).status_code == 200
    assert client.post(
        "/app/finance/refund",
        json={
            "item_id": item_id,
            "refund_amount_cents": 100,
            "quantity_decimal": "1",
            "uom": "ea",
            "restock_inventory": False,
        },
    ).status_code == 200

    assert [c[0] for c in calls].count("ledger") == 3
    assert [c[0] for c in calls].count("finance") == 1


def test_fifo_partial_sale_uses_oldest_batch(bus_client):
    client = bus_client["client"]
    engine_module = bus_client["engine"]
    models = bus_client["models"]

    item_id = _create_count_item(client, "FIFOPartial", price=3.0)
    _purchase_count_stock(client, item_id, qty_each="2", unit_cost_cents=10)
    _purchase_count_stock(client, item_id, qty_each="2", unit_cost_cents=20)

    sold = client.post(
        "/app/stock/out",
        json={
            "item_id": item_id,
            "quantity_decimal": "3",
            "uom": "ea",
            "reason": "sold",
            "record_cash_event": True,
            "sell_unit_price_cents": 300,
        },
    )
    assert sold.status_code == 200, sold.text
    sale_source_id = sold.json()["lines"][0]["source_id"]

    with engine_module.SessionLocal() as db:
        moves = (
            db.query(models.ItemMovement)
            .filter(models.ItemMovement.source_id == sale_source_id)
            .order_by(models.ItemMovement.id.asc())
            .all()
        )
    assert len(moves) == 2
    assert int(moves[0].qty_change) == -2000
    assert int(moves[0].unit_cost_cents) == 1
    assert int(moves[1].qty_change) == -1000
    assert int(moves[1].unit_cost_cents) == 2


def test_refund_restock_restores_stock_and_no_restock_leaves_stock(bus_client):
    client = bus_client["client"]
    engine_module = bus_client["engine"]
    models = bus_client["models"]

    item_id = _create_count_item(client, "RefundStock", price=3.0)
    _purchase_count_stock(client, item_id, qty_each="3", unit_cost_cents=10)

    sold = client.post(
        "/app/stock/out",
        json={
            "item_id": item_id,
            "quantity_decimal": "1",
            "uom": "ea",
            "reason": "sold",
            "record_cash_event": True,
            "sell_unit_price_cents": 300,
        },
    )
    assert sold.status_code == 200, sold.text
    sale_source_id = sold.json()["lines"][0]["source_id"]

    def _on_hand() -> int:
        with engine_module.SessionLocal() as db:
            return int(sum(int(b.qty_remaining) for b in db.query(models.ItemBatch).filter(models.ItemBatch.item_id == item_id).all()))

    on_hand_after_sale = _on_hand()
    assert on_hand_after_sale == 2000

    r1 = client.post(
        "/app/finance/refund",
        json={
            "item_id": item_id,
            "refund_amount_cents": 300,
            "quantity_decimal": "1",
            "uom": "ea",
            "restock_inventory": True,
            "related_source_id": sale_source_id,
        },
    )
    assert r1.status_code == 200, r1.text
    assert _on_hand() == 3000

    r2 = client.post(
        "/app/finance/refund",
        json={
            "item_id": item_id,
            "refund_amount_cents": 100,
            "quantity_decimal": "1",
            "uom": "ea",
            "restock_inventory": False,
        },
    )
    assert r2.status_code == 200, r2.text
    assert _on_hand() == 3000


def test_expense_does_not_change_cogs(bus_client):
    client = bus_client["client"]

    item_id = _create_count_item(client, "ExpenseNoCOGS", price=4.0)
    _purchase_count_stock(client, item_id, qty_each="1", unit_cost_cents=125)
    sold = client.post(
        "/app/stock/out",
        json={
            "item_id": item_id,
            "quantity_decimal": "1",
            "uom": "ea",
            "reason": "sold",
            "record_cash_event": True,
            "sell_unit_price_cents": 400,
        },
    )
    assert sold.status_code == 200, sold.text
    expense = client.post("/app/finance/expense", json={"amount_cents": 999, "category": "ops"})
    assert expense.status_code == 200, expense.text

    day = datetime.utcnow().date().strftime("%Y-%m-%d")
    pr = client.get(f"/app/finance/profit?from={day}&to={day}")
    assert pr.status_code == 200, pr.text
    payload = pr.json()
    assert int(payload["cogs_cents"]) == 13000


def test_inventory_cost_routes_use_normalize_cost_contract(bus_client, monkeypatch):
    client = bus_client["client"]
    import core.api.routes.ledger_api as ledger_module
    import core.api.routes.finance_api as finance_module

    calls: list[str] = []

    def _track_ledger_cost(dimension: str, cost_uom: str, unit_cost_decimal: str) -> int:
        calls.append("ledger")
        return 1

    def _track_finance_cost(dimension: str, cost_uom: str, unit_cost_decimal: str) -> int:
        calls.append("finance")
        return 1

    monkeypatch.setattr(ledger_module, "normalize_cost_to_base_cents", _track_ledger_cost)
    monkeypatch.setattr(finance_module, "normalize_cost_to_base_cents", _track_finance_cost)

    item_id = _create_count_item(client, "CostContract", price=2.0)

    assert client.post(
        "/app/purchase",
        json={"item_id": item_id, "quantity_decimal": "1", "uom": "ea", "unit_cost_decimal": "10.00", "cost_uom": "ea"},
    ).status_code == 200
    assert client.post(
        "/app/stock_in",
        json={"item_id": item_id, "quantity_decimal": "1", "uom": "ea", "unit_cost_decimal": "1.00", "cost_uom": "ea"},
    ).status_code == 200
    assert client.post(
        "/app/finance/refund",
        json={
            "item_id": item_id,
            "refund_amount_cents": 100,
            "quantity_decimal": "1",
            "uom": "ea",
            "restock_inventory": True,
            "restock_unit_cost_decimal": "2.00",
            "restock_cost_uom": "ea",
        },
    ).status_code == 200

    assert calls.count("ledger") == 2
    assert calls.count("finance") == 1


def test_legacy_cost_fields_are_rejected(bus_client):
    client = bus_client["client"]
    item_id = _create_count_item(client, "LegacyCostFields", price=2.0)

    p1 = client.post(
        "/app/purchase",
        json={"item_id": item_id, "quantity_decimal": "1", "uom": "ea", "unit_cost_cents": 100},
    )
    assert p1.status_code in (400, 422), p1.text

    p2 = client.post(
        "/app/stock_in",
        json={"item_id": item_id, "quantity_decimal": "1", "uom": "ea", "unit_cost_cents": 100},
    )
    assert p2.status_code in (400, 422), p2.text

    p3 = client.post(
        "/app/finance/refund",
        json={
            "item_id": item_id,
            "refund_amount_cents": 100,
            "quantity_decimal": "1",
            "uom": "ea",
            "restock_inventory": True,
            "restock_unit_cost_cents": 100,
        },
    )
    assert p3.status_code in (400, 422), p3.text
