# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from core.config.writes import set_writes_enabled


MODULES_TO_RESET = [
    "core.api.http",
    "core.api.routes.finance_api",
    "core.api.routes.ledger_api",
    "core.appdb.engine",
    "core.appdb.models",
    "core.appdb.models_recipes",
    "core.services.models",
]


@pytest.fixture()
def client_prod(tmp_path, monkeypatch):
    # Copied from tests/api/test_error_shapes.py (manufacturing_client_prod) pattern.
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("BUS_DB", str(db_path))

    for module_name in MODULES_TO_RESET:
        sys.modules.pop(module_name, None)

    import core.appdb.engine as engine_module
    import core.appdb.models as models_module
    import core.api.http as api_http

    engine_module = importlib.reload(engine_module)
    models_module = importlib.reload(models_module)
    api_http = importlib.reload(api_http)

    models_module.Base.metadata.create_all(bind=engine_module.ENGINE)

    set_writes_enabled(True)
    api_http.app.state.allow_writes = True

    client = TestClient(api_http.APP)

    # Auth cookie (copied pattern)
    session_token = api_http._load_or_create_token()
    api_http.app.state.app_state.tokens._rec.token = session_token
    client.headers.update({"Cookie": f"bus_session={session_token}"})

    yield client


def _create_count_item(client: TestClient, name: str, price: float = 2.50) -> int:
    r = client.post(
        "/app/items",
        json={"name": name, "dimension": "count", "uom": "ea", "price": price},
    )
    assert r.status_code == 200, r.text
    return int(r.json()["item"]["id"])


def _purchase_count_stock(client: TestClient, item_id: int, qty_each: str, unit_cost_cents: int):
    r = client.post(
        "/app/purchase",
        json={
            "item_id": int(item_id),
            "uom": "ea",
            "qty_uom": qty_each,
            "unit_cost_cents": int(unit_cost_cents),
            "meta": {},
            "note": "seed",
        },
    )
    assert r.status_code == 200, r.text


def test_sale_records_cash_event_and_links_source_id(client_prod: TestClient):
    item_id = _create_count_item(client_prod, "CountItem", price=2.50)
    _purchase_count_stock(client_prod, item_id, qty_each="10", unit_cost_cents=5)

    # Sell 2 ea = 2000 base units; unit price 300 cents => amount 600 cents
    r = client_prod.post(
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

    from core.appdb.engine import get_engine
    from sqlalchemy.orm import sessionmaker
    from core.appdb.models import CashEvent, ItemMovement

    SessionLocal = sessionmaker(bind=get_engine(), future=True)
    db = SessionLocal()
    try:
        ce = (
            db.query(CashEvent)
            .filter(CashEvent.kind == "sale")
            .order_by(CashEvent.id.desc())
            .first()
        )
        assert ce is not None
        assert int(ce.item_id) == int(item_id)
        assert int(ce.qty_base) == 2000
        assert int(ce.unit_price_cents) == 300
        assert int(ce.amount_cents) == 600
        assert ce.source_id

        moves = db.query(ItemMovement).filter(ItemMovement.source_id == ce.source_id).all()
        assert moves
        total_qty = sum(int(m.qty_change) for m in moves)
        assert total_qty == -2000
    finally:
        db.close()


def test_refund_requires_cost_when_restock_true_and_no_related_source_id(client_prod: TestClient):
    item_id = _create_count_item(client_prod, "RefundItem", price=1.00)

    r = client_prod.post(
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


def test_profit_window_exclusive_upper_bound(client_prod: TestClient):
    from core.appdb.engine import get_engine
    from sqlalchemy.orm import sessionmaker
    from core.appdb.models import CashEvent

    engine = get_engine()
    SessionLocal = sessionmaker(bind=engine, future=True)

    day = datetime.utcnow().date()
    from_dt = datetime(day.year, day.month, day.day, 0, 0, 0)
    next_dt = from_dt + timedelta(days=1)

    db = SessionLocal()
    try:
        db.add(
            CashEvent(
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
            CashEvent(
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
    pr = client_prod.get(f"/app/finance/profit?from={s}&to={s}")
    assert pr.status_code == 200, pr.text
    j = pr.json()
    assert int(j["gross_sales_cents"]) == 111
