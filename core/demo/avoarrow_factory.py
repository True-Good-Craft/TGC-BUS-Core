# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from sqlalchemy.orm import Session

from core.api.cost_contract import normalize_cost_to_base_cents
from core.api.quantity_contract import normalize_quantity_to_base_int
from core.api.routes.ledger_api import StockOutIn, stock_out
from core.appdb.ledger import add_batch
from core.appdb.models import CashEvent, Item, ItemBatch, ItemMovement, Vendor
from core.appdb.models_recipes import Recipe, RecipeItem
from core.manufacturing.service import execute_run_txn, validate_run
from core.api.schemas.manufacturing import RecipeRunRequest
from core.services.finance_service import process_refund, record_expense


EMPTY_GUARD_ERROR = "Database is not empty. Demo load aborted."


def _require_empty(db: Session) -> None:
    has_rows = (
        db.query(Item).first() is not None
        or db.query(ItemBatch).first() is not None
        or db.query(ItemMovement).first() is not None
        or db.query(CashEvent).first() is not None
    )
    if has_rows:
        raise ValueError(EMPTY_GUARD_ERROR)


def _create_vendor(db: Session, name: str, province: str) -> Vendor:
    vendor = Vendor(name=name, contact=province, role="vendor", is_vendor=1, is_org=1)
    db.add(vendor)
    db.flush()
    return vendor


def _create_item(db: Session, name: str, *, is_product: bool = False) -> Item:
    item = Item(name=name, uom="ea", dimension="count", qty_stored=0, is_product=is_product)
    db.add(item)
    db.flush()
    return item


def _purchase_batch(db: Session, item: Item, quantity_decimal: str, unit_cost_decimal: str) -> None:
    qty_base = normalize_quantity_to_base_int(item.dimension, "ea", quantity_decimal)
    unit_cost_cents = normalize_cost_to_base_cents(
        item.dimension,
        "ea",
        unit_cost_decimal,
    )
    add_batch(
        db,
        item_id=int(item.id),
        qty=int(qty_base),
        unit_cost_cents=int(unit_cost_cents),
        source_kind="purchase",
        source_id="avoarrow_demo",
    )


def load_demo_factory(db: Session) -> dict:
    summary = {
        "vendors_created": 0,
        "items_created": 0,
        "batches_created": 0,
        "blueprints_created": 0,
        "units_manufactured": 0,
        "units_sold": 0,
        "refunds_processed": 0,
        "expenses_recorded": 0,
    }

    try:
        with db.begin():
            _require_empty(db)

            maple = _create_vendor(db, "Maple Fibre Supply", "Ontario")
            _ = maple
            _create_vendor(db, "Northern Composites Ltd", "Quebec")
            _create_vendor(db, "TrueNorth Packaging", "Alberta")
            summary["vendors_created"] = 3

            paper = _create_item(db, "Premium Paper Sheet")
            carbon = _create_item(db, "Carbon Reinforcement Strip")
            nose_weight = _create_item(db, "Nose Weight Insert")
            summary["items_created"] += 3

            _purchase_batch(db, paper, "100", "0.05")
            _purchase_batch(db, paper, "100", "0.07")
            _purchase_batch(db, carbon, "50", "0.20")
            _purchase_batch(db, carbon, "50", "0.25")
            _purchase_batch(db, nose_weight, "100", "0.10")
            summary["batches_created"] = 5

            avoarrow = _create_item(db, "AvoArrow Mk I", is_product=True)
            summary["items_created"] += 1

            recipe = Recipe(
                name="AvoArrow Mk I Blueprint",
                code="AVOARROW-MK1",
                output_item_id=int(avoarrow.id),
                output_qty=1,
                archived=False,
                notes="Blueprint for AvoArrow Mk I",
            )
            db.add(recipe)
            db.flush()
            db.add_all(
                [
                    RecipeItem(recipe_id=recipe.id, item_id=paper.id, qty_required=2, is_optional=False, sort_order=0),
                    RecipeItem(recipe_id=recipe.id, item_id=carbon.id, qty_required=1, is_optional=False, sort_order=1),
                    RecipeItem(recipe_id=recipe.id, item_id=nose_weight.id, qty_required=1, is_optional=False, sort_order=2),
                ]
            )
            summary["blueprints_created"] = 1

            req = RecipeRunRequest(recipe_id=int(recipe.id), output_qty=10)
            output_item_id, required, k, shortages = validate_run(db, req)
            if shortages:
                raise ValueError("Unexpected demo shortage")
            execute_run_txn.__wrapped__(db, req, output_item_id, required, k)
            summary["units_manufactured"] = 10

            sale_resp = stock_out(
                StockOutIn(
                    item_id=int(avoarrow.id),
                    quantity_decimal="5",
                    uom="ea",
                    reason="sold",
                    record_cash_event=True,
                    sell_unit_price_cents=1500,
                ),
                db,
            )
            summary["units_sold"] = 5 if sale_resp.get("ok") else 0

            sale_event = (
                db.query(CashEvent)
                .filter(CashEvent.kind == "sale", CashEvent.item_id == int(avoarrow.id))
                .order_by(CashEvent.id.desc())
                .first()
            )
            if not sale_event or not sale_event.source_id:
                raise ValueError("Demo sale source id missing")

            sale_source_id = str(sale_event.source_id)
            process_refund(
                db,
                item_id=int(avoarrow.id),
                refund_amount_cents=1500,
                quantity_decimal="1",
                uom="ea",
                restock_inventory=True,
                related_source_id=str(sale_source_id),
                category="refund",
                notes="Demo customer refund with restock",
            )
            summary["refunds_processed"] = 1

            record_expense(
                db,
                amount_cents=20000,
                category="rent",
                notes="Workshop Lease",
            )
            summary["expenses_recorded"] = 1
    except Exception:
        db.rollback()
        raise

    return summary
