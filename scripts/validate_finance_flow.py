# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import argparse
import csv
import re
import sys
import uuid
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from io import StringIO
from typing import Any

import requests


WINDOW_FROM = "2000-01-01"
WINDOW_TO = "2999-12-31"

EXPECTED_CSV_COLUMNS = [
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

UNIT_MULTIPLIER = {
    "length": {"mm": 1, "cm": 10, "m": 1000},
    "area": {"mm2": 1, "cm2": 100, "m2": 1_000_000},
    "volume": {"mm3": 1, "cm3": 1_000, "ml": 1_000, "l": 1_000_000, "m3": 1_000_000_000},
    "weight": {"mg": 1, "g": 1_000, "kg": 1_000_000},
    "count": {"mc": 1, "ea": 1_000},
}


class ValidationFailure(AssertionError):
    pass


@dataclass
class ItemRef:
    logical_name: str
    item_id: int
    dimension: str
    uom: str


@dataclass
class Batch:
    item_key: str
    qty_base_remaining: int
    unit_cost_cents: int
    source_id: str


@dataclass
class ExpectedEvent:
    kind: str
    source_id: str
    amount_cents: int
    item_key: str | None = None
    notes: str | None = None
    cogs_cents: int | None = None
    gross_profit_cents: int | None = None


@dataclass
class ExpectedModel:
    items: dict[str, ItemRef] = field(default_factory=dict)
    inventory_base: dict[str, int] = field(default_factory=dict)
    batches: dict[str, list[Batch]] = field(default_factory=dict)
    events: list[ExpectedEvent] = field(default_factory=list)
    operations_performed: int = 0

    def add_item(self, key: str, item_id: int, dimension: str, uom: str) -> None:
        self.items[key] = ItemRef(key, item_id, dimension, uom)
        self.inventory_base[key] = 0
        self.batches[key] = []

    def to_base(self, key: str, quantity_decimal: str, uom: str) -> int:
        item = self.items[key]
        multiplier = UNIT_MULTIPLIER[item.dimension][uom]
        return int((Decimal(quantity_decimal) * Decimal(multiplier)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def human_quantity_for_item_uom(self, key: str, qty_base: int) -> Decimal:
        item = self.items[key]
        multiplier = UNIT_MULTIPLIER[item.dimension][item.uom]
        return Decimal(qty_base) / Decimal(multiplier)

    def line_cost_cents(self, key: str, qty_base: int, unit_cost_cents: int) -> int:
        return int(
            (Decimal(unit_cost_cents) * self.human_quantity_for_item_uom(key, qty_base)).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )

    def stock_in(self, key: str, quantity_decimal: str, uom: str, unit_cost_cents: int, source_id: str) -> None:
        qty_base = self.to_base(key, quantity_decimal, uom)
        self.inventory_base[key] += qty_base
        self.batches[key].append(Batch(key, qty_base, unit_cost_cents, source_id))

    def purchase(
        self,
        key: str,
        quantity_decimal: str,
        uom: str,
        unit_cost_cents: int,
        source_id: str,
        notes: str | None = None,
    ) -> None:
        qty_base = self.to_base(key, quantity_decimal, uom)
        amount_cents = self.line_cost_cents(key, qty_base, unit_cost_cents)
        self.inventory_base[key] += qty_base
        self.batches[key].append(Batch(key, qty_base, unit_cost_cents, source_id))
        self.events.append(ExpectedEvent("purchase", source_id, -amount_cents, key, notes))

    def sale(
        self,
        key: str,
        quantity_decimal: str,
        uom: str,
        sell_unit_price_cents: int,
        source_id: str,
    ) -> None:
        qty_base = self.to_base(key, quantity_decimal, uom)
        sale_qty = self.human_quantity_for_item_uom(key, qty_base)
        amount_cents = int((Decimal(sell_unit_price_cents) * sale_qty).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

        remaining = qty_base
        cogs_cents = 0
        for batch in self.batches[key]:
            if remaining <= 0:
                break
            if batch.qty_base_remaining <= 0:
                continue
            take = min(batch.qty_base_remaining, remaining)
            cogs_cents += self.line_cost_cents(key, take, batch.unit_cost_cents)
            batch.qty_base_remaining -= take
            remaining -= take
        if remaining:
            raise ValidationFailure(f"Expected model oversold {key}: missing base quantity {remaining}")

        self.inventory_base[key] -= qty_base
        self.events.append(
            ExpectedEvent(
                "sale",
                source_id,
                amount_cents,
                key,
                cogs_cents=cogs_cents,
                gross_profit_cents=amount_cents - cogs_cents,
            )
        )

    def refund(
        self,
        key: str,
        quantity_decimal: str,
        uom: str,
        refund_source_id: str,
        amount_cents: int,
        restock_unit_cost_cents: int,
        related_source_id: str,
    ) -> None:
        qty_base = self.to_base(key, quantity_decimal, uom)
        self.inventory_base[key] += qty_base
        self.batches[key].append(Batch(key, qty_base, restock_unit_cost_cents, refund_source_id))
        self.events.append(ExpectedEvent("refund", refund_source_id, -abs(amount_cents), key))

        related_sales = [event for event in self.events if event.kind == "sale" and event.source_id == related_source_id]
        if len(related_sales) != 1:
            raise ValidationFailure(f"Expected exactly one related sale for refund source {related_source_id}")

    @property
    def expected_purchase_total(self) -> int:
        return sum(event.amount_cents for event in self.events if event.kind == "purchase")

    @property
    def expected_sales_total(self) -> int:
        return sum(event.amount_cents for event in self.events if event.kind == "sale")

    @property
    def expected_refunds_total(self) -> int:
        return sum(event.amount_cents for event in self.events if event.kind == "refund")

    @property
    def expected_cogs_total(self) -> int:
        return sum(int(event.cogs_cents or 0) for event in self.events if event.kind == "sale")

    @property
    def expected_net_sales(self) -> int:
        return self.expected_sales_total + self.expected_refunds_total

    @property
    def expected_gross_profit(self) -> int:
        return self.expected_net_sales - self.expected_cogs_total

    @property
    def expected_expenses(self) -> int:
        return abs(self.expected_purchase_total)

    @property
    def expected_net_profit(self) -> int:
        return self.expected_gross_profit - self.expected_expenses

    def source_ids_for(self, kind: str) -> set[str]:
        return {event.source_id for event in self.events if event.kind == kind}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate BUS Core finance/inventory transaction math through the public HTTP API."
    )
    parser.add_argument("--base-url", required=True, help="BUS Core base URL, for example http://127.0.0.1:8765")
    parser.add_argument(
        "--i-know-this-mutates-data",
        action="store_true",
        help="Required acknowledgement that this script creates real BUS Core test data.",
    )
    return parser.parse_args()


def normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def fail(message: str, context: Any | None = None) -> None:
    if context is None:
        raise ValidationFailure(message)
    raise ValidationFailure(f"{message}\nContext: {context}")


def api_get(session: requests.Session, base_url: str, path: str, *, expected_status: int = 200) -> requests.Response:
    response = session.get(f"{base_url}{path}", timeout=30)
    if response.status_code != expected_status:
        fail(
            f"GET {path} returned {response.status_code}, expected {expected_status}",
            response.text[:2000],
        )
    return response


def api_post(
    session: requests.Session,
    base_url: str,
    path: str,
    payload: dict[str, Any],
    *,
    expected_status: int = 200,
) -> dict[str, Any]:
    response = session.post(f"{base_url}{path}", json=payload, timeout=30)
    if response.status_code != expected_status:
        fail(
            f"POST {path} returned {response.status_code}, expected {expected_status}",
            {"payload": payload, "response": response.text[:2000]},
        )
    try:
        return response.json()
    except ValueError as exc:
        fail(f"POST {path} did not return JSON: {exc}", response.text[:2000])
    raise AssertionError("unreachable")


def get_session_token(session: requests.Session, base_url: str) -> None:
    response = api_get(session, base_url, "/session/token")
    payload = response.json()
    if not payload.get("token"):
        fail("GET /session/token did not return a token", payload)
    if not session.cookies:
        fail("GET /session/token did not set a session cookie")


def fetch_summary(session: requests.Session, base_url: str) -> dict[str, Any]:
    return api_get(session, base_url, f"/app/finance/summary?from={WINDOW_FROM}&to={WINDOW_TO}").json()


def fetch_transactions(session: requests.Session, base_url: str, *, limit: int = 500) -> list[dict[str, Any]]:
    payload = api_get(
        session,
        base_url,
        f"/app/finance/transactions?from={WINDOW_FROM}&to={WINDOW_TO}&limit={limit}",
    ).json()
    return list(payload.get("transactions") or [])


def fetch_csv(session: requests.Session, base_url: str) -> tuple[list[str], list[dict[str, str]]]:
    response = api_get(
        session,
        base_url,
        f"/app/finance/export.csv?profile=generic&from={WINDOW_FROM}&to={WINDOW_TO}",
    )
    reader = csv.DictReader(StringIO(response.text))
    return list(reader.fieldnames or []), list(reader)


def assert_clean_finance_window(session: requests.Session, base_url: str) -> None:
    summary = fetch_summary(session, base_url)
    transactions = fetch_transactions(session, base_url, limit=1)
    non_zero_fields = {
        key: int(summary.get(key, 0) or 0)
        for key in (
            "gross_sales_cents",
            "returns_cents",
            "net_sales_cents",
            "cogs_cents",
            "gross_profit_cents",
            "expenses_cents",
            "net_profit_cents",
        )
        if int(summary.get(key, 0) or 0) != 0
    }
    if transactions or non_zero_fields:
        fail(
            "The wide finance window is not empty. Run this validator against a fresh test BUS_DB; no data was mutated.",
            {"non_zero_summary_fields": non_zero_fields, "sample_transactions": transactions},
        )


def create_item(
    session: requests.Session,
    base_url: str,
    model: ExpectedModel,
    key: str,
    name: str,
    *,
    dimension: str,
    uom: str,
    is_product: bool,
    price: float,
) -> int:
    payload = {
        "name": name,
        "dimension": dimension,
        "uom": uom,
        "is_product": is_product,
        "price": price,
    }
    body = api_post(session, base_url, "/app/items", payload)
    item_obj = body.get("item") if isinstance(body, dict) else None
    if item_obj is None and isinstance(body, dict) and "id" in body:
        item_obj = body
    if not item_obj or item_obj.get("id") is None:
        fail("Unexpected /app/items create response", body)
    item_id = int(item_obj["id"])
    model.add_item(key, item_id, dimension, uom)
    model.operations_performed += 1
    return item_id


def item_payload(model: ExpectedModel, key: str) -> dict[str, Any]:
    return {"item_id": model.items[key].item_id}


def assert_inventory(session: requests.Session, base_url: str, model: ExpectedModel, key: str) -> dict[str, Any]:
    item = model.items[key]
    actual = api_get(session, base_url, f"/app/items/{item.item_id}").json()
    actual_base = int(actual.get("stock_on_hand_int", 0) or 0)
    expected_base = int(model.inventory_base[key])
    if actual_base != expected_base:
        fail(
            f"Inventory mismatch for {key}",
            {
                "item_id": item.item_id,
                "expected_base": expected_base,
                "actual_base": actual_base,
                "actual_display": actual.get("stock_on_hand_display"),
            },
        )
    return actual


def stock_in(
    session: requests.Session,
    base_url: str,
    model: ExpectedModel,
    key: str,
    *,
    quantity_decimal: str,
    uom: str,
    unit_cost_cents: int,
    source_id: str,
) -> None:
    payload = {
        **item_payload(model, key),
        "quantity_decimal": quantity_decimal,
        "uom": uom,
        "unit_cost_cents": unit_cost_cents,
        "source_id": source_id,
    }
    api_post(session, base_url, "/app/stock/in", payload)
    model.stock_in(key, quantity_decimal, uom, unit_cost_cents, source_id)
    model.operations_performed += 1
    assert_inventory(session, base_url, model, key)


def purchase(
    session: requests.Session,
    base_url: str,
    model: ExpectedModel,
    key: str,
    *,
    quantity_decimal: str,
    uom: str,
    unit_cost_cents: int,
    source_id: str,
    category: str,
    notes: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        **item_payload(model, key),
        "quantity_decimal": quantity_decimal,
        "uom": uom,
        "unit_cost_cents": unit_cost_cents,
        "source_id": source_id,
        "category": category,
    }
    if notes is not None:
        payload["notes"] = notes
    body = api_post(session, base_url, "/app/purchase", payload)
    if body.get("source_id") != source_id:
        fail("/app/purchase did not preserve requested source_id", {"expected": source_id, "response": body})
    model.purchase(key, quantity_decimal, uom, unit_cost_cents, source_id, notes)
    model.operations_performed += 1
    assert_inventory(session, base_url, model, key)


def sale(
    session: requests.Session,
    base_url: str,
    model: ExpectedModel,
    key: str,
    *,
    quantity_decimal: str,
    uom: str,
    sell_unit_price_cents: int,
    source_id: str,
) -> None:
    payload = {
        **item_payload(model, key),
        "quantity_decimal": quantity_decimal,
        "uom": uom,
        "reason": "sold",
        "record_cash_event": True,
        "sell_unit_price_cents": sell_unit_price_cents,
        "note": source_id,
    }
    body = api_post(session, base_url, "/app/stock/out", payload)
    lines = body.get("lines") or []
    if not lines:
        fail("/app/stock/out returned no FIFO lines", body)
    unexpected_sources = {line.get("source_id") for line in lines if line.get("source_id") != source_id}
    if unexpected_sources:
        fail("/app/stock/out did not use note as sale source_id", {"expected": source_id, "response": body})
    model.sale(key, quantity_decimal, uom, sell_unit_price_cents, source_id)
    model.operations_performed += 1
    assert_inventory(session, base_url, model, key)


def refund(
    session: requests.Session,
    base_url: str,
    model: ExpectedModel,
    key: str,
    *,
    quantity_decimal: str,
    uom: str,
    refund_amount_cents: int,
    related_source_id: str,
    restock_unit_cost_cents: int,
) -> str:
    payload = {
        **item_payload(model, key),
        "quantity_decimal": quantity_decimal,
        "uom": uom,
        "refund_amount_cents": refund_amount_cents,
        "restock_inventory": True,
        "related_source_id": related_source_id,
        "category": "refunds",
        "notes": f"refund for {related_source_id}",
    }
    body = api_post(session, base_url, "/app/finance/refund", payload)
    refund_source_id = str(body.get("source_id") or "")
    if not refund_source_id:
        fail("/app/finance/refund did not return source_id", body)
    model.refund(
        key,
        quantity_decimal,
        uom,
        refund_source_id,
        refund_amount_cents,
        restock_unit_cost_cents,
        related_source_id,
    )
    model.operations_performed += 1
    assert_inventory(session, base_url, model, key)
    return refund_source_id


def require_one(rows: list[dict[str, Any]], *, kind: str, source_id: str) -> dict[str, Any]:
    matches = [row for row in rows if row.get("kind") == kind and row.get("source_id") == source_id]
    if len(matches) != 1:
        fail(f"Expected one {kind} row for source_id {source_id}, found {len(matches)}", matches)
    return matches[0]


def sum_amounts(rows: list[dict[str, Any]], kind: str, source_ids: set[str] | None = None) -> int:
    total = 0
    for row in rows:
        if row.get("kind") != kind:
            continue
        if source_ids is not None and row.get("source_id") not in source_ids:
            continue
        total += int(row.get("amount_cents") or 0)
    return total


def assert_finance(model: ExpectedModel, summary: dict[str, Any], transactions: list[dict[str, Any]], stock_only_source: str) -> dict[str, int]:
    expected_summary = {
        "gross_sales_cents": model.expected_sales_total,
        "returns_cents": model.expected_refunds_total,
        "net_sales_cents": model.expected_net_sales,
        "cogs_cents": model.expected_cogs_total,
        "gross_profit_cents": model.expected_gross_profit,
        "expenses_cents": model.expected_expenses,
        "net_profit_cents": model.expected_net_profit,
    }
    for field_name, expected_value in expected_summary.items():
        actual_value = int(summary.get(field_name, 0) or 0)
        if actual_value != expected_value:
            fail(f"Finance summary mismatch for {field_name}", {"expected": expected_value, "actual": actual_value, "summary": summary})

    stock_only_purchase_rows = [
        row for row in transactions if row.get("source_id") == stock_only_source and row.get("kind") == "purchase"
    ]
    if stock_only_purchase_rows:
        fail("Stock-only Add Batch appeared as a purchase transaction", stock_only_purchase_rows)

    for event in model.events:
        row = require_one(transactions, kind=event.kind, source_id=event.source_id)
        actual_amount = int(row.get("amount_cents") or 0)
        if actual_amount != event.amount_cents:
            fail(
                f"Transaction amount mismatch for {event.kind} {event.source_id}",
                {"expected": event.amount_cents, "actual": actual_amount, "row": row},
            )
        if event.kind == "purchase" and actual_amount >= 0:
            fail("Purchase transaction is not negative", row)
        if event.kind == "sale":
            if actual_amount <= 0:
                fail("Sale transaction is not positive", row)
            if int(row.get("cogs_cents") or 0) != int(event.cogs_cents or 0):
                fail("Sale COGS mismatch", {"expected": event.cogs_cents, "row": row})
            if int(row.get("gross_profit_cents") or 0) != int(event.gross_profit_cents or 0):
                fail("Sale gross profit mismatch", {"expected": event.gross_profit_cents, "row": row})
        if event.kind == "refund" and actual_amount >= 0:
            fail("Refund transaction does not follow current negative amount convention", row)

    return {
        "purchases": sum_amounts(transactions, "purchase", model.source_ids_for("purchase")),
        "sales": sum_amounts(transactions, "sale", model.source_ids_for("sale")),
        "refunds": sum_amounts(transactions, "refund", model.source_ids_for("refund")),
    }


def cents_from_amount_string(amount: str) -> int:
    return int((Decimal(amount) * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def assert_csv(model: ExpectedModel, headers: list[str], rows: list[dict[str, str]], stock_only_source: str) -> dict[str, int]:
    if headers != EXPECTED_CSV_COLUMNS:
        fail("CSV headers do not match expected generic export columns", {"expected": EXPECTED_CSV_COLUMNS, "actual": headers})

    amount_re = re.compile(r"^-?\d+\.\d{2}$")
    event_id_re = re.compile(r"^[a-z_]+:\d+$")
    for row in rows:
        if row.get("currency") != "CAD":
            fail("CSV row currency is not CAD", row)
        if not event_id_re.match(row.get("bus_event_id") or ""):
            fail("CSV bus_event_id is missing or not type-prefixed", row)
        amount = row.get("amount") or ""
        if not amount_re.match(amount):
            fail("CSV amount is not fixed two decimals", row)
        amount_cents = int(row.get("amount_cents") or 0)
        if cents_from_amount_string(amount) != amount_cents:
            fail("CSV amount and amount_cents disagree", row)

    stock_only_purchase_rows = [row for row in rows if row.get("source_id") == stock_only_source and row.get("kind") == "purchase"]
    if stock_only_purchase_rows:
        fail("Stock-only Add Batch appeared as a CSV purchase row", stock_only_purchase_rows)

    for event in model.events:
        row = require_one(rows, kind=event.kind, source_id=event.source_id)
        amount_cents = int(row.get("amount_cents") or 0)
        if amount_cents != event.amount_cents:
            fail(
                f"CSV amount mismatch for {event.kind} {event.source_id}",
                {"expected": event.amount_cents, "row": row},
            )
        if not row.get("source_id"):
            fail("CSV source_id missing", row)
        if event.kind == "purchase" and amount_cents >= 0:
            fail("CSV purchase row is not negative", row)
        if event.kind == "sale" and amount_cents <= 0:
            fail("CSV sale row is not positive", row)
        if event.kind == "refund" and amount_cents >= 0:
            fail("CSV refund row does not follow current negative amount convention", row)
        if event.notes is not None and row.get("notes") != event.notes:
            fail("CSV notes field was not preserved through csv.DictReader", {"expected": event.notes, "row": row})

    return {
        "purchases": sum_amounts(rows, "purchase", model.source_ids_for("purchase")),
        "sales": sum_amounts(rows, "sale", model.source_ids_for("sale")),
        "refunds": sum_amounts(rows, "refund", model.source_ids_for("refund")),
    }


def run_scenario(session: requests.Session, base_url: str, run_id: str) -> tuple[ExpectedModel, str, dict[str, dict[str, Any]]]:
    model = ExpectedModel()
    actual_inventory: dict[str, dict[str, Any]] = {}

    create_item(session, base_url, model, "MAT-RIBBON", f"MAT-RIBBON-{run_id}", dimension="length", uom="m", is_product=False, price=0)
    create_item(session, base_url, model, "MAT-LABEL", f"MAT-LABEL-{run_id}", dimension="count", uom="ea", is_product=False, price=0)
    create_item(session, base_url, model, "PROD-CANDLE", f"PROD-CANDLE-{run_id}", dimension="count", uom="ea", is_product=True, price=15.00)
    create_item(session, base_url, model, "PROD-KIT", f"PROD-KIT-{run_id}", dimension="count", uom="ea", is_product=True, price=25.00)

    stock_only_source = f"stock-only-opening-candle-{run_id}"
    stock_in(
        session,
        base_url,
        model,
        "PROD-CANDLE",
        quantity_decimal="5",
        uom="ea",
        unit_cost_cents=500,
        source_id=stock_only_source,
    )
    purchase(
        session,
        base_url,
        model,
        "MAT-RIBBON",
        quantity_decimal="12.5",
        uom="m",
        unit_cost_cents=80,
        source_id=f"purchase-ribbon-{run_id}",
        category="materials",
        notes="ribbon purchase",
    )
    purchase(
        session,
        base_url,
        model,
        "PROD-CANDLE",
        quantity_decimal="30",
        uom="ea",
        unit_cost_cents=650,
        source_id=f"purchase-candle-{run_id}",
        category="materials",
    )
    purchase(
        session,
        base_url,
        model,
        "PROD-KIT",
        quantity_decimal="20",
        uom="ea",
        unit_cost_cents=1200,
        source_id=f"purchase-kit-{run_id}",
        category="materials",
        notes="bulk, order\nsecond line",
    )
    sale(
        session,
        base_url,
        model,
        "PROD-CANDLE",
        quantity_decimal="8",
        uom="ea",
        sell_unit_price_cents=1500,
        source_id=f"sale-candle-1-{run_id}",
    )
    sale(
        session,
        base_url,
        model,
        "PROD-KIT",
        quantity_decimal="4",
        uom="ea",
        sell_unit_price_cents=2500,
        source_id=f"sale-kit-1-{run_id}",
    )
    purchase(
        session,
        base_url,
        model,
        "MAT-LABEL",
        quantity_decimal="200",
        uom="ea",
        unit_cost_cents=12,
        source_id=f"purchase-label-{run_id}",
        category="materials",
    )
    sale_candle_2_source = f"sale-candle-2-{run_id}"
    sale(
        session,
        base_url,
        model,
        "PROD-CANDLE",
        quantity_decimal="6",
        uom="ea",
        sell_unit_price_cents=1600,
        source_id=sale_candle_2_source,
    )
    refund(
        session,
        base_url,
        model,
        "PROD-CANDLE",
        quantity_decimal="2",
        uom="ea",
        refund_amount_cents=3200,
        related_source_id=sale_candle_2_source,
        restock_unit_cost_cents=650,
    )

    for key in model.items:
        actual_inventory[key] = assert_inventory(session, base_url, model, key)
    return model, stock_only_source, actual_inventory


def display_quantity(model: ExpectedModel, key: str, qty_base: int) -> str:
    value = model.human_quantity_for_item_uom(key, qty_base).quantize(Decimal("0.01"))
    return f"{value.normalize():f} {model.items[key].uom}"


def print_report(
    model: ExpectedModel,
    transaction_totals: dict[str, int],
    csv_totals: dict[str, int],
    summary: dict[str, Any],
    actual_inventory: dict[str, dict[str, Any]],
) -> None:
    print("\nBUS Core finance flow validation report")
    print("=======================================")
    print(f"Operations performed: {model.operations_performed}")
    print(f"Expected purchase expenses: {model.expected_purchase_total} cents")
    print(f"Actual purchase expenses from finance transactions: {transaction_totals['purchases']} cents")
    print(f"Actual purchase expenses from CSV: {csv_totals['purchases']} cents")
    print(f"Expected sales: {model.expected_sales_total} cents")
    print(f"Actual sales from finance transactions: {transaction_totals['sales']} cents")
    print(f"Actual sales from CSV: {csv_totals['sales']} cents")
    print(f"Expected refunds: {model.expected_refunds_total} cents")
    print(f"Actual refunds from finance transactions: {transaction_totals['refunds']} cents")
    print(f"Actual refunds from CSV: {csv_totals['refunds']} cents")
    print(f"Expected COGS: {model.expected_cogs_total} cents")
    print(f"Actual COGS from finance summary: {int(summary['cogs_cents'])} cents")
    print(f"Expected net profit: {model.expected_net_profit} cents")
    print(f"Actual net profit from finance summary: {int(summary['net_profit_cents'])} cents")
    print("Inventory expected vs actual:")
    for key, item in model.items.items():
        expected_base = model.inventory_base[key]
        actual = actual_inventory[key]
        actual_display = actual.get("stock_on_hand_display") or {}
        print(
            f"  - {key} (item_id={item.item_id}): "
            f"expected {expected_base} base / {display_quantity(model, key, expected_base)}; "
            f"actual {actual.get('stock_on_hand_int')} base / "
            f"{actual_display.get('value')} {actual_display.get('unit')}"
        )
    print("PASS")


def main() -> int:
    args = parse_args()
    if not args.i_know_this_mutates_data:
        print("ERROR: --i-know-this-mutates-data is required because this script creates real BUS Core test data.", file=sys.stderr)
        return 2

    base_url = normalize_base_url(args.base_url)
    run_id = uuid.uuid4().hex[:10]

    print("WARNING: this validator mutates BUS Core data by creating test items, stock movements, purchases, sales, and a refund.")
    print("Run it against a fresh temporary BUS_DB or another disposable BUS Core test instance.")
    print(f"Target base URL: {base_url}")
    print(f"Run id: {run_id}")

    session = requests.Session()
    get_session_token(session, base_url)
    api_get(session, base_url, "/app/items")
    assert_clean_finance_window(session, base_url)

    model, stock_only_source, actual_inventory = run_scenario(session, base_url, run_id)
    summary = fetch_summary(session, base_url)
    transactions = fetch_transactions(session, base_url)
    headers, csv_rows = fetch_csv(session, base_url)

    transaction_totals = assert_finance(model, summary, transactions, stock_only_source)
    csv_totals = assert_csv(model, headers, csv_rows, stock_only_source)
    if transaction_totals != csv_totals:
        fail("Finance transaction totals and CSV totals disagree", {"transactions": transaction_totals, "csv": csv_totals})

    print_report(model, transaction_totals, csv_totals, summary, actual_inventory)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationFailure as exc:
        print("\nFAIL")
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
