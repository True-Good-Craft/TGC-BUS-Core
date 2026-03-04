# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import pytest

pytestmark = pytest.mark.api


def _create_item(client, name: str) -> int:
    resp = client.post(
        "/app/items",
        json={"name": name, "dimension": "count", "uom": "ea", "price": 1.0},
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    item = payload.get("item") if isinstance(payload, dict) else None
    if item is None:
        item = payload
    return int(item["id"])


def test_items_listing_excludes_archived_unless_included(bus_client):
    client = bus_client["client"]
    models = bus_client["models"]
    engine_module = bus_client["engine"]

    active_item_id = _create_item(client, "Archive Listing Active")
    archived_item_id = _create_item(client, "Archive Listing Archived")

    with engine_module.SessionLocal() as db:
        archived_item = db.get(models.Item, archived_item_id)
        assert archived_item is not None
        archived_item.is_archived = True
        db.commit()

    default_list = client.get("/app/items")
    assert default_list.status_code == 200, default_list.text
    default_ids = {int(it["id"]) for it in default_list.json()}
    assert active_item_id in default_ids
    assert archived_item_id not in default_ids

    all_items = client.get("/app/items?include_archived=true")
    assert all_items.status_code == 200, all_items.text
    all_ids = {int(it["id"]) for it in all_items.json()}
    assert active_item_id in all_ids
    assert archived_item_id in all_ids
