# SPDX-License-Identifier: AGPL-3.0-or-later
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.api.utils.quantity_guard import reject_legacy_qty_keys
from core.appdb.engine import get_session
from core.appdb.models import Item
from core.appdb.models_recipes import ManufacturingRun, Recipe, RecipeItem
from core.config.writes import require_writes
from core.metrics.metric import default_unit_for, from_base, normalize_quantity_to_base_int
from core.policy.guard import require_owner_commit
from tgc.security import require_token_ctx
from tgc.state import AppState, get_state

router = APIRouter(prefix="/recipes", tags=["recipes"])


def _journals_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if not root:
        # Linux/macOS fallback
        root = os.path.expanduser("~/.local/share")
    d = Path(root) / "BUSCore" / "app" / "data" / "journals"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _append_recipe_journal(entry: dict) -> None:
    try:
        entry = dict(entry)
        entry.setdefault("timestamp", datetime.utcnow().isoformat() + "Z")
        p = _journals_dir() / "recipes.jsonl"
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, separators=(",", ":")) + "\n")
    except Exception:
        pass


class RecipeItemIn(BaseModel):
    item_id: int
    quantity_decimal: str
    uom: str
    optional: bool = False
    sort: int = 0


class RecipeCreate(BaseModel):
    name: str
    code: str | None = None
    output_item_id: int
    quantity_decimal: str = "1"
    uom: str = "ea"
    archived: bool = False
    notes: str | None = None
    items: list[RecipeItemIn] = []


class RecipeUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    output_item_id: int | None = None
    quantity_decimal: str | None = None
    uom: str | None = None
    archived: bool | None = None
    notes: str | None = None
    items: list[RecipeItemIn] = []


def _to_decimal_string(value) -> str:
    text = str(value)
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _resolve_uom_for_item(item: Item) -> str:
    return (getattr(item, "uom", None) or default_unit_for(item.dimension) or "ea").lower()


def _serialize_recipe_detail(db: Session, recipe: Recipe) -> dict:
    output_item = db.get(Item, recipe.output_item_id) if recipe.output_item_id else None
    output_uom = _resolve_uom_for_item(output_item) if output_item else "ea"
    output_dimension = output_item.dimension if output_item else "count"
    output_quantity_decimal = _to_decimal_string(from_base(int(recipe.output_qty or 0), output_uom, output_dimension))

    items = []
    for ri in db.query(RecipeItem).filter(RecipeItem.recipe_id == recipe.id).order_by(RecipeItem.sort_order).all():
        it = db.get(Item, ri.item_id)
        item_uom = _resolve_uom_for_item(it) if it else "ea"
        item_dimension = it.dimension if it else "count"
        quantity_decimal = _to_decimal_string(from_base(int(ri.qty_required or 0), item_uom, item_dimension))
        items.append(
            {
                "id": ri.id,
                "item_id": ri.item_id,
                "quantity_decimal": quantity_decimal,
                "uom": item_uom,
                "optional": bool(ri.is_optional),
                "sort": ri.sort_order,
                "item": None
                if not it
                else {
                    "id": it.id,
                    "name": it.name,
                    "uom": it.uom,
                    "qty_stored": it.qty_stored,
                },
            }
        )

    return {
        "id": recipe.id,
        "name": recipe.name,
        "code": recipe.code,
        "output_item_id": recipe.output_item_id,
        "quantity_decimal": output_quantity_decimal,
        "uom": output_uom,
        "archived": bool(recipe.archived),
        "notes": recipe.notes,
        "items": items,
        "output_item": None
        if not output_item
        else {
            "id": output_item.id,
            "name": output_item.name,
            "uom": output_item.uom,
            "qty_stored": output_item.qty_stored,
        },
    }


@router.get("")
async def list_recipes(
    db: Session = Depends(get_session),
    _token: str = Depends(require_token_ctx),
    _state: AppState = Depends(get_state),
):
    rs = db.query(Recipe).all()
    out = []
    for r in rs:
        output_item = db.get(Item, r.output_item_id) if r.output_item_id else None
        output_uom = _resolve_uom_for_item(output_item) if output_item else "ea"
        output_dimension = output_item.dimension if output_item else "count"
        out.append(
            {
                "id": r.id,
                "name": r.name,
                "code": r.code,
                "output_item_id": r.output_item_id,
                "quantity_decimal": _to_decimal_string(from_base(int(r.output_qty or 0), output_uom, output_dimension)),
                "uom": output_uom,
                "archived": bool(r.archived),
                "notes": r.notes,
            }
        )
    return out


@router.get("/{rid}")
async def get_recipe(
    rid: int,
    db: Session = Depends(get_session),
    _token: str = Depends(require_token_ctx),
    _state: AppState = Depends(get_state),
):
    r = db.get(Recipe, rid)
    if not r:
        raise HTTPException(404, "recipe not found")
    return _serialize_recipe_detail(db, r)


@router.post("")
async def create_recipe(
    req: Request,
    raw: dict = Body(...),
    db: Session = Depends(get_session),
    _writes: None = Depends(require_writes),
    _token: str = Depends(require_token_ctx),
    _state: AppState = Depends(get_state),
):
    reject_legacy_qty_keys(raw)
    payload = RecipeCreate(**raw)

    require_owner_commit(req)
    output_item = db.get(Item, payload.output_item_id)
    if not output_item:
        raise HTTPException(404, "output item not found")

    output_qty_base = normalize_quantity_to_base_int(
        quantity_decimal=payload.quantity_decimal,
        uom=payload.uom,
        dimension=output_item.dimension,
    )
    if output_qty_base <= 0:
        raise HTTPException(status_code=400, detail="quantity_decimal must be > 0")

    recipe = Recipe(
        name=payload.name,
        code=payload.code,
        output_item_id=payload.output_item_id,
        output_qty=output_qty_base,
        archived=bool(payload.archived),
        notes=payload.notes,
    )
    db.add(recipe)
    db.flush()

    for idx, it in enumerate(payload.items or []):
        item = db.get(Item, it.item_id)
        if not item:
            raise HTTPException(status_code=404, detail=f"item_not_found:{it.item_id}")
        qty_required_base = normalize_quantity_to_base_int(
            quantity_decimal=it.quantity_decimal,
            uom=it.uom,
            dimension=item.dimension,
        )
        if qty_required_base <= 0:
            raise HTTPException(status_code=400, detail="quantity_decimal must be > 0")
        db.add(
            RecipeItem(
                recipe_id=recipe.id,
                item_id=it.item_id,
                qty_required=qty_required_base,
                is_optional=it.optional,
                sort_order=it.sort or idx,
            )
        )
    db.commit()
    db.refresh(recipe)
    _append_recipe_journal({
        "type": "recipe.create",
        "recipe_id": int(recipe.id),
        "recipe_name": recipe.name,
    })
    return _serialize_recipe_detail(db, recipe)


@router.put("/{rid}")
async def update_recipe(
    rid: int,
    req: Request,
    raw: dict = Body(...),
    db: Session = Depends(get_session),
    _writes: None = Depends(require_writes),
    _token: str = Depends(require_token_ctx),
    _state: AppState = Depends(get_state),
):
    reject_legacy_qty_keys(raw)
    payload = RecipeUpdate(**raw)

    require_owner_commit(req)
    recipe = db.get(Recipe, rid)
    if not recipe:
        raise HTTPException(404, "recipe not found")

    if payload.name is not None:
        recipe.name = payload.name
    if payload.code is not None:
        recipe.code = payload.code
    if payload.output_item_id is not None:
        recipe.output_item_id = payload.output_item_id

    output_item = db.get(Item, recipe.output_item_id) if recipe.output_item_id else None
    if not output_item:
        raise HTTPException(404, "output item not found")

    quantity_decimal = payload.quantity_decimal if payload.quantity_decimal is not None else _to_decimal_string(
        from_base(int(recipe.output_qty or 0), _resolve_uom_for_item(output_item), output_item.dimension)
    )
    output_uom = payload.uom if payload.uom is not None else _resolve_uom_for_item(output_item)
    recipe.output_qty = normalize_quantity_to_base_int(
        quantity_decimal=quantity_decimal,
        uom=output_uom,
        dimension=output_item.dimension,
    )

    if payload.archived is not None:
        recipe.archived = bool(payload.archived)
    if payload.notes is not None:
        recipe.notes = payload.notes

    db.query(RecipeItem).filter(RecipeItem.recipe_id == rid).delete()
    for idx, it in enumerate(payload.items or []):
        item = db.get(Item, it.item_id)
        if not item:
            raise HTTPException(status_code=404, detail=f"item_not_found:{it.item_id}")
        qty_required_base = normalize_quantity_to_base_int(
            quantity_decimal=it.quantity_decimal,
            uom=it.uom,
            dimension=item.dimension,
        )
        if qty_required_base <= 0:
            raise HTTPException(status_code=400, detail="quantity_decimal must be > 0")
        db.add(
            RecipeItem(
                recipe_id=rid,
                item_id=it.item_id,
                qty_required=qty_required_base,
                is_optional=it.optional,
                sort_order=it.sort or idx,
            )
        )

    db.commit()
    db.refresh(recipe)
    _append_recipe_journal({
        "type": "recipe.update",
        "recipe_id": int(recipe.id),
        "recipe_name": recipe.name,
    })
    return _serialize_recipe_detail(db, recipe)


@router.delete("/{recipe_id}")
async def delete_recipe(
    recipe_id: int,
    req: Request,
    db: Session = Depends(get_session),
    _writes: None = Depends(require_writes),
    _token: str = Depends(require_token_ctx),
    _state: AppState = Depends(get_state),
):
    require_owner_commit(req)
    r = db.get(Recipe, recipe_id)
    if not r:
        raise HTTPException(status_code=404, detail="Not Found")
    db.query(ManufacturingRun).filter(ManufacturingRun.recipe_id == recipe_id).update(
        {ManufacturingRun.recipe_id: None}, synchronize_session=False
    )
    db.query(RecipeItem).filter(RecipeItem.recipe_id == recipe_id).delete()
    db.delete(r)
    db.commit()
    _append_recipe_journal(
        {
            "type": "recipe.delete",
            "recipe_id": int(recipe_id),
            "recipe_name": getattr(r, "name", None),
        }
    )
    return {"ok": True, "deleted": recipe_id}


if sys.version_info < (3, 11):
    pass
