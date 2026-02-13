# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.api


def _z(dt: datetime) -> str:
    return dt.replace(microsecond=0, tzinfo=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _create_item(client, name: str, price: float = 1.0) -> int:
    r = client.post("/app/items", json={"name": name, "dimension": "count", "uom": "ea", "price": price})
    assert r.status_code == 200, r.text
    payload = r.json()
    item = payload.get("item", payload)
    return int(item["id"])


def _purchase(client, item_id: int, qty_each: str, unit_cost_cents: int):
    r = client.post(
        "/app/purchase",
        json={
            "item_id": item_id,
            "quantity_decimal": qty_each,
            "uom": "ea",
            "unit_cost_cents": unit_cost_cents,
            "meta": {},
            "note": "seed",
        },
    )
    assert r.status_code == 200, r.text


def test_dashboard_returns_window_object(bus_client):
    r = bus_client["client"].get("/app/dashboard/summary")
    assert r.status_code == 200, r.text
    j = r.json()
    assert "window" in j
    assert j["window"]["start"].endswith("Z")
    assert j["window"]["end"].endswith("Z")


def test_dashboard_window_matches_half_open_bounds(bus_client):
    start = datetime(2025, 1, 1, 0, 0, 0)
    end = datetime(2025, 2, 1, 0, 0, 0)
    r = bus_client["client"].get(f"/app/dashboard/summary?start={start.isoformat()}Z&end={end.isoformat()}Z")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["window"]["start"] == _z(start)
    assert j["window"]["end"] == _z(end)


def test_finance_preset_priority_start_end_override_range(bus_client):
    now = datetime.utcnow().replace(microsecond=0)
    start = now - timedelta(days=2)
    end = now - timedelta(days=1)
    r = bus_client["client"].get(
        f"/app/finance/profit?start={start.isoformat()}Z&end={end.isoformat()}Z&range=7d"
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["window"]["start"] == _z(start)
    assert j["window"]["end"] == _z(end)


def test_finance_range_ytd_correct(bus_client):
    r = bus_client["client"].get("/app/finance/profit?range=ytd")
    assert r.status_code == 200, r.text
    j = r.json()
    year = datetime.utcnow().year
    assert j["window"]["start"] == f"{year}-01-01T00:00:00Z"


def test_finance_range_all_correct(bus_client):
    models = bus_client["models"]
    earliest = datetime(2024, 1, 2, 3, 4, 5)
    with bus_client["engine"].SessionLocal() as db:
        db.add(models.CashEvent(kind="sale", amount_cents=10, source_id="s1", created_at=earliest))
        db.add(models.CashEvent(kind="sale", amount_cents=20, source_id="s2", created_at=earliest + timedelta(days=2)))
        db.commit()

    r = bus_client["client"].get("/app/finance/profit?range=all")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["window"]["start"] == _z(earliest)


def test_manufacture_summary_cost_correct(bus_client):
    client = bus_client["client"]
    comp = _create_item(client, "Comp")
    out = _create_item(client, "Out")
    _purchase(client, comp, "2", 50)

    r = client.post(
        "/app/manufacturing/run",
        json={"output_item_id": out, "output_qty": 1000, "components": [{"item_id": comp, "qty_required": 1000}]},
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["produced_quantity"] == 1000
    assert j["total_batch_cost_cents"] == 50000
    assert j["cost_per_unit_cents"] == 50.0
    assert isinstance(j["run_id"], str)
    assert isinstance(j["movements"], list)


def test_manufacture_summary_rounding_precision(bus_client):
    client = bus_client["client"]
    comp = _create_item(client, "Comp2")
    out = _create_item(client, "Out2")
    _purchase(client, comp, "1", 1)

    r = client.post(
        "/app/manufacturing/run",
        json={"output_item_id": out, "output_qty": 3, "components": [{"item_id": comp, "qty_required": 1}]},
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["total_batch_cost_cents"] == 1
    assert j["cost_per_unit_cents"] == 0.3333


def test_manufacture_summary_zero_quantity_guard(bus_client):
    client = bus_client["client"]
    comp = _create_item(client, "Comp3")
    out = _create_item(client, "Out3")
    _purchase(client, comp, "1", 1)

    r = client.post(
        "/app/manufacturing/run",
        json={"output_item_id": out, "output_qty": 0.0001, "components": [{"item_id": comp, "qty_required": 1}]},
    )
    assert r.status_code in (200, 400)
    if r.status_code == 200:
        j = r.json()
        if int(j["produced_quantity"]) == 0:
            assert j["cost_per_unit_cents"] == 0.0


def test_item_summary_last_20_limit_sql_enforced(bus_client):
    client = bus_client["client"]
    item = _create_item(client, "SummaryItem")
    _purchase(client, item, "30", 5)

    for _ in range(25):
        r = client.post(
            "/app/stock/out",
            json={
                "item_id": item,
                "quantity_decimal": "1",
                "uom": "ea",
                "reason": "sold",
                "record_cash_event": False,
            },
        )
        assert r.status_code == 200, r.text

    resp = client.get(f"/app/items/{item}/summary")
    assert resp.status_code == 200, resp.text
    j = resp.json()
    assert len(j["last_20_movements"]) == 20


def test_item_summary_fifo_value_matches_dashboard_logic(bus_client):
    client = bus_client["client"]
    item = _create_item(client, "ValueMatch")
    _purchase(client, item, "2", 100)

    sr = client.get(f"/app/items/{item}/summary")
    dr = client.get("/app/dashboard/summary")
    assert sr.status_code == 200, sr.text
    assert dr.status_code == 200, dr.text

    assert int(sr.json()["inventory_value_cents"]) == int(dr.json()["inventory_value_cents"])
