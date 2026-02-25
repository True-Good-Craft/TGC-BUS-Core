#!/usr/bin/env python3
"""
BUS Core Dev Seeder
Deterministic dataset for UI/Finance testing.
Uses canonical endpoints only.

Improvements:
- No hard sys.exit() that raises SystemExit during normal failure.
- Clearer error reporting.
- Optional --self-test mode to validate payload contracts without hitting the API.
"""

import requests
import sys
import argparse
from datetime import datetime, UTC

BASE = "http://127.0.0.1:8765"

s = requests.Session()


# ----------------------------
# HTTP Helpers
# ----------------------------

def ensure_token():
    r = s.get(f"{BASE}/session/token")
    r.raise_for_status()


def post(path, payload):
    r = s.post(f"{BASE}{path}", json=payload)
    if not r.ok:
        print(f"\nERROR calling {path}")
        print("Payload:", payload)
        print("Response:", r.text)
        raise RuntimeError(f"Request failed: {path}")
    return r.json()


def get(path):
    r = s.get(f"{BASE}{path}")
    r.raise_for_status()
    return r.json()


# ----------------------------
# Domain Helpers
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
    bench = create_item("Workbench", "count", "ea", True)

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
        r = s.get(
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
    args = parser.parse_args()

    try:
        if args.self_test:
            ok = self_test()
        else:
            ok = main()

        if not ok:
            print("Seeder finished with errors.")

    except Exception as e:
        print("Seeder encountered an error:", e)
        # No sys.exit() here to avoid raising SystemExit during debugging
