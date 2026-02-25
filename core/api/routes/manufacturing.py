# SPDX-License-Identifier: AGPL-3.0-or-later
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from core.api.schemas.manufacturing import ManufacturingRunRequest, parse_run_request
from core.appdb.engine import get_session
from core.appdb.ledger import InsufficientStock
from core.appdb.models import Item, Recipe
from core.config.writes import require_writes
from core.manufacturing.service import execute_run_txn, format_shortages, validate_run
from core.metrics.metric import default_unit_for, normalize_quantity_to_base_int
from core.policy.guard import require_owner_commit
from tgc.security import require_token_ctx
from tgc.state import AppState, get_state

router = APIRouter(prefix="/manufacturing", tags=["manufacturing"])
public_router = APIRouter(tags=["manufacturing"])
logger = logging.getLogger(__name__)


def _journals_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if not root:
        root = os.path.expanduser("~/.local/share")
    d = Path(root) / "BUSCore" / "app" / "data" / "journals"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _mf_journal_path() -> Path:
    return _journals_dir() / "manufacturing.jsonl"


def _parse_iso_utc(ts: str) -> datetime:
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _load_recent_runs(days: int) -> list[dict]:
    p = _mf_journal_path()
    if not p.exists():
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=int(days))
    runs: list[dict] = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue

            ts_val = obj.get("timestamp")
            dt = None
            if ts_val is not None:
                try:
                    dt = _parse_iso_utc(str(ts_val))
                except Exception:
                    dt = None
            if dt is None and obj.get("ts") is not None:
                try:
                    dt = datetime.fromtimestamp(float(obj.get("ts")), tz=timezone.utc)
                except Exception:
                    dt = None
            if dt is None:
                continue

            if dt >= cutoff:
                obj.setdefault("timestamp", dt.isoformat())
                obj["_ts"] = dt.isoformat()
                runs.append(obj)

    runs.sort(key=lambda x: x.get("_ts", ""), reverse=True)
    return runs


def _map_shortages(shortages: Iterable[dict]) -> list[dict]:
    return [
        {
            "component": int(s.get("item_id")) if s.get("item_id") is not None else None,
            "required": int(s.get("required", 0)),
            "available": int(s.get("available", s.get("on_hand", 0))),
        }
        for s in shortages
    ]


def _resolve_recipe_name(db: Session, recipe_id: int | None) -> str | None:
    if recipe_id is None:
        return None
    rec = db.get(Recipe, int(recipe_id))
    if rec is not None and getattr(rec, "name", None):
        return rec.name
    return None


def _record_failed_run(
    db: Session, body: ManufacturingRunRequest, output_item_id: int | None, shortages: list[dict]
):
    from core.appdb.models_recipes import ManufacturingRun

    item = db.get(Item, int(output_item_id or getattr(body, "output_item_id", 0) or 0))
    dimension = getattr(item, "dimension", None) or "count"
    output_qty_base = int(
        normalize_quantity_to_base_int(
            quantity_decimal=str(getattr(body, "quantity_decimal", "0")),
            uom=str(getattr(body, "uom", "ea")),
            dimension=dimension,
        )
    )

    run = ManufacturingRun(
        recipe_id=getattr(body, "recipe_id", None),
        output_item_id=output_item_id or getattr(body, "output_item_id", None),
        output_qty=output_qty_base,
        status="failed_insufficient_stock",
        notes=getattr(body, "notes", None),
        meta=json.dumps({"shortages": shortages}),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _shortage_detail(shortages: list[dict], run_id: int | None) -> dict:
    return {
        "error": "insufficient_stock",
        "message": "Insufficient stock for required components.",
        "shortages": _map_shortages(shortages),
        "run_id": run_id,
    }






def _reject_legacy_qty_keys(payload: dict) -> None:
    bad = [k for k in ("qty", "qty_base", "quantity_int", "quantity", "output_qty") if k in payload]
    if bad:
        raise HTTPException(status_code=400, detail={"error": "legacy_quantity_keys_forbidden", "keys": bad})

@public_router.post("/manufacture")
async def canonical_manufacture(
    req: Request,
    raw_body: Any = Body(...),
    db: Session = Depends(get_session),
    _writes: None = Depends(require_writes),
    _token: str = Depends(require_token_ctx),
    _state: AppState = Depends(get_state),
):
    require_owner_commit(req)

    if isinstance(raw_body, list):
        raise HTTPException(status_code=400, detail="single run only")
    if not isinstance(raw_body, dict):
        raise HTTPException(status_code=400, detail="invalid payload")
    payload = dict(raw_body)
    _reject_legacy_qty_keys(payload)
    if "quantity_decimal" not in payload:
        raise HTTPException(status_code=400, detail="quantity_decimal_required")
    if "uom" not in payload:
        raise HTTPException(status_code=400, detail="uom_required")

    body: ManufacturingRunRequest = parse_run_request(payload)
    return await _execute_manufacture(body, db)


async def _execute_manufacture(body: ManufacturingRunRequest, db: Session):
    output_item_id: int | None = getattr(body, "output_item_id", None)

    recipe: Recipe | None = None
    if getattr(body, "recipe_id", None) is not None:
        recipe = db.get(Recipe, body.recipe_id)
        if not recipe:
            raise HTTPException(status_code=404, detail="Recipe not found")
        if recipe.archived:
            raise HTTPException(status_code=400, detail="Recipe is archived")
        if not recipe.output_item_id:
            raise HTTPException(status_code=400, detail="Recipe has no output item")
        if recipe.output_qty <= 0:
            raise HTTPException(status_code=400, detail="Recipe has invalid output quantity")
        output_item_id = recipe.output_item_id

    try:
        output_item_id, required_components, output_qty_base, shortages = validate_run(db, body)
        if shortages:
            run = _record_failed_run(db, body, output_item_id, shortages)
            raise HTTPException(status_code=400, detail=_shortage_detail(shortages, run.id))
        result = execute_run_txn(db, body, output_item_id, required_components, output_qty_base)
        recipe_name = _resolve_recipe_name(db, getattr(body, "recipe_id", None))
        try:
            append_mfg_journal(
                {
                    "type": "manufacturing.run",
                    "recipe_id": int(body.recipe_id) if getattr(body, "recipe_id", None) is not None else None,
                    "recipe_name": recipe_name,
                    "output_item_id": int(output_item_id) if output_item_id is not None else None,
                    "output_qty_base": int(output_qty_base),
                }
            )
        except Exception:
            pass
        return {
            "ok": True,
            "status": "completed",
            "run_id": result["run"].id,
            "output_unit_cost_cents": result["output_unit_cost_cents"],
        }
    except InsufficientStock as exc:
        db.rollback()
        shortages = format_shortages(exc.shortages)
        run = _record_failed_run(db, body, output_item_id, shortages)
        raise HTTPException(status_code=400, detail=_shortage_detail(shortages, run.id))
    except HTTPException as exc:
        db.rollback()
        detail = exc.detail

        if isinstance(detail, dict) and detail.get("error") == "insufficient_stock":
            raise

        shortages: list[dict] | None = None
        if isinstance(detail, dict) and detail.get("shortages"):
            shortages = format_shortages(detail.get("shortages", []))

        if shortages is not None:
            run = _record_failed_run(db, body, output_item_id, shortages)
            raise HTTPException(status_code=400, detail=_shortage_detail(shortages, run.id))
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail={"status": "failed_error"})

@router.post("/run")
async def run_manufacturing_wrapper(
    req: Request,
    raw_body: Any = Body(...),
    db: Session = Depends(get_session),
    _writes: None = Depends(require_writes),
    _token: str = Depends(require_token_ctx),
    _state: AppState = Depends(get_state),
):
    if isinstance(raw_body, list):
        raise HTTPException(status_code=400, detail="single run only")
    if not isinstance(raw_body, dict):
        raise HTTPException(status_code=400, detail="invalid payload")
    payload = dict(raw_body)
    if "output_qty" in payload and "quantity_decimal" not in payload:
        payload["quantity_decimal"] = str(payload.pop("output_qty"))
    if "quantity" in payload and "quantity_decimal" not in payload:
        payload["quantity_decimal"] = str(payload.pop("quantity"))
    elif "quantity" in payload:
        payload.pop("quantity")
    if "uom" not in payload:
        item_id = payload.get("output_item_id")
        if item_id is None and payload.get("recipe_id") is not None:
            recipe = db.get(Recipe, int(payload["recipe_id"]))
            item_id = getattr(recipe, "output_item_id", None)
        item = db.get(Item, int(item_id)) if item_id is not None else None
        dimension = getattr(item, "dimension", None) or "count"
        payload["uom"] = default_unit_for(dimension)
    body = await canonical_manufacture(req=req, raw_body=payload, db=db, _writes=_writes, _token=_token, _state=_state)
    return JSONResponse(content=body, headers={"X-BUS-Deprecation": "/app/manufacture"})


def _append_manufacturing_journal(entry: dict) -> None:
    try:
        entry = dict(entry)
        entry.setdefault("timestamp", datetime.utcnow().isoformat() + "Z")
        p = _journals_dir() / "manufacturing.jsonl"
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, separators=(",", ":")) + "\n")
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to append manufacturing journal entry")


def append_mfg_journal(entry: dict) -> None:
    _append_manufacturing_journal(entry)


@router.get("/runs")
async def list_runs(days: int = Query(30, ge=1, le=365)):
    return {"runs": _load_recent_runs(days)}


@router.get("/history")
async def list_runs_alias(days: int = Query(30, ge=1, le=365)):
    return {"runs": _load_recent_runs(days)}


__all__ = ["router", "public_router"]
