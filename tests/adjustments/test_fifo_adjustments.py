# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import importlib
import sys

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from core.api.routes.ledger_api import AdjustmentInput, adjust_stock


@pytest.fixture()
def ledger_setup(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    monkeypatch.setenv("BUS_DB", str(db_path))
    monkeypatch.setenv("BUS_DEV", "1")

    for module_name in [
        "core.api.http",
        "core.api.routes.ledger_api",
        "core.appdb.engine",
        "core.appdb.ledger",
        "core.appdb.models",
        "core.services.models",
    ]:
        sys.modules.pop(module_name, None)

    import core.appdb.engine as engine_module
    import core.appdb.ledger as ledger_module
    import core.appdb.models as models_module
    import core.api.http as api_http
    import core.services.models as services_models

    engine_module = importlib.reload(engine_module)
    ledger_module = importlib.reload(ledger_module)
    models_module = importlib.reload(models_module)
    api_http = importlib.reload(api_http)
    services_models = importlib.reload(services_models)

    from tgc.settings import Settings
    from tgc.state import init_state

    api_http.app.state.app_state = init_state(Settings())
    api_http.app.state.allow_writes = True

    engine = engine_module.get_engine()
    models_module.Base.metadata.create_all(bind=engine)

    from core.config.writes import set_writes_enabled

    set_writes_enabled(True)

    client = TestClient(api_http.APP)
    session_token = api_http._load_or_create_token()
    api_http.app.state.app_state.tokens._rec.token = session_token
    client.headers.update({"Cookie": f"bus_session={session_token}"})

    with engine_module.SessionLocal() as db:
        item = models_module.Item(name="Adjusted", uom="ea", qty_stored=0)
        db.add(item)
        db.commit()
        item_id = item.id

    yield {
        "client": client,
        "engine": engine_module,
        "models": models_module,
        "ledger": ledger_module,
        "item_id": item_id,
    }


def test_positive_adjustment_creates_new_batch(ledger_setup):
    client = ledger_setup["client"]
    engine = ledger_setup["engine"]
    models = ledger_setup["models"]

    resp = client.post(
        "/app/adjust",
        json={"item_id": ledger_setup["item_id"], "qty_change": 5, "note": "count"},
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
    with engine.SessionLocal() as db:
        ledger.add_batch(db, item_id, 3, unit_cost_cents=100, source_kind="purchase", source_id=None)
        ledger.add_batch(db, item_id, 2, unit_cost_cents=50, source_kind="purchase", source_id=None)
        db.commit()
        resp = adjust_stock(AdjustmentInput(item_id=item_id, qty_change=-4, note="shrink"), db)

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
            adjust_stock(AdjustmentInput(item_id=item_id, qty_change=-3), db)
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
