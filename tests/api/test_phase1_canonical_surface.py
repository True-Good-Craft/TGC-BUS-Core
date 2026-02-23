from __future__ import annotations

from pathlib import Path


def test_canonical_endpoints_exist(bus_client):
    app = bus_client["api_http"].APP
    routes = {
        (m, r.path)
        for r in app.routes
        for m in getattr(r, "methods", set())
        if m not in {"HEAD", "OPTIONS"}
    }
    targets = {
        ("POST", "/app/stock/in"),
        ("POST", "/app/stock/out"),
        ("POST", "/app/purchase"),
        ("GET", "/app/ledger/history"),
        ("POST", "/app/manufacture"),
    }
    assert targets.issubset(routes)


def test_legacy_wrappers_emit_deprecation_header(bus_client, monkeypatch):
    client = bus_client["client"]

    movements = client.get("/app/ledger/movements")
    assert dict(movements.headers).get("x-bus-deprecation") == "/app/ledger/history"

    import core.api.routes.manufacturing as manufacturing_routes

    async def _fake_canonical(**_kwargs):
        return {"ok": True}

    monkeypatch.setattr(manufacturing_routes, "canonical_manufacture", _fake_canonical)
    run_resp = client.post("/app/manufacturing/run", json={"quantity_decimal": "1", "uom": "ea", "recipe_id": 1})
    assert dict(run_resp.headers).get("x-bus-deprecation") == "/app/manufacture"


def test_manufacture_rejects_legacy_quantity_key(bus_client):
    client = bus_client["client"]
    resp = client.post("/app/manufacture", json={"quantity": "1", "uom": "ea", "recipe_id": 1})
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "legacy_quantity_keys_forbidden"
    assert "quantity" in resp.json()["detail"]["keys"]


def test_ledger_purchase_wrapper_defaults_uom_for_non_count_item(bus_client):
    client = bus_client["client"]
    engine = bus_client["engine"]
    models = bus_client["models"]

    with engine.SessionLocal() as db:
        item = models.Item(name="Flour", uom="kg", dimension="weight", qty_stored=0)
        db.add(item)
        db.commit()
        item_id = int(item.id)

    resp = client.post(
        "/app/ledger/purchase",
        json={"item_id": item_id, "qty": 2, "unit_cost_cents": 500, "source_id": "po-weight"},
    )
    assert resp.status_code == 200, resp.text
    assert dict(resp.headers).get("x-bus-deprecation") == "/app/purchase"


def test_canonical_stock_endpoints_invalid_uom_400(bus_client):
    client = bus_client["client"]
    engine = bus_client["engine"]
    models = bus_client["models"]

    with engine.SessionLocal() as db:
        item = models.Item(name="Salt", uom="g", dimension="weight", qty_stored=0)
        db.add(item)
        db.commit()
        item_id = int(item.id)

    resp = client.post(
        "/app/stock/in",
        json={"item_id": item_id, "quantity_decimal": "1", "uom": "nope", "unit_cost_cents": 10},
    )
    assert resp.status_code == 400


def test_route_modules_forbid_mutation_primitives():
    route_dir = Path("core/api/routes")
    bad_tokens = ("add_batch", "fifo_consume", "append_inventory")
    offenders = []
    for py_file in route_dir.glob("*.py"):
        text = py_file.read_text(encoding="utf-8", errors="replace")
        for token in bad_tokens:
            if token in text:
                offenders.append(f"{py_file}:{token}")
    assert not offenders, f"Forbidden mutation primitives found: {offenders}"
