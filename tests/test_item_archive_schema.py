# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations


from sqlalchemy import text


def test_item_archive_schema_default_and_column(bus_client):
    client = bus_client["client"]
    models = bus_client["models"]
    engine_module = bus_client["engine"]

    assert hasattr(models.Item, "is_archived")

    created = client.post(
        "/app/items",
        json={"name": "Archive Schema Item", "dimension": "count", "uom": "ea", "price": 1.0},
    )
    assert created.status_code == 200, created.text
    payload = created.json()
    item_obj = payload.get("item") if isinstance(payload, dict) else None
    if item_obj is None:
        item_obj = payload
    item_id = int(item_obj["id"])

    with engine_module.SessionLocal() as db:
        db_item = db.get(models.Item, item_id)
        assert db_item is not None
        assert bool(getattr(db_item, "is_archived")) is False

        rows = db.execute(text("PRAGMA table_info('items')")).fetchall()

    column_names = [str(r[1]) for r in rows]
    assert "is_archived" in column_names
