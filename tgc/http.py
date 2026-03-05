# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Generator

import asyncio

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.staticfiles import StaticFiles

from core.api.routes.items import router as items_router
from core.api.routes.manufacturing import router as manufacturing_router
from core.api.routes.recipes import router as recipes_router
from core.api.routes.ledger_api import router as ledger_router
from core.api.utils.devguard import require_dev
from core.appdb.engine import DB_PATH as DB_FILE, get_engine, get_session
from core.appdb.ensure import DB_PATH as ACTIVE_DB_PATH, ensure_schema
from core.appdb.paths import ui_dir
from core.appdb.migrate import ensure_vendors_flags
from core.config.paths import APP_DIR, BUS_ROOT, DATA_DIR, JOURNALS_DIR
from core.config.writes import require_writes
from core.services.capabilities import registry
from core.services.capabilities.registry import MANIFEST_PATH
from core.version import VERSION
from tgc.security import set_session_cookie as attach_session_cookie, require_token_ctx
from tgc.settings import Settings
from tgc.state import AppState, get_state, init_state
from datetime import datetime, timezone

# ---- Runtime guard: supported Python versions (FastAPI/Starlette not ready for 3.14 yet)
if not ((3, 11) <= sys.version_info[:2] <= (3, 13)):
    raise SystemExit(
        f"BUS Core requires Python 3.11–3.13. Detected {sys.version_info.major}.{sys.version_info.minor}. "
        "Please install a supported version and recreate your virtualenv."
    )

# Strict imports - Fail fast if routers have syntax errors
from core.api.routes.vendors import router as vendors_router


REPO_ROOT = Path(__file__).resolve().parents[1]
UI_DIR = ui_dir()
EXPORTS_DIR = APP_DIR / "exports"
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
DEV_MODE = os.getenv("BUS_DEV", "0") == "1"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    FastAPI/Starlette requires an *async* contextmanager for lifespan.
    Initialize AppState on startup; attempt graceful teardown on shutdown.
    """

    settings = Settings()
    state = init_state(settings)
    app.state.app_state = state
    _run_startup_migrations()
    try:
        yield
    finally:
        # best-effort cleanup if core exposes close() or async close()
        core = getattr(state, "core", None)
        if core is not None:
            close = getattr(core, "close", None)
            if callable(close):
                try:
                    rv = close()
                    # If close() returned a coroutine, await it
                    if asyncio.iscoroutine(rv):
                        await rv
                except Exception:
                    # never block shutdown on cleanup errors
                    pass


app = FastAPI(title="BUS Core", version=VERSION, lifespan=lifespan)
try:
    ensure_schema()
except Exception:
    pass

app.mount("/ui", StaticFiles(directory="core/ui", html=True), name="ui")
app.mount("/brand", StaticFiles(directory=str(REPO_ROOT)), name="brand")

# ---- Protected health endpoint for smoke tests
health_router = APIRouter(prefix="/app", tags=["health"])


@health_router.get("/ping")
def app_ping(state=Depends(get_state), _=Depends(require_token_ctx)):
    return {
        "ok": True,
        "server": "bus-core",
        "ts": datetime.now(timezone.utc).isoformat()
    }

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1", "http://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "Content-Type", "X-Session-Token"],
)


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    ico = UI_DIR / "favicon.ico"
    if ico.exists():
        return FileResponse(str(ico))
    return JSONResponse(status_code=204, content=None)


@app.get("/")
def root():
    shell = UI_DIR / "shell.html"
    if shell.exists():
        return RedirectResponse(url="/ui/shell.html", status_code=307)
    return {"ok": True, "message": "BUS Core server running"}


@app.get("/ui", include_in_schema=False)
def ui_root():
    return RedirectResponse(url="/ui/shell.html", status_code=307)


@app.get("/ui/index.html", include_in_schema=False)
def ui_index():
    return RedirectResponse(url="/ui/shell.html", status_code=307)


@app.get("/session/token")
def mint_token(state=Depends(get_state)):
    tok = state.tokens.current()
    # Return the token in JSON so clients can cache and send X-Session-Token
    resp = JSONResponse({"ok": True, "token": tok})
    attach_session_cookie(resp, tok, state.settings)
    return resp

# Debug-friendly variant that returns plain text; useful if some clients behave oddly with JSONResponse.
@app.get("/session/token/plain")
def mint_token_plain(state=Depends(get_state)):
    tok = state.tokens.current()
    # Plain-text variant returns the token string (useful for CLI/dev)
    resp = Response(content=tok, media_type="text/plain; charset=utf-8")
    attach_session_cookie(resp, tok, state.settings)
    return resp


@app.post("/session/rotate")
def rotate_token(state=Depends(get_state), _=Depends(require_token_ctx)):
    tok = state.tokens.rotate()
    resp = JSONResponse({"token": tok})
    attach_session_cookie(resp, tok, state.settings)
    return resp


def _health_basic() -> Dict[str, Any]:
    return {"ok": True, "version": VERSION}


def _health_detailed() -> Dict[str, Any]:
    require_dev()
    return {"ok": True, "version": VERSION, "mode": "dev"}


@app.get("/health")
async def health() -> Dict[str, Any]:
    return _health_basic()


if DEV_MODE:
    @app.get("/health/detailed")
    async def health_detailed() -> Dict[str, Any]:
        return _health_detailed()


# ---- DB helpers ----

def _ensure_schema_upgrades(db: Session) -> None:
    def _col_exists(table: str, col: str) -> bool:
        rows = db.execute(text(f"PRAGMA table_info('{table}')")).fetchall()
        return any(r[1] == col for r in rows)

    def _ensure_column(table: str, column: str, ddl: str) -> None:
        if not _col_exists(table, column):
            db.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))

    if not _col_exists("vendors", "role"):
        db.execute(text("ALTER TABLE vendors ADD COLUMN role TEXT DEFAULT 'contact'"))
    if not _col_exists("vendors", "kind"):
        db.execute(text("ALTER TABLE vendors ADD COLUMN kind TEXT DEFAULT 'org'"))
    if not _col_exists("vendors", "organization_id"):
        db.execute(text("ALTER TABLE vendors ADD COLUMN organization_id INTEGER"))
    if not _col_exists("vendors", "meta"):
        db.execute(text("ALTER TABLE vendors ADD COLUMN meta TEXT"))

    _ensure_column("items", "item_type", "item_type TEXT DEFAULT 'product'")
    _ensure_column("items", "location", "location TEXT")

    db.execute(text("UPDATE vendors SET role='vendor' WHERE role IS NULL"))
    db.execute(text("UPDATE vendors SET kind='org' WHERE kind IS NULL"))
    db.execute(text("UPDATE vendors SET meta='{}' WHERE meta IS NULL OR trim(meta)=''"))
    db.execute(text("UPDATE items SET item_type='product' WHERE item_type IS NULL OR trim(item_type)=''"))

    db.execute(text("CREATE INDEX IF NOT EXISTS vendors_role_idx ON vendors(role)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS vendors_kind_idx ON vendors(kind)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS vendors_org_idx  ON vendors(organization_id)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS items_item_type_idx ON items(item_type)"))

    try:
        idx_list = db.execute(text("PRAGMA index_list('vendors')")).fetchall()
        for row in idx_list:
            idx_name = row[1]
            is_unique = bool(row[2])
            if not is_unique:
                continue
            cols = db.execute(text(f"PRAGMA index_info('{idx_name}')")).fetchall()
            col_names = [c[2] for c in cols]
            if len(col_names) == 1 and col_names[0] == "name":
                db.execute(text(f'DROP INDEX IF EXISTS "{idx_name}"'))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_vendors_name ON vendors(name)"))
    except Exception:
        db.execute(text("DROP INDEX IF EXISTS ix_vendors_name"))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_vendors_name ON vendors(name)"))

    db.commit()


def _run_startup_migrations() -> None:
    ensure_vendors_flags(get_engine())
    db = next(get_session())
    try:
        _ensure_schema_upgrades(db)
    finally:
        db.close()


def get_db() -> Generator[Session, None, None]:
    db_gen = get_session()
    db = next(db_gen)
    try:
        yield db
    finally:
        db.close()


def _db_conn() -> sqlite3.Connection:
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_FILE), timeout=30)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA journal_mode=WAL")
    except sqlite3.DatabaseError:
        pass
    con.execute("PRAGMA foreign_keys=ON")
    return con


mfg_router = APIRouter(prefix="/app")


@mfg_router.post("/inventory/run")
async def inventory_run(
    body: Dict[str, Any],
    _token: str = Depends(require_token_ctx),
    _writes: None = Depends(require_writes),
    _state: AppState = Depends(get_state),
):
    inputs = {int(k): float(v) for k, v in (body.get("inputs") or {}).items()}
    outputs = {int(k): float(v) for k, v in (body.get("outputs") or {}).items()}
    ids = set(inputs) | set(outputs)

    deltas: Dict[int, float] = {}
    for iid in ids:
        deltas[iid] = outputs.get(iid, 0.0) - inputs.get(iid, 0.0)

    with _db_conn() as con:
        existing: set[int] = set()
        if ids:
            placeholders = ",".join("?" * len(ids))
            query = f"SELECT id FROM items WHERE id IN ({placeholders})"
            rows = con.execute(query, list(ids)).fetchall()
            existing = {int(row["id"]) for row in rows}
        missing = sorted(iid for iid in ids if iid not in existing)
        if missing:
            raise HTTPException(status_code=400, detail={"error": "Invalid IDs", "missing_items": missing})

        cur = con.cursor()
        try:
            cur.execute("BEGIN")
            for iid, delta in deltas.items():
                cur.execute("UPDATE items SET qty_stored = COALESCE(qty_stored, 0) + ? WHERE id = ?", (delta, iid))
            con.commit()
        except Exception:
            con.rollback()
            raise

    snapshot_version = int(time.time())
    journal_path = JOURNALS_DIR / "inventory.jsonl"
    record = {
        "ts": snapshot_version,
        "inputs": inputs,
        "outputs": outputs,
        "deltas": deltas,
        "note": body.get("note"),
        "snapshot_version": snapshot_version,
    }
    try:
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        with journal_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:  # pragma: no cover - best effort logging
        raise HTTPException(
            status_code=500,
            detail={"error": "journal_write_failed", "path": str(journal_path), "message": str(exc)},
        )

    return {"ok": True, "deltas": deltas, "snapshot_version": snapshot_version}


@mfg_router.post("/manufacturing/run")
async def manufacturing_run(
    body: Dict[str, Any],
    token: str = Depends(require_token_ctx),
    _writes: None = Depends(require_writes),
    state: AppState = Depends(get_state),
):
    return await inventory_run(body=body, _token=token, _writes=_writes, _state=state)


@app.get("/app/inventory/ledger")
async def inventory_ledger(
    _token: str = Depends(require_token_ctx),
    _state: AppState = Depends(get_state),
):
    journal_path = JOURNALS_DIR / "inventory.jsonl"
    exists = journal_path.exists()
    lines = []
    if exists:
        try:
            with journal_path.open("r", encoding="utf-8") as handle:
                lines = list(deque(handle, maxlen=200))
        except Exception as exc:
            lines = [f"__read_error__: {exc}"]
    return {
        "BUS_ROOT": str(BUS_ROOT),
        "APP_DIR": str(APP_DIR),
        "DATA_DIR": str(DATA_DIR),
        "JOURNAL_DIR": str(JOURNALS_DIR),
        "inventory_path": str(journal_path),
        "exists": exists,
        "tail": lines,
    }


@app.get("/dev/capabilities")
async def dev_capabilities(_token: str = Depends(require_token_ctx)):
    require_dev()
    manifest = registry.load_manifest(MANIFEST_PATH)
    return manifest


items_router.dependencies = [Depends(require_token_ctx)]
vendors_router.dependencies = [Depends(require_token_ctx)]
recipes_router.dependencies = [Depends(require_token_ctx)]
manufacturing_router.dependencies = [Depends(require_token_ctx)]
ledger_router.dependencies = [Depends(require_token_ctx)]

app.include_router(items_router, prefix="/app")
app.include_router(vendors_router, prefix="/app")
app.include_router(recipes_router, prefix="/app")
app.include_router(manufacturing_router, prefix="/app")
app.include_router(mfg_router)
app.include_router(ledger_router, prefix="/app")
if DEV_MODE:
    from core.api.routes.dev_dbinfo import router as dev_dbinfo_router

    dev_dbinfo_router.dependencies = [Depends(require_token_ctx), Depends(require_dev)]
    app.include_router(dev_dbinfo_router)

app.include_router(health_router)


if __name__ == "__main__":
    import uvicorn

    settings = Settings()
    uvicorn.run(
        "core.api.http:create_app",
        host=settings.host,
        port=settings.port,
        log_level="info",
        factory=True,
    )
