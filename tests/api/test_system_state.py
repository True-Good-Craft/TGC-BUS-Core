# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from sqlalchemy.orm import Session


def test_system_state_is_first_run_on_empty_db(bus_client):
    client = bus_client["client"]

    response = client.get("/app/system/state")
    assert response.status_code == 200

    payload = response.json()
    assert payload["is_first_run"] is True
    assert payload["status"] == "empty"
    assert payload["demo_allowed"] is True
    assert payload["basis"] == []
    assert "build" in payload
    assert payload["counts"] == {
        "items": 0,
        "vendors": 0,
        "recipes": 0,
        "movements": 0,
        "cash_events": 0,
        "manufacturing_runs": 0,
    }


def test_system_state_not_first_run_after_item_created(bus_client):
    client = bus_client["client"]
    models = bus_client["models"]
    engine = bus_client["engine"]

    with engine.SessionLocal(bind=engine.get_engine()) as session:
        session.add(models.Item(name="Starter item", dimension="count", uom="ea", qty_stored=0))
        session.commit()

    response = client.get("/app/system/state")
    assert response.status_code == 200

    payload = response.json()
    assert payload["is_first_run"] is False
    assert payload["demo_allowed"] is False
    assert payload["counts"]["items"] == 1
    assert "items" in payload["basis"]


def test_system_state_vendor_basis_and_order(bus_client):
    client = bus_client["client"]
    models = bus_client["models"]
    engine = bus_client["engine"]

    with engine.SessionLocal(bind=engine.get_engine()) as session:
        session.add(models.Vendor(name="Vendor One"))
        session.commit()

    response = client.get("/app/system/state")
    assert response.status_code == 200

    payload = response.json()
    assert payload["is_first_run"] is False
    assert payload["status"] == "needs_migration"
    assert "vendors" in payload["basis"]
    assert all(isinstance(value, int) for value in payload["counts"].values())
    assert list(payload["counts"].keys()) == [
        "items",
        "vendors",
        "recipes",
        "movements",
        "cash_events",
        "manufacturing_runs",
    ]


def test_system_state_db_failure_returns_stable_500(bus_client, monkeypatch):
    client = bus_client["client"]

    def _boom(*_args, **_kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(Session, "query", _boom)

    response = client.get("/app/system/state")
    assert response.status_code == 500
    assert response.json() == {
        "detail": {
            "error": "bad_request",
            "message": "system_state_unavailable",
        }
    }


def test_system_state_build_metadata_fields_are_strings(bus_client):
    client = bus_client["client"]

    response = client.get("/app/system/state")
    assert response.status_code == 200

    payload = response.json()
    assert "build" in payload
    assert isinstance(payload["build"].get("version"), str)
    assert isinstance(payload["build"].get("schema_version"), str)


def test_system_state_status_ready_when_schema_version_is_not_baseline(bus_client, monkeypatch):
    client = bus_client["client"]
    models = bus_client["models"]
    engine = bus_client["engine"]
    original_execute = Session.execute

    with engine.SessionLocal(bind=engine.get_engine()) as session:
        session.add(models.Vendor(name="Vendor Ready"))
        session.commit()

    class _FakeRow:
        def __init__(self, values):
            self._values = values

        def __getitem__(self, idx):
            return self._values[idx]

    class _FakeResult:
        def __init__(self, row):
            self._row = row

        def fetchone(self):
            return self._row

    def _execute(self, statement, *args, **kwargs):
        sql = str(statement)
        if "sqlite_master" in sql:
            return _FakeResult(_FakeRow(("alembic_version",)))
        if "SELECT version_num FROM alembic_version" in sql:
            return _FakeResult(_FakeRow(("2026_01",)))
        return original_execute(self, statement, *args, **kwargs)

    monkeypatch.setattr(Session, "execute", _execute)

    response = client.get("/app/system/state")
    assert response.status_code == 200
    payload = response.json()
    assert payload["build"]["schema_version"] == "2026_01"
    assert payload["status"] == "ready"
