#!/usr/bin/env python3
"""
BUS Core Minimal Seeder
Theme: Northwind Aeronautics (Paper Airplane Factory)

Purpose:
Populate UI with clean, economically sane data.
NOT a stress test.
"""

import requests
import random
import json
from typing import Dict, List

BASE_URL = "http://127.0.0.1:8765"
SESSION = None
random.seed(42)


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def get_session():
    global SESSION
    if SESSION is None:
        SESSION = requests.Session()
    return SESSION


def post(path: str, payload: Dict):
    r = get_session().post(f"{BASE_URL}{path}", json=payload, timeout=10)
    if r.status_code not in (200, 201):
        print(f"[ERROR] {path} → {r.status_code} → {r.text}")
        return None
    return r.json()


def get(path: str):
    r = get_session().get(f"{BASE_URL}{path}", timeout=10)
    if r.status_code != 200:
        print(f"[ERROR] {path} → {r.status_code}")
        return None
    return r.json()


def authenticate():
    print("Authenticating...")
    r = get_session().get(f"{BASE_URL}/session/token", timeout=10)
    if r.status_code != 200:
        raise SystemExit("Auth failed")
    print("Session established.")


# --------------------------------------------------
# Seed Logic
# --------------------------------------------------

def create_vendors():
    vendors = []
    for name in ["AeroFold Supply", "Strato Materials", "Nimbus Logistics"]:
        resp = post("/app/vendors", {"name": name, "role": "vendor"})
        if resp:
            vendors.append(resp["id"])
    return vendors


def create_items(vendors: List[int]):
    raw_ids = []
    product_ids = []

    raws = [
        ("Premium Paper Sheet", "RAW-PAPER-001"),
        ("Carbon Strip", "RAW-RFN-001"),
        ("Nose Weight", "RAW-WGT-001"),
    ]

    for name, sku in raws:
        resp = post("/app/items", {
            "name": name,
            "sku": sku,
            "dimension": "count",
            "uom": "mc",
            "price_decimal": 10.0,
            "is_product": False,
            "vendor_id": vendors[0] if vendors else None
        })
        if resp:
            raw_ids.append(resp["id"])

    products = [
        "Falcon Mk I",
        "SkyLancer Pro",
        "Nimbus Dart"
    ]

    for i, name in enumerate(products, 1):
        resp = post("/app/items", {
            "name": name,
            "sku": f"PROD-{i:03d}",
            "dimension": "count",
            "uom": "mc",
            "price_decimal": 49.99,
            "is_product": True,
            "vendor_id": vendors[1] if vendors else None
        })
        if resp:
            product_ids.append(resp["id"])

    return raw_ids, product_ids


def seed_inventory(raw_ids: List[int]):
    for item_id in raw_ids:
        resp = post("/app/ledger/purchase", {
            "item_id": item_id,
            "quantity_decimal": "100",
            "uom": "mc",
            "unit_cost_cents": 100
        })

        if not resp:
            print(f"FAILED PURCHASE FOR RAW {item_id}")
        else:
            print(f"RAW INVENTORY OK {item_id}")


def seed_products(product_ids: List[int]):
    for item_id in product_ids:
        resp = post("/app/ledger/purchase", {
            "item_id": item_id,
            "quantity_decimal": "10",
            "uom": "mc",
            "unit_cost_cents": 1000
        })

        if not resp:
            print(f"FAILED PURCHASE FOR PRODUCT {item_id}")
        else:
            print(f"PRODUCT INVENTORY OK {item_id}")


def record_sales(product_ids: List[int]):
    sales = []
    for product_id in product_ids:
        for _ in range(2):
            resp = post("/app/ledger/stock/out", {
                "item_id": product_id,
                "quantity_decimal": "1",
                "uom": "mc",
                "reason": "sold",
                "record_cash_event": True,
                "sell_unit_price_cents": 2000
            })
            if resp and "lines" in resp and resp["lines"]:
                source_id = resp["lines"][0]["source_id"]
                sales.append((product_id, source_id))
    return sales


def record_refund(sales):
    if not sales:
        return
    product_id, source_id = sales[0]

    post("/app/finance/refund", {
        "item_id": product_id,
        "refund_amount_cents": 2000,
        "quantity_decimal": "1",
        "uom": "mc",
        "restock_inventory": True,
        "related_source_id": source_id
    })


def validate():
    print("\nValidation:")
    profit = get("/app/finance/profit?range=all")
    valuation = get("/app/ledger/valuation")
    print("Profit:", json.dumps(profit, indent=2))
    print("Valuation:", json.dumps(valuation, indent=2))


# --------------------------------------------------
# Main
# --------------------------------------------------

def main():
    print("=== BUS Core Minimal Seeder ===")

    authenticate()
    vendors = create_vendors()
    raw_ids, product_ids = create_items(vendors)
    seed_inventory(raw_ids)
    seed_products(product_ids)
    sales = record_sales(product_ids)
    record_refund(sales)
    validate()

    print("\nSeeding complete.")


if __name__ == "__main__":
    main()