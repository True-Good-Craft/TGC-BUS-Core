# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import pytest

pytestmark = pytest.mark.api


def _create_item(client, name: str) -> int:
    resp = client.post(
        "/app/items",
        json={"name": name, "dimension": "count", "uom": "ea", "price": 2.5},
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    item = payload.get("item") if isinstance(payload, dict) else None
    if item is None:
        item = payload
    return int(item["id"])


def _create_history_for_item(client, item_id: int, source_id: str):
    purchase = client.post(
        "/app/purchase",
        json={
            "item_id": item_id,
            "quantity_decimal": "1000",
            "uom": "mc",
            "unit_cost_cents": 10,
            "source_id": source_id,
        },
    )
    assert purchase.status_code == 200, purchase.text


def test_delete_item_archives_when_history_exists(bus_client):
    client = bus_client["client"]
    item_id = _create_item(client, "Delete Guard History")
    _create_history_for_item(client, item_id, "delete-guard-history")

    resp = client.delete(f"/app/items/{item_id}")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"archived": True}

    default_list = client.get("/app/items")
    assert default_list.status_code == 200, default_list.text
    default_ids = {int(it["id"]) for it in default_list.json()}
    assert item_id not in default_ids

    with_archived = client.get("/app/items?include_archived=true")
    assert with_archived.status_code == 200, with_archived.text
    archived_ids = {int(it["id"]) for it in with_archived.json()}
    assert item_id in archived_ids

    get_item = client.get(f"/app/items/{item_id}")
    assert get_item.status_code == 200, get_item.text
    assert int(get_item.json()["id"]) == item_id


def test_delete_archived_item_idempotent(bus_client):
    client = bus_client["client"]
    item_id = _create_item(client, "Delete Guard Idempotent")
    _create_history_for_item(client, item_id, "delete-guard-idempotent")

    first = client.delete(f"/app/items/{item_id}")
    assert first.status_code == 200, first.text
    assert first.json() == {"archived": True}

    second = client.delete(f"/app/items/{item_id}")
    assert second.status_code == 200, second.text
    assert second.json() == {"archived": True}

    get_item = client.get(f"/app/items/{item_id}")
    assert get_item.status_code == 200, get_item.text
    assert int(get_item.json()["id"]) == item_id


def test_delete_item_allowed_when_no_history(bus_client):
    client = bus_client["client"]
    item_id = _create_item(client, "Delete Guard No History")

    resp = client.delete(f"/app/items/{item_id}")
    assert resp.status_code == 200, resp.text

    get_item = client.get(f"/app/items/{item_id}")
    assert get_item.status_code == 404
