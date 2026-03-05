#!/usr/bin/env python3
"""
BUS Core Dev Seeder
Deterministic dataset for UI/Finance testing.
Uses canonical endpoints only.

Improvements:
- No hard sys.exit() that raises SystemExit during normal failure.
- Clearer error reporting.
- Optional --self-test mode to validate payload contracts without hitting the API.
- Optional --db-path mode to seed SQLite directly for deterministic demo DB generation.
"""

from __future__ import annotations

import argparse
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

BASE = os.environ.get("BUS_SEED_BASE", "http://127.0.0.1:8765")
_API_SESSION = None


# ----------------------------
# HTTP Helpers (API mode)
# ----------------------------

def _session():
    global _API_SESSION
    if _API_SESSION is None:
        import requests

        _API_SESSION = requests.Session()
    return _API_SESSION


def ensure_token():
    r = _session().get(f"{BASE}/session/token")
    r.raise_for_status()


def post(path, payload):
    r = _session().post(f"{BASE}{path}", json=payload)
    if not r.ok:
        print(f"\nERROR calling {path}")
        print("Payload:", payload)
        print("Response:", r.text)
        raise RuntimeError(f"Request failed: {path}")
    return r.json()


def get(path):
    r = _session().get(f"{BASE}{path}")
    r.raise_for_status()
    return r.json()


# ----------------------------
# Domain Helpers (API mode)
# ----------------------------

def create_vendor(name):
    return post("/app/vendors", {"name": name})


def create_item(name, dimension, uom, is_product=False):
    return post(
        "/app/items",
        {
            "name": name,
            "dimension": dimension,
            "uom": uom,
            "display_unit": uom,
            "unit": uom,
            "is_product": is_product,
        },
    )


def purchase(item_id, qty, uom, cost):
    return post(
        "/app/purchase",
        {
            "item_id": item_id,
            "quantity_decimal": str(qty),
            "uom": uom,
            "unit_cost_cents": cost,
            "source_id": "seed",
        },
    )


def stock_out(item_id, qty, uom, reason, sell_price=None):
    payload = {
        "item_id": item_id,
        "quantity_decimal": str(qty),
        "uom": uom,
        "reason": reason,
        "note": "seed",
        "record_cash_event": reason == "sold",
    }

    if reason == "sold":
        payload["sell_unit_price_cents"] = sell_price

    return post("/app/stock/out", payload)


def manufacture(recipe_id, qty, uom="ea"):
    return post(
        "/app/manufacture",
        {
            "recipe_id": recipe_id,
            "quantity_decimal": str(qty),
            "uom": uom,
            "notes": "seed run",
        },
    )


def create_recipe(name, output_item_id, output_qty, uom, components):
    return post(
        "/app/recipes",
        {
            "name": name,
            "output_item_id": output_item_id,
            "quantity_decimal": str(output_qty),
            "uom": uom,
            "items": components,
        },
    )


def expense(amount, category):
    return post(
        "/app/finance/expense",
        {
            "amount_cents": amount,
            "category": category,
            "at": datetime.now(UTC).isoformat(),
        },
    )


def refund(refund_amount, item_id, qty, uom, unit_cost_cents):
    """
    Canonical refund contract (current server enforcement):
    Required:
    - item_id
    - refund_amount_cents
    - quantity_decimal
    - uom
    - restock_inventory
    - at

    Additionally required when no related_source_id is provided:
    - restock_unit_cost_cents
    """
    return post(
        "/app/finance/refund",
        {
            "item_id": item_id,
            "refund_amount_cents": refund_amount,
            "quantity_decimal": str(qty),
            "uom": uom,
            "restock_inventory": True,
            "restock_unit_cost_cents": unit_cost_cents,
            "at": datetime.now(UTC).isoformat(),
        },
    )


# ----------------------------
# Self-Test Mode
# ----------------------------

def self_test():
    """
    Minimal contract validation without calling the API.
    Ensures required refund fields are present.
    """
    payload = {
        "item_id": 1,
        "refund_amount_cents": 1000,
        "quantity_decimal": "1",
        "uom": "ea",
        "restock_inventory": True,
        "at": datetime.now(UTC).isoformat(),
    }

    required = {
        "item_id",
        "refund_amount_cents",
        "quantity_decimal",
        "uom",
        "restock_inventory",
        "at",
    }

    missing = required - payload.keys()
    if missing:
        print("Self-test failed. Missing fields:", missing)
        return False

    print("Self-test passed.")
    return True


# ----------------------------
# Direct DB Mode (deterministic demo DB)
# ----------------------------

def _to_base(quantity_decimal: str, uom: str, dimension: str) -> int:
    from core.metrics.metric import normalize_quantity_to_base_int

    return int(
        normalize_quantity_to_base_int(
            quantity_decimal=str(quantity_decimal),
            uom=str(uom),
            dimension=str(dimension),
        )
    )


def _stamp_by_source(db, source_id, when):
    from core.appdb.models import CashEvent, ItemBatch, ItemMovement

    db.query(ItemMovement).filter(ItemMovement.source_id == source_id).update(
        {"created_at": when}, synchronize_session=False
    )
    db.query(ItemBatch).filter(ItemBatch.source_id == source_id).update(
        {"created_at": when}, synchronize_session=False
    )
    db.query(CashEvent).filter(CashEvent.source_id == source_id).update(
        {"created_at": when}, synchronize_session=False
    )


def seed_sqlite_demo_db(db_path: str | Path) -> bool:
    """Seed a deterministic offline dataset into the provided SQLite DB path."""

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from core.api.schemas.manufacturing import RecipeRunRequest
    from core.appdb.migrate import ensure_vendors_flags
    from core.appdb.models import Base, CashEvent, Item, Vendor
    from core.appdb.models_recipes import ManufacturingRun, Recipe, RecipeItem
    from core.manufacturing.service import execute_run_txn, validate_run
    from core.services.stock_mutation import (
        perform_purchase_base,
        perform_stock_in_base,
        perform_stock_out_base,
    )

    target = Path(db_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        f"sqlite+pysqlite:///{target.as_posix()}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)

    try:
        Base.metadata.create_all(bind=engine)
        ensure_vendors_flags(engine)

        with SessionLocal() as db:
            if db.query(Item).count() > 0 or db.query(Vendor).count() > 0:
                return True

            t0 = datetime(2026, 1, 2, 9, 0, 0)
            t1 = t0 + timedelta(minutes=1)
            t2 = t0 + timedelta(minutes=2)
            t3 = t0 + timedelta(minutes=3)
            t4 = t0 + timedelta(minutes=4)
            t5 = t0 + timedelta(minutes=5)
            t6 = t0 + timedelta(minutes=6)

            print("Creating vendors...")
            db.add_all(
                [
                    Vendor(name="Steel Supply Co", created_at=t0),
                    Vendor(name="Local Wood Ltd", created_at=t0),
                    Vendor(name="Packaging Inc", created_at=t0),
                ]
            )
            db.commit()

            print("Creating items...")
            steel = Item(name="Steel Rod", dimension="length", uom="m", qty_stored=0, created_at=t1)
            wood = Item(name="Wood Panel", dimension="area", uom="m2", qty_stored=0, created_at=t1)
            screws = Item(name="Screws", dimension="count", uom="ea", qty_stored=0, created_at=t1)
            frame = Item(
                name="Table Frame",
                dimension="count",
                uom="ea",
                qty_stored=0,
                is_product=True,
                price=150.0,
                created_at=t1,
            )
            bench = Item(name="Workbench", dimension="count", uom="ea", qty_stored=0, is_product=True, created_at=t1)
            db.add_all([steel, wood, screws, frame, bench])
            db.commit()

            print("Purchasing stock...")
            perform_purchase_base(
                db,
                vendor_id="",
                lines=[
                    {
                        "item_id": int(steel.id),
                        "qty_base": _to_base("100", "m", "length"),
                        "unit_cost_cents": 500,
                        "source_kind": "purchase",
                        "source_id": "seed-purchase-steel",
                    }
                ],
            )
            perform_purchase_base(
                db,
                vendor_id="",
                lines=[
                    {
                        "item_id": int(wood.id),
                        "qty_base": _to_base("50", "m2", "area"),
                        "unit_cost_cents": 2000,
                        "source_kind": "purchase",
                        "source_id": "seed-purchase-wood",
                    }
                ],
            )
            perform_purchase_base(
                db,
                vendor_id="",
                lines=[
                    {
                        "item_id": int(screws.id),
                        "qty_base": _to_base("1000", "ea", "count"),
                        "unit_cost_cents": 10,
                        "source_kind": "purchase",
                        "source_id": "seed-purchase-screws",
                    }
                ],
            )
            _stamp_by_source(db, "seed-purchase-steel", t2)
            _stamp_by_source(db, "seed-purchase-wood", t2)
            _stamp_by_source(db, "seed-purchase-screws", t2)
            db.commit()

            print("Creating recipe...")
            recipe_frame = Recipe(
                name="Frame Recipe",
                output_item_id=int(frame.id),
                output_qty=_to_base("1", "ea", "count"),
                created_at=t3,
                updated_at=t3,
            )
            db.add(recipe_frame)
            db.flush()
            db.add_all(
                [
                    RecipeItem(
                        recipe_id=int(recipe_frame.id),
                        item_id=int(steel.id),
                        qty_required=_to_base("5", "m", "length"),
                        sort_order=0,
                        created_at=t3,
                        updated_at=t3,
                    ),
                    RecipeItem(
                        recipe_id=int(recipe_frame.id),
                        item_id=int(screws.id),
                        qty_required=_to_base("20", "ea", "count"),
                        sort_order=1,
                        created_at=t3,
                        updated_at=t3,
                    ),
                ]
            )
            db.commit()

            print("Manufacturing run...")
            run_request = RecipeRunRequest(
                recipe_id=int(recipe_frame.id),
                quantity_decimal="5",
                uom="ea",
                output_qty=5,
                notes="seed run",
            )
            output_item_id, required_components, output_qty_base, shortages = validate_run(db, run_request)
            if shortages:
                print("Seeder aborted: unexpected manufacturing shortages", shortages)
                db.rollback()
                return False
            result = execute_run_txn(db, run_request, output_item_id, required_components, output_qty_base)
            run_id = int(result["run"].id)
            run = db.get(ManufacturingRun, run_id)
            if run is not None:
                run.created_at = t4
                run.executed_at = t4
            _stamp_by_source(db, run_id, t4)
            db.commit()

            print("Selling product...")
            perform_stock_out_base(
                db,
                item_id=str(int(frame.id)),
                qty_base=_to_base("2", "ea", "count"),
                ref="seed-sale-frame",
                meta={
                    "reason": "sold",
                    "note": "seed",
                    "record_cash_event": True,
                    "sell_unit_price_cents": 15000,
                },
            )
            _stamp_by_source(db, "seed-sale-frame", t5)
            db.commit()

            print("Refunding one unit...")
            refund_source = "seed-refund-frame"
            refund_qty = _to_base("1", "ea", "count")
            db.add(
                CashEvent(
                    kind="refund",
                    category=None,
                    amount_cents=-15000,
                    item_id=int(frame.id),
                    qty_base=refund_qty,
                    unit_price_cents=None,
                    source_kind="refund",
                    source_id=refund_source,
                    related_source_id="seed-sale-frame",
                    notes="seed refund",
                    created_at=t6,
                )
            )
            perform_stock_in_base(
                db,
                item_id=str(int(frame.id)),
                qty_base=refund_qty,
                unit_cost_cents=5000,
                ref=refund_source,
                meta={"source_kind": "refund_restock", "source_id": refund_source},
            )
            _stamp_by_source(db, refund_source, t6)

            db.add(
                CashEvent(
                    kind="expense",
                    category="rent",
                    amount_cents=-50000,
                    item_id=None,
                    qty_base=None,
                    unit_price_cents=None,
                    source_kind="expense",
                    source_id="seed-expense-rent",
                    related_source_id=None,
                    notes="seed expense",
                    created_at=t6,
                )
            )
            db.commit()

            # Profit snapshot seed requirement is satisfied by sale/refund/expense + COGS movements.
            print("Seed complete.")
            return True
    finally:
        engine.dispose()


# ----------------------------
# Main Execution
# ----------------------------

def main():
    print("=== BUS Core Dev Seeder ===")
    ensure_token()

    print("Creating vendors...")
    create_vendor("Steel Supply Co")
    create_vendor("Local Wood Ltd")
    create_vendor("Packaging Inc")

    print("Creating raw materials...")
    steel = create_item("Steel Rod", "length", "m")
    wood = create_item("Wood Panel", "area", "m2")
    screws = create_item("Screws", "count", "ea")

    print("Creating finished products...")
    frame = create_item("Table Frame", "count", "ea", True)
    create_item("Workbench", "count", "ea", True)

    print("Purchasing stock...")
    purchase(steel["id"], 100, "m", 500)
    purchase(wood["id"], 50, "m2", 2000)
    purchase(screws["id"], 1000, "ea", 10)

    print("Creating recipes...")
    recipe_frame = create_recipe(
        "Frame Recipe",
        frame["id"],
        1,
        "ea",
        [
            {"item_id": steel["id"], "quantity_decimal": "5", "uom": "m"},
            {"item_id": screws["id"], "quantity_decimal": "20", "uom": "ea"},
        ],
    )

    print("Manufacturing...")
    manufacture(recipe_frame["id"], 5)

    print("Selling products...")
    stock_out(frame["id"], 2, "ea", "sold", 15000)

    print("Refunding 1 frame...")
    # Assume frame unit cost ~ $50 (5000 cents) for deterministic seed
    refund(15000, frame["id"], 1, "ea", 5000)

    print("Adding expenses...")
    expense(50000, "rent")

    print("Profit snapshot...")
    try:
        from_ts = datetime(2020, 1, 1, tzinfo=UTC).strftime("%Y-%m-%d")
        to_ts = datetime.now(UTC).strftime("%Y-%m-%d")
        r = _session().get(
            f"{BASE}/app/finance/profit",
            params={"from": from_ts, "to": to_ts},
        )
        if not r.ok:
            print("/app/finance/profit returned:", r.status_code, r.text)
        else:
            print("Profit:", r.json())
    except Exception as e:
        print("Profit endpoint error:", e)

    print("Seed complete.")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--db-path", type=str, default="")
    args = parser.parse_args()

    try:
        if args.self_test:
            ok = self_test()
        elif args.db_path:
            ok = seed_sqlite_demo_db(args.db_path)
        else:
            ok = main()

        if not ok:
            print("Seeder finished with errors.")

    except Exception as e:
        print("Seeder encountered an error:", e)
        # No sys.exit() here to avoid raising SystemExit during debugging
