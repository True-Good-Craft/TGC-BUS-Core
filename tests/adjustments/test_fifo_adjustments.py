# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import importlib

import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.api


@pytest.fixture()
def ledger_setup(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest):
    monkeypatch.setenv("BUS_DEV", "1")
    env = request.getfixturevalue("bus_client")
    engine_module = env["engine"]
    models_module = env["models"]
    ledger_module = env["ledger"]
    ledger_api = importlib.import_module("core.api.routes.ledger_api")
    ledger_api = importlib.reload(ledger_api)

    with engine_module.SessionLocal() as db:
        item = models_module.Item(name="Adjusted", uom="ea", qty_stored=0)
        db.add(item)
        db.commit()
        item_id = item.id

    return {
        **env,
        "item_id": item_id,
        "ledger_api": ledger_api,
    }


def test_positive_adjustment_creates_new_batch(ledger_setup):
    client = ledger_setup["client"]
    engine = ledger_setup["engine"]
    models = ledger_setup["models"]

    resp = client.post(
        "/app/adjust",
        json={"item_id": ledger_setup["item_id"], "quantity_decimal": "5", "uom": "mc", "direction": "in", "note": "count"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True}

    with engine.SessionLocal() as db:
        batches = db.query(models.ItemBatch).all()
        assert len(batches) == 1
        batch = batches[0]
        assert batch.item_id == ledger_setup["item_id"]
        assert batch.qty_initial == pytest.approx(5)
        assert batch.qty_remaining == pytest.approx(5)
        assert batch.unit_cost_cents == 0
        assert batch.source_kind == "adjustment"
        assert batch.is_oversold is False

        moves = db.query(models.ItemMovement).all()
        assert len(moves) == 1
        mv = moves[0]
        assert mv.item_id == ledger_setup["item_id"]
        assert mv.batch_id == batch.id
        assert mv.qty_change == pytest.approx(5)
        assert mv.unit_cost_cents == 0
        assert mv.source_kind == "adjustment"
        assert mv.is_oversold is False


def test_negative_adjustment_fifo_consume_and_400_on_insufficient(ledger_setup):
    client = ledger_setup["client"]
    models = ledger_setup["models"]
    item_id = ledger_setup["item_id"]

    engine = ledger_setup["engine"]
    ledger = ledger_setup["ledger"]
    ledger_api = ledger_setup["ledger_api"]
    with engine.SessionLocal() as db:
        ledger.add_batch(db, item_id, 3, unit_cost_cents=100, source_kind="purchase", source_id=None)
        ledger.add_batch(db, item_id, 2, unit_cost_cents=50, source_kind="purchase", source_id=None)
        db.commit()
        resp = ledger_api.adjust_stock(
            ledger_api.AdjustmentInput(item_id=item_id, quantity_decimal="4", uom="mc", direction="out", note="shrink"),
            db,
        )

    assert resp == {"ok": True}

    with engine.SessionLocal() as db:
        batches = (
            db.query(models.ItemBatch)
            .filter(models.ItemBatch.item_id == item_id)
            .order_by(models.ItemBatch.created_at, models.ItemBatch.id)
            .all()
        )
        assert len(batches) == 2
        assert batches[0].qty_remaining == pytest.approx(0)
        assert batches[1].qty_remaining == pytest.approx(1)

        adjustments = db.query(models.ItemMovement).filter_by(source_kind="adjustment").all()
        assert len(adjustments) == 2
        qtys = sorted(mv.qty_change for mv in adjustments)
        assert qtys == [pytest.approx(-3), pytest.approx(-1)]
        costs = sorted(mv.unit_cost_cents for mv in adjustments)
        assert costs == [50, 100]
        assert all(mv.is_oversold is False for mv in adjustments)

    with engine.SessionLocal() as db:
        with pytest.raises(HTTPException) as excinfo:
            ledger_api.adjust_stock(
                ledger_api.AdjustmentInput(item_id=item_id, quantity_decimal="3", uom="mc", direction="out"),
                db,
            )
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == {
        "shortages": [
            {
                "item_id": item_id,
                "required": 3,
                "on_hand": 1,
                "missing": 2,
            }
        ]
    }

    with engine.SessionLocal() as db:
        batches = (
            db.query(models.ItemBatch)
            .filter(models.ItemBatch.item_id == item_id)
            .order_by(models.ItemBatch.created_at, models.ItemBatch.id)
            .all()
        )
        assert [b.qty_remaining for b in batches] == [pytest.approx(0), pytest.approx(1)]
        adjustments = db.query(models.ItemMovement).filter_by(source_kind="adjustment").count()
        assert adjustments == 2
