# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

import json

import pytest

pytestmark = pytest.mark.api


def _create_count_item(client, name: str) -> int:
    r = client.post(
        "/app/items",
        json={"name": name, "dimension": "count", "uom": "ea", "price": 2.50},
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    item = payload.get("item") if isinstance(payload, dict) else None
    if item is None and isinstance(payload, dict) and "id" in payload:
        item = payload
    assert item is not None
    return int(item["id"])


def _install_test_journal(monkeypatch, journal_path):
    import json

    def _write(entry):
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        with open(journal_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    monkeypatch.setattr("core.services.stock_mutation.append_inventory", _write)
    monkeypatch.setattr("core.api.http.append_inventory", _write)



@pytest.fixture()
def inventory_journal_setup(tmp_path, monkeypatch, request: pytest.FixtureRequest):
    journal_path = tmp_path / "journals" / "inventory.jsonl"
    monkeypatch.setenv("BUS_INVENTORY_JOURNAL", str(journal_path))
    _install_test_journal(monkeypatch, journal_path)
    env = request.getfixturevalue("bus_client")
    engine_module = env["engine"]
    models_module = env["models"]

    with engine_module.SessionLocal() as db:
        item = models_module.Item(name="Widget", uom="ea", qty_stored=0)
        db.add(item)
        db.commit()
        item_id = item.id

    return {
        **env,
        "journal_path": journal_path,
        "item_id": item_id,
    }


def test_purchase_appends_journal(inventory_journal_setup):
    client = inventory_journal_setup["client"]
    engine = inventory_journal_setup["engine"]
    models = inventory_journal_setup["models"]
    journal_path = inventory_journal_setup["journal_path"]

    resp = client.post(
        "/app/purchase",
        json={
            "item_id": inventory_journal_setup["item_id"],
            "quantity_decimal": "3",
            "uom": "mc",
            "unit_cost_cents": 125,
            "source_id": "po-1",
        },
    )

    assert resp.status_code == 200, resp.text
    assert resp.json().get("ok") is True

    with engine.SessionLocal() as db:
        batches = db.query(models.ItemBatch).all()
        assert len(batches) == 1
        assert batches[0].qty_initial == pytest.approx(3)
        item = db.get(models.Item, inventory_journal_setup["item_id"])
        assert item is not None
        assert item.qty_stored == pytest.approx(3)

    assert journal_path.exists()
    lines = journal_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["op"] == "purchase"
    assert entry["qty"] == pytest.approx(3)
    assert entry["unit_cost_cents"] == 125
    assert entry["item_id"] == inventory_journal_setup["item_id"]
    batch_ids = resp.json().get("batch_ids")
    assert batch_ids
    assert len(batch_ids) == 1
    assert entry["batch_id"] == batch_ids[0]


def test_journal_failure_does_not_block_adjustment(inventory_journal_setup, monkeypatch):
    client = inventory_journal_setup["client"]
    engine = inventory_journal_setup["engine"]
    models = inventory_journal_setup["models"]
    journal_path = inventory_journal_setup["journal_path"]

    def boom(_entry):
        raise RuntimeError("fsync failed")

    monkeypatch.setattr("core.services.stock_mutation.append_inventory", boom)
    monkeypatch.setattr("core.api.http.append_inventory", boom)

    resp = client.post(
        "/app/adjust",
        json={"item_id": inventory_journal_setup["item_id"], "qty_change": 2},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True}

    with engine.SessionLocal() as db:
        batches = db.query(models.ItemBatch).all()
        assert len(batches) == 1
        assert batches[0].qty_initial == pytest.approx(2)
        assert batches[0].qty_remaining == pytest.approx(2)

    # Journal write failed but DB state is still committed
    assert not journal_path.exists()


def test_stock_out_sold_without_ref_uses_generated_source_id_across_surfaces(bus_client, monkeypatch, tmp_path):
    client = bus_client["client"]
    engine = bus_client["engine"]
    models = bus_client["models"]
    journal_path = tmp_path / "journals" / "inventory.jsonl"
    _install_test_journal(monkeypatch, journal_path)

    item_id = _create_count_item(client, "SoldNoRef")
    seed = client.post(
        "/app/purchase",
        json={"item_id": item_id, "quantity_decimal": "10", "uom": "ea", "unit_cost_cents": 50, "source_id": "seed-no-ref"},
    )
    assert seed.status_code == 200, seed.text

    sold = client.post(
        "/app/stock/out",
        json={"item_id": item_id, "quantity_decimal": "2", "uom": "ea", "reason": "sold", "record_cash_event": True, "sell_unit_price_cents": 300},
    )
    assert sold.status_code == 200, sold.text
    sold_payload = sold.json()
    assert sold_payload.get("ok") is True

    with engine.SessionLocal() as db:
        ce = (
            db.query(models.CashEvent)
            .filter(models.CashEvent.kind == "sale", models.CashEvent.item_id == item_id)
            .order_by(models.CashEvent.id.desc())
            .first()
        )
        assert ce is not None
        assert ce.source_id
        moves = db.query(models.ItemMovement).filter(models.ItemMovement.source_id == ce.source_id).all()
        assert moves

    line_source_ids = {line["source_id"] for line in sold_payload["lines"]}
    assert line_source_ids == {ce.source_id}

    entries = [json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines()]
    sold_entries = [entry for entry in entries if entry.get("op") == "sold" and int(entry.get("item_id")) == item_id]
    assert sold_entries
    assert sold_entries[-1]["source_id"] == ce.source_id


def test_stock_out_sold_with_ref_uses_provided_source_id_across_surfaces(bus_client, monkeypatch, tmp_path):
    client = bus_client["client"]
    engine = bus_client["engine"]
    models = bus_client["models"]
    journal_path = tmp_path / "journals" / "inventory.jsonl"
    _install_test_journal(monkeypatch, journal_path)

    item_id = _create_count_item(client, "SoldWithRef")
    provided_source_id = "sold-correlation-ref-1"
    seed = client.post(
        "/app/purchase",
        json={"item_id": item_id, "quantity_decimal": "10", "uom": "ea", "unit_cost_cents": 50, "source_id": "seed-with-ref"},
    )
    assert seed.status_code == 200, seed.text

    sold = client.post(
        "/app/stock/out",
        json={
            "item_id": item_id,
            "quantity_decimal": "2",
            "uom": "ea",
            "reason": "sold",
            "note": provided_source_id,
            "record_cash_event": True,
            "sell_unit_price_cents": 300,
        },
    )
    assert sold.status_code == 200, sold.text
    sold_payload = sold.json()
    assert sold_payload.get("ok") is True

    with engine.SessionLocal() as db:
        ce = (
            db.query(models.CashEvent)
            .filter(models.CashEvent.kind == "sale", models.CashEvent.item_id == item_id)
            .order_by(models.CashEvent.id.desc())
            .first()
        )
        assert ce is not None
        assert ce.source_id == provided_source_id
        moves = db.query(models.ItemMovement).filter(models.ItemMovement.source_id == provided_source_id).all()
        assert moves

    line_source_ids = {line["source_id"] for line in sold_payload["lines"]}
    assert line_source_ids == {provided_source_id}

    entries = [json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines()]
    sold_entries = [entry for entry in entries if entry.get("op") == "sold" and int(entry.get("item_id")) == item_id]
    assert sold_entries
    assert sold_entries[-1]["source_id"] == provided_source_id
