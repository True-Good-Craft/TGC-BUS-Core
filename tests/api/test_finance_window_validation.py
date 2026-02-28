# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import pytest

pytestmark = pytest.mark.api


def test_finance_read_window_validation(bus_client):
    client = bus_client["client"]

    bad_range = client.get("/app/finance/transactions?from=2026-01-02&to=2026-01-01&limit=10")
    assert bad_range.status_code == 400, bad_range.text
    assert bad_range.json() == {"detail": "invalid_date_range"}

    bad_format = client.get("/app/finance/transactions?from=not-a-date&to=2026-01-01&limit=10")
    assert bad_format.status_code == 400, bad_format.text
    assert bad_format.json() == {"detail": "invalid_date_format"}

    empty_ok = client.get("/app/finance/transactions?from=2026-01-01&to=2026-01-01&limit=10")
    assert empty_ok.status_code == 200, empty_ok.text
    payload = empty_ok.json()
    assert set(payload.keys()) == {"from", "to", "limit", "count", "transactions"}
    assert payload["from"] == "2026-01-01"
    assert payload["to"] == "2026-01-01"
    assert payload["limit"] == 10
    assert payload["count"] == 0
    assert payload["transactions"] == []


def test_finance_summary_window_validation(bus_client):
    client = bus_client["client"]

    bad_range = client.get("/app/finance/summary?from=2026-01-02&to=2026-01-01")
    assert bad_range.status_code == 400, bad_range.text
    assert bad_range.json() == {"detail": "invalid_date_range"}

    bad_format = client.get("/app/finance/summary?from=not-a-date&to=2026-01-01")
    assert bad_format.status_code == 400, bad_format.text
    assert bad_format.json() == {"detail": "invalid_date_format"}

    empty_ok = client.get("/app/finance/summary?from=2026-01-01&to=2026-01-01")
    assert empty_ok.status_code == 200, empty_ok.text
    payload = empty_ok.json()
    expected_keys = {
        "gross_sales_cents",
        "returns_cents",
        "net_sales_cents",
        "cogs_cents",
        "gross_profit_cents",
        "expenses_cents",
        "net_profit_cents",
        "runs_count",
        "units_produced",
        "units_sold",
        "from",
        "to",
    }
    assert set(payload.keys()) == expected_keys
    assert payload["units_produced"] == []
    assert payload["units_sold"] == []
