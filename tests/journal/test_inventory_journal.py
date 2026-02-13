# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

import json

import pytest

pytestmark = pytest.mark.api


@pytest.fixture()
def inventory_journal_setup(tmp_path, monkeypatch, request: pytest.FixtureRequest):
    journal_path = tmp_path / "journals" / "inventory.jsonl"
    monkeypatch.setenv("BUS_INVENTORY_JOURNAL", str(journal_path))
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
            "source_kind": "purchase",
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
    assert entry["batch_id"] == resp.json().get("batch_id")


def test_journal_failure_does_not_block_adjustment(inventory_journal_setup, monkeypatch):
    client = inventory_journal_setup["client"]
    engine = inventory_journal_setup["engine"]
    models = inventory_journal_setup["models"]
    journal_path = inventory_journal_setup["journal_path"]

    def boom(_entry):
        raise RuntimeError("fsync failed")

    monkeypatch.setattr("core.api.routes.ledger_api.append_inventory", boom)

    resp = client.post(
        "/app/adjust",
        json={"item_id": inventory_journal_setup["item_id"], "quantity_decimal": "2", "uom": "mc", "direction": "in"},
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
