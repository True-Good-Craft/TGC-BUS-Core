# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import csv
from datetime import datetime
from io import StringIO

import pytest

pytestmark = pytest.mark.api

EXPECTED_COLUMNS = [
    "date",
    "bus_event_id",
    "kind",
    "source_kind",
    "source_id",
    "description",
    "amount_cents",
    "amount",
    "currency",
    "category",
    "suggested_account",
    "item_id",
    "item_name",
    "quantity_decimal",
    "uom",
    "unit_amount_cents",
    "notes",
]


def _create_item(client, name: str) -> int:
    res = client.post("/app/items", json={"name": name, "dimension": "count", "uom": "ea", "price": 1.0})
    assert res.status_code == 200, res.text
    payload = res.json()
    item_obj = payload.get("item") if isinstance(payload, dict) else None
    if item_obj is None:
        item_obj = payload
    return int(item_obj["id"])


def _csv_rows(response):
    reader = csv.DictReader(StringIO(response.text))
    return reader.fieldnames, list(reader)


def test_finance_export_csv_contains_traceable_purchase_row(bus_client):
    client = bus_client["client"]
    item_id = _create_item(client, "CSV Purchase Item")

    purchase = client.post(
        "/app/purchase",
        json={"item_id": item_id, "quantity_decimal": "2", "uom": "ea", "unit_cost_cents": 500},
    )
    assert purchase.status_code == 200, purchase.text
    source_id = purchase.json()["source_id"]

    response = client.get("/app/finance/export.csv?profile=generic")
    assert response.status_code == 200, response.text
    assert "text/csv" in response.headers["content-type"]
    assert "BUS-Core-Finance-Export" in response.headers["content-disposition"]

    headers, rows = _csv_rows(response)
    assert headers == EXPECTED_COLUMNS
    purchase_row = next(row for row in rows if row["kind"] == "purchase" and row["source_id"] == source_id)

    assert purchase_row["bus_event_id"].startswith("cash_event:")
    assert int(purchase_row["amount_cents"]) < 0
    assert purchase_row["amount"] == "-10.00"
    assert purchase_row["currency"] == "CAD"


def test_finance_export_rejects_unsupported_profile(bus_client):
    response = bus_client["client"].get("/app/finance/export.csv?profile=qbo")

    assert response.status_code == 400, response.text
    assert response.json()["detail"]["error"] == "unsupported_export_profile"
    assert response.json()["detail"]["profile"] == "qbo"


def test_finance_export_date_filter(bus_client):
    client = bus_client["client"]
    models = bus_client["models"]
    engine_module = bus_client["engine"]

    with engine_module.SessionLocal() as db:
        db.add(
            models.CashEvent(
                kind="expense",
                amount_cents=-111,
                source_kind="expense",
                source_id="outside-window",
                created_at=datetime(2026, 3, 1, 9, 0, 0),
            )
        )
        db.add(
            models.CashEvent(
                kind="expense",
                amount_cents=-222,
                source_kind="expense",
                source_id="inside-window",
                created_at=datetime(2026, 3, 2, 9, 0, 0),
            )
        )
        db.commit()

    response = client.get("/app/finance/export.csv?from=2026-03-02&to=2026-03-02")
    assert response.status_code == 200, response.text
    _, rows = _csv_rows(response)

    assert [row["source_id"] for row in rows] == ["inside-window"]
    assert rows[0]["date"] == "2026-03-02"


def test_finance_export_quotes_csv_fields(bus_client):
    client = bus_client["client"]
    notes = "needs, review\nsecond line"

    expense = client.post(
        "/app/finance/expense",
        json={
            "amount_cents": 1234,
            "category": "ops",
            "notes": notes,
            "created_at": "2026-04-01T09:00:00",
        },
    )
    assert expense.status_code == 200, expense.text

    response = client.get("/app/finance/export.csv?from=2026-04-01&to=2026-04-01")
    assert response.status_code == 200, response.text
    _, rows = _csv_rows(response)

    assert len(rows) == 1
    assert rows[0]["kind"] == "expense"
    assert rows[0]["notes"] == notes
