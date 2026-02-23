# SPDX-License-Identifier: AGPL-3.0-or-later
# TGC BUS Core (Business Utility System Core)
# Copyright (C) 2025 True Good Craft
#
# This file is part of TGC BUS Core.
#
# TGC BUS Core is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# TGC BUS Core is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with TGC BUS Core.  If not, see <https://www.gnu.org/licenses/>.

from __future__ import annotations

import asyncio
import base64
import ctypes
import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager
from ctypes import wintypes
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional
from urllib.parse import urlencode

from fastapi import FastAPI
from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.staticfiles import StaticFiles
from starlette.responses import RedirectResponse, Response

import requests
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.status import HTTP_401_UNAUTHORIZED
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.appdb.engine import DB_PATH as DB_FILE, dispose_engine, get_engine, get_session

from core.services.capabilities import registry
from core.services.capabilities.registry import MANIFEST_PATH
from core.policy.guard import require_owner_commit
from core.policy.model import Policy
from core.policy.store import load_policy, save_policy
from core.config.writes import require_writes
from core.plans.commit import commit_local
from core.plans.model import Plan, PlanStatus
from core.plans.preview import preview_plan
from core.plans.store import get_plan, list_plans, save_plan
from core.runtime.core_alpha import CoreAlpha
from core.runtime.policy import PolicyDecision
from core.runtime.probe import PROBE_TIMEOUT_SEC
from core.secrets import SecretError, Secrets
from core.version import VERSION
from core.utils.export import (
    export_db,
    import_preview as _import_preview,
    import_commit as _import_commit,
    list_exports as _list_exports,
    stage_uploaded_backup,
)
from core.journal.inventory import append_inventory
from tgc.bootstrap_fs import DATA, LOGS
from tgc.state import get_state, init_app_state

from pydantic import BaseModel, Field

from core.domain.bootstrap import get_broker
from core.settings.reader_state import (
    get_allowed_local_roots as _reader_roots,
    load_settings as _reader_load,
    save_settings as _reader_save,
    set_allowed_local_roots as _reader_set_roots,
)
from core.reader.api import router as reader_local_router
from core.organizer.api import router as organizer_router
from core.api.utils.devguard import require_dev, is_dev
from core.api.routes import dev as dev_routes
from core.api.routes import transactions as transactions_routes
from core.api.routes import config as config_routes
from core.api.security import _calc_default_allow_writes
from core.api.errors import error_envelope, normalize_http_exc, normalize_validation_err
from core.config.paths import (
    APP_DIR,
    BUS_ROOT,
    DATA_DIR,
    JOURNALS_DIR,
    IMPORTS_DIR,
    DB_URL,
)
from core.appdb.migrate import ensure_vendors_flags
from core.appdb.models import Base
from core.appdb.paths import ui_dir

if os.name == "nt":  # pragma: no cover - windows specific
    from core.broker.pipes import NamedPipeServer
    from core.broker.service import PluginBroker, handle_connection
    from core.win.sandbox import spawn_sandboxed
else:  # pragma: no cover - non-windows fallback
    NamedPipeServer = PluginBroker = handle_connection = spawn_sandboxed = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)


def _load_session_token() -> str:
    return _load_or_create_token()


def _b64u_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _b64u_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _mk_state() -> str:
    """
    Create a per-flow state: base64url(nonce . hmac_sha256(session_token, nonce))
    """

    nonce = secrets.token_urlsafe(16).encode()
    sig = hmac.new(_load_session_token().encode(), nonce, hashlib.sha256).digest()
    return _b64u_encode(nonce + b"." + sig)


def _check_state(state_b64: str) -> bool:
    try:
        blob = _b64u_decode(state_b64)
        nonce, sig = blob.split(b".", 1)
        expected = hmac.new(_load_session_token().encode(), nonce, hashlib.sha256).digest()
        return hmac.compare_digest(sig, expected)
    except Exception:
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    startup_migrations()
    _buscore_writeflag_startup()
    ensure_core_initialized()
    await _auto_index_if_stale()
    await _start_indexer_event()
    try:
        yield
    finally:
        await _stop_indexer_event()


INDEX_LOGGER = logging.getLogger(__name__)


def _index_disabled() -> bool:
    flag = os.environ.get("BUS_DISABLE_INDEX", "").strip().lower()
    return flag in {"1", "true", "yes"}


app = FastAPI(title="BUS Core Alpha", version=VERSION, lifespan=lifespan)

# --- Maintenance / Restore Interlock ---------------------------------------
app.state.maintenance = False
app.state.restore_lock = threading.Lock()

MAINT_ALLOW = {
    "/session/token",
    "/openapi.json",
    "/app/db/import/preview",
    "/app/db/import/commit",
}


@app.exception_handler(HTTPException)
async def _http_exc_handler(request: Request, exc: HTTPException):
    # Dev: return as-is.
    if is_dev():
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    # Prod: sanitize.
    return JSONResponse(status_code=exc.status_code, content=normalize_http_exc(exc.detail))


@app.exception_handler(RequestValidationError)
async def _validation_exc_handler(request: Request, exc: RequestValidationError):
    if is_dev():
        return JSONResponse(status_code=400, content={"detail": exc.errors()})
    return JSONResponse(status_code=400, content=normalize_validation_err(exc))


@app.exception_handler(Exception)
async def _unhandled_exc_handler(request: Request, exc: Exception):
    try:
        log(
            f'[error] req="{getattr(request.state, "req_id", "-")}" '
            f'path="{request.url.path}" class="{exc.__class__.__name__}"'
        )
    except Exception:
        pass
    return JSONResponse(status_code=500, content=error_envelope("internal_error"))


CORRELATION_HEADER = "X-Request-ID"


@app.middleware("http")
async def _correlation(request: Request, call_next):
    req_id = request.headers.get(CORRELATION_HEADER) or uuid.uuid4().hex[:12]
    request.state.req_id = req_id
    response = await call_next(request)
    response.headers[CORRELATION_HEADER] = req_id
    return response


@app.middleware("http")
async def maintenance_guard(request: Request, call_next):
    if getattr(request.app.state, "maintenance", False):
        if request.url.path not in MAINT_ALLOW:
            return JSONResponse({"detail": {"error": "maintenance"}}, status_code=503)
    return await call_next(request)

# ---------------------------------------------------------------------------


UI_DIR = ui_dir()
# Mount brand to the repo root so Flat-Dark.png / Glow-Hero.png are reachable
REPO_ROOT = Path(__file__).resolve().parents[2]

# --- BEGIN UI MOUNT ---
app.mount("/ui", StaticFiles(directory=UI_DIR), name="ui")
app.mount("/brand", StaticFiles(directory=str(REPO_ROOT)), name="brand")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(REPO_ROOT / "Flat-Dark.png", media_type="image/png")


@app.get("/")
def root():
    return RedirectResponse(url="/ui/shell.html", status_code=307)
# --- END UI MOUNT ---

UI_STATIC_DIR = UI_DIR


def _ensure_schema_upgrades(db: Session) -> None:
    def _col_exists(table: str, col: str) -> bool:
        rows = db.execute(text(f"PRAGMA table_info('{table}')")).fetchall()
        return any(r[1] == col for r in rows)  # r[1] = column name

    def _ensure_column(table: str, column: str, ddl: str) -> None:
        if not _col_exists(table, column):
            db.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))

    # vendors: additive columns
    if not _col_exists("vendors", "role"):
        db.execute(text("ALTER TABLE vendors ADD COLUMN role TEXT DEFAULT 'vendor'"))
    if not _col_exists("vendors", "kind"):
        db.execute(text("ALTER TABLE vendors ADD COLUMN kind TEXT DEFAULT 'org'"))
    if not _col_exists("vendors", "organization_id"):
        db.execute(text("ALTER TABLE vendors ADD COLUMN organization_id INTEGER"))
    if not _col_exists("vendors", "meta"):
        db.execute(text("ALTER TABLE vendors ADD COLUMN meta TEXT"))

    # items: additive column
    _ensure_column("items", "item_type", "item_type TEXT DEFAULT 'product'")
    _ensure_column("items", "location", "location TEXT")

    # Backfill (idempotent)
    db.execute(text("UPDATE vendors SET role='vendor' WHERE role IS NULL"))
    db.execute(text("UPDATE vendors SET kind='org' WHERE kind IS NULL"))
    db.execute(text("UPDATE vendors SET meta='{}' WHERE meta IS NULL OR trim(meta)=''"))
    db.execute(text("UPDATE items SET item_type='product' WHERE item_type IS NULL OR trim(item_type)=''"))

    # Helpful indexes (idempotent)
    db.execute(text("CREATE INDEX IF NOT EXISTS vendors_role_idx ON vendors(role)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS vendors_kind_idx ON vendors(kind)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS vendors_org_idx  ON vendors(organization_id)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS items_item_type_idx ON items(item_type)"))

    # ---- ensure vendors.name is NOT unique (unified Vendors/Contacts table) ----
    # Drop any unique index on vendors(name), then create a non-unique index.
    try:
        idx_list = db.execute(text("PRAGMA index_list('vendors')")).fetchall()
        for row in idx_list:
            # PRAGMA index_list columns: seq, name, unique, origin, partial
            idx_name = row[1]
            is_unique = bool(row[2])
            if not is_unique:
                continue
            cols = db.execute(text(f"PRAGMA index_info('{idx_name}')")).fetchall()
            col_names = [c[2] for c in cols]  # seqno, cid, name
            if len(col_names) == 1 and col_names[0] == "name":
                db.execute(text(f'DROP INDEX IF EXISTS "{idx_name}"'))
        # Ensure a non-unique index exists for performance
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_vendors_name ON vendors(name)"))
    except Exception:
        # As a fallback, try the common SQLAlchemy-generated name directly
        db.execute(text("DROP INDEX IF EXISTS ix_vendors_name"))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_vendors_name ON vendors(name)"))

    db.commit()


def startup_migrations():
    engine = get_engine()
    # Ensure all declared tables exist before running additive patches.
    Base.metadata.create_all(bind=engine)
    ensure_vendors_flags(engine)
    db = next(get_session())
    try:
        _ensure_schema_upgrades(db)
    finally:
        db.close()


def get_db(request: Request) -> Generator[Session, None, None]:
    if getattr(request.app.state, "maintenance", False):
        raise HTTPException(status_code=503, detail={"error": "maintenance"})

    db_gen = get_session()
    db = next(db_gen)
    try:
        yield db
    finally:
        db.close()


async def _nocache_ui(request: Request, call_next):
    resp = await call_next(request)
    if os.environ.get("BUS_ROOT") and request.url.path.startswith("/ui/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


app.add_middleware(BaseHTTPMiddleware, dispatch=_nocache_ui)

PUBLIC_PATHS = {
    "/",
    "/session/token",
    "/favicon.ico",
    "/health",
    "/openapi.json",
    "/docs",
    "/docs/oauth2-redirect",
}
PUBLIC_PREFIXES = (
    "/ui/",
    "/session/",
    # "/dev/" removed to enforce middleware auth on dev routes
    "/brand/",
    "/favicon.ico",
)


def _buscore_writeflag_startup() -> None:
    app.state.allow_writes = _calc_default_allow_writes()


def ensure_core_initialized():
    if CORE is None:
        build_app()


@app.get("/dev/paths")
def dev_paths():
    from core.config import paths

    return {
        **{
            k: str(getattr(paths, k))
            for k in [
                "BUS_ROOT",
                "APP_DIR",
                "DATA_DIR",
                "JOURNALS_DIR",
                "IMPORTS_DIR",
                "UI_DIR",
            ]
        },
        "DB_PATH": str(DB_FILE),
    }


@app.get("/ui", include_in_schema=False)
def ui_root():
    return RedirectResponse(url="/ui/shell.html", status_code=307)


@app.get("/ui/index.html", include_in_schema=False)
def ui_index():
    return RedirectResponse(url="/ui/shell.html", status_code=307)


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "version": VERSION}


def _health_details_payload() -> Dict[str, Any]:
    policy_dict: Dict[str, Any] = {}
    try:
        if CORE and hasattr(CORE, "policy") and hasattr(CORE.policy, "as_dict"):
            policy_dict = CORE.policy.as_dict()
    except NameError:
        policy_dict = {}

    rid = None
    try:
        rid = getattr(CORE, "run_id", None)
    except NameError:
        rid = None
    try:
        rid = rid or RUN_ID
    except NameError:
        pass
    rid = str(rid or uuid.uuid4())

    return {
        "ok": True,
        "version": VERSION,
        "policy": policy_dict,
        "run-id": rid,
    }


@app.get("/health/detailed")
def health_detailed() -> Dict[str, Any]:
    require_dev()
    return _health_details_payload()


@app.get("/")
def _root():
    return RedirectResponse(url="/ui/shell.html")


TOKEN_FILE = DATA_DIR / "session_token.txt"


def _load_or_create_token() -> str:
    try:
        if TOKEN_FILE.exists():
            return TOKEN_FILE.read_text(encoding="utf-8").strip()
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        tok = secrets.token_urlsafe(32)
        TOKEN_FILE.write_text(tok, encoding="utf-8")
        return tok
    except Exception:
        return secrets.token_urlsafe(32)


@app.get("/session/token")
def session_token(request: Request):
    state = get_state(request)
    tok = state.tokens.current()
    global SESSION_TOKEN
    SESSION_TOKEN = tok
    resp = JSONResponse({"token": tok})
    resp.set_cookie(
        key=state.settings.session_cookie_name,
        value=tok,
        httponly=True,
        samesite=(state.settings.same_site or "lax").lower(),
        secure=bool(state.settings.secure_cookie),
        path="/",
    )
    return resp

CORE: CoreAlpha | None = None
RUN_ID: str = ""
SESSION_TOKEN: str = ""
LOG_FILE: Path | None = None
_OAUTH_STATES: Dict[str, Dict[str, Any]] = {}
BACKGROUND_INDEX_TASK: asyncio.Task | None = None
INDEX_STOP_EVENT = threading.Event()
INDEX_PAUSE_EVENT = threading.Event()
INDEX_IDLE_EVENT = threading.Event()
INDEX_IDLE_EVENT.set()
INDEX_LOOP: asyncio.AbstractEventLoop | None = None


def log(msg: str) -> None:
    line = msg.rstrip()
    try:
        print(line, flush=True)
    except Exception:
        pass
    path = LOG_FILE or (LOGS / "core.log")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _dispose_index_handles() -> None:
    try:
        dispose_engine()
    except Exception:
        if is_dev():
            log("[index] pause: engine dispose failed (ignored)")


def pause_indexer(timeout: float = 5.0) -> bool:
    global BACKGROUND_INDEX_TASK
    INDEX_STOP_EVENT.set()
    INDEX_PAUSE_EVENT.set()
    _dispose_index_handles()
    task = BACKGROUND_INDEX_TASK
    if task and not task.done():
        deadline = time.time() + max(timeout, 0)
        while time.time() < deadline:
            if task.done():
                break
            if INDEX_IDLE_EVENT.wait(0.25):
                break
    INDEX_IDLE_EVENT.set()
    return True


def resume_indexer() -> None:
    INDEX_STOP_EVENT.clear()
    INDEX_PAUSE_EVENT.clear()


def stop_indexer(timeout: float = 10.0) -> bool:
    """Signal background indexer to stop and release DB handles."""
    global BACKGROUND_INDEX_TASK
    INDEX_STOP_EVENT.set()
    INDEX_PAUSE_EVENT.set()
    task = BACKGROUND_INDEX_TASK
    loop = INDEX_LOOP
    if task and not task.done() and loop and loop.is_running():
        try:
            loop.call_soon_threadsafe(task.cancel)
        except Exception:
            pass
    _dispose_index_handles()
    deadline = time.time() + max(timeout, 0)
    while time.time() < deadline:
        if INDEX_IDLE_EVENT.wait(0.25):
            break
    INDEX_IDLE_EVENT.set()
    if task and task.done():
        BACKGROUND_INDEX_TASK = None
    return True


def start_indexer(initial_status: Optional[Dict[str, Any]] | None = None) -> None:
    """Start the background indexer task if not already running."""
    global BACKGROUND_INDEX_TASK, INDEX_LOOP
    if _index_disabled():
        INDEX_LOGGER.debug("[index] start skipped (BUS_DISABLE_INDEX)")
        return
    INDEX_STOP_EVENT.clear()
    INDEX_PAUSE_EVENT.clear()
    if BACKGROUND_INDEX_TASK and BACKGROUND_INDEX_TASK.done():
        BACKGROUND_INDEX_TASK = None
    if BACKGROUND_INDEX_TASK and not BACKGROUND_INDEX_TASK.done():
        return

    loop = INDEX_LOOP
    if loop is None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            try:
                loop = asyncio.get_event_loop()
            except Exception:
                loop = None
        INDEX_LOOP = loop
    if loop is None or not loop.is_running():
        return

    status = initial_status
    if status is None:
        try:
            status = _index_status_payload(_broker())
        except Exception as exc:
            if is_dev():
                log(f"[index] start failed: error={type(exc).__name__}")
            return

    def _spawn() -> None:
        global BACKGROUND_INDEX_TASK
        BACKGROUND_INDEX_TASK = asyncio.create_task(_run_background_index(status))

    try:
        loop.call_soon_threadsafe(_spawn)
    except Exception as exc:
        if is_dev():
            log(f"[index] start scheduling failed: error={type(exc).__name__}")


PLUGIN_UI_BASES = [
    REPO_ROOT / "core" / "plugins_builtin",
    REPO_ROOT / "plugins",
    REPO_ROOT / "plugins_user",
]


def _resolve_plugin_ui_path(plugin_id: str, resource: str) -> Path | None:
    safe_plugin = Path(plugin_id.strip("/"))
    if safe_plugin.parts != (plugin_id,) and len(safe_plugin.parts) != 1:
        return None
    relative = Path(resource or "")
    if relative.is_absolute():
        return None
    safe_resource = Path("index.html") if str(relative) == "" else relative
    if any(part in ("..", "") for part in safe_resource.parts if part != ""):
        safe_resource = Path("index.html")
    for base in PLUGIN_UI_BASES:
        ui_root = base / plugin_id / "ui"
        try:
            ui_root_resolved = ui_root.resolve(strict=False)
        except FileNotFoundError:
            continue
        if not ui_root_resolved.exists() or not ui_root_resolved.is_dir():
            continue
        candidate = (ui_root_resolved / safe_resource).resolve(strict=False)
        try:
            candidate.relative_to(ui_root_resolved)
        except ValueError:
            continue
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


@app.middleware("http")
async def _request_log_mw(request: Request, call_next):
    start = time.time()
    response = None
    try:
        response = await call_next(request)
        return response
    finally:
        elapsed_ms = int((time.time() - start) * 1000)
        summary = {
            "path": request.url.path,
            "method": request.method,
            "elapsed_ms": elapsed_ms,
            "run_id": RUN_ID,
            "status": getattr(response, "status_code", 0),
        }
        log(f"[request] {json.dumps(summary, separators=(',', ':'))}")


def _require_core() -> CoreAlpha:
    if CORE is None:
        raise HTTPException(status_code=503, detail="core_not_initialized")
    return CORE


def _extract_token(req: Request) -> str | None:
    # Cookie-only session per SoT
    token = (
        req.cookies.get("bus_session")
        or req.cookies.get("session")
        or req.cookies.get("sessionid")
    )
    return token


def get_session_token(request: Request) -> str | None:
    session = getattr(request.state, "session", None)
    if session:
        return session if isinstance(session, str) else getattr(session, "token", None)
    return _extract_token(request)


def validate_session_token(token: Optional[str]) -> bool:
    if not token:
        return False
    expected = SESSION_TOKEN or _load_or_create_token()
    try:
        return hmac.compare_digest(token, expected)
    except Exception:
        return token == expected


def _require_token(token: Optional[str]) -> None:
    if not token or not validate_session_token(token):
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail={"error": "unauthorized"})


def require_token_ctx(request: Request) -> Dict[str, str]:
    token = get_session_token(request)
    _require_token(token)
    assert token is not None
    return {"token": token}


def require_token(request: Request) -> str:
    token = get_session_token(request)
    _require_token(token)
    assert token is not None
    return token


def require_session_token(request: Request) -> str:
    return require_token(request)


async def _require_session(req: Request):
    token = _extract_token(req)
    if not token:
        return JSONResponse({"error": "unauthorized"}, status_code=HTTP_401_UNAUTHORIZED)
    session = token if validate_session_token(token) else None
    if not session:
        return JSONResponse({"error": "unauthorized"}, status_code=HTTP_401_UNAUTHORIZED)
    req.state.session = session
    return None


@app.middleware("http")
async def session_guard(request: Request, call_next):
    p = request.url.path
    if request.method == "OPTIONS":
        return await call_next(request)
    # Make static UI, session bootstrap, and brand assets public
    if p in PUBLIC_PATHS or any(p.startswith(prefix) for prefix in PUBLIC_PREFIXES):
        return await call_next(request)
    failure = await _require_session(request)
    if failure:
        return failure
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["Accept", "Content-Type"],
)


protected = APIRouter(dependencies=[Depends(require_token_ctx)])
protected.include_router(reader_local_router)
protected.include_router(organizer_router)
from core.api.routes.items import router as items_router
from core.api.routes.vendors import router as vendors_router
from core.api.routes.recipes import router as recipes_router
from core.api.routes.manufacturing import public_router as manufacturing_public_router, router as manufacturing_router
from core.api.routes import logs_api
from core.api.routes.finance_api import router as finance_router
from core.api.routes.ledger_api import public_router as ledger_public_router, router as ledger_router

oauth = APIRouter()


def _broker():
    return get_broker()


class ExportReq(BaseModel):
    password: str


class ImportReq(BaseModel):
    password: str
    path: str


IMPORT_ERROR_CODES = {
    "path_out_of_roots",
    "cannot_read_file",
    "bad_container",
    "decrypt_failed",
    "password_required",
    "incompatible_schema",
}


@protected.post("/app/db/export")
def app_export(req: ExportReq, _writes: None = Depends(require_writes)):
    if not req.password:
        raise HTTPException(status_code=400, detail={"error": "password_required"})
    res = export_db(req.password)
    if not res.get("ok"):
        raise HTTPException(
            status_code=400,
            detail={"error": res.get("error", "export_failed")},
        )
    return res


@protected.get("/app/db/exports")
def app_exports(_writes: None = Depends(require_writes)):
    return {"ok": True, "exports": _list_exports()}


@protected.post("/app/db/import/upload")
async def app_import_upload(
    file: UploadFile = File(...), _w: None = Depends(require_writes)
):
    data = await file.read()
    res = stage_uploaded_backup(file.filename, data)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail={"error": res.get("error", "upload_failed")})
    return res


@protected.post("/app/db/import/preview")
def app_import_preview(req: ImportReq, _w: None = Depends(require_writes)):
    res = _import_preview(req.path, req.password)
    if not res.get("ok"):
        err = res.get("error", "preview_failed")
        if err in IMPORT_ERROR_CODES:
            raise HTTPException(status_code=400, detail={"error": err})
        raise HTTPException(status_code=400, detail={"error": "preview_failed"})
    return res


@protected.post("/app/db/import/commit")
def app_import_commit(req: ImportReq, request: Request, _w: None = Depends(require_writes)):
    app = request.app
    dev = os.environ.get("BUS_DEV") in {"1", "true", "True"}
    _log = lambda s: log(f"[restore] commit: {s}")

    lock = getattr(app.state, "restore_lock", None)
    if lock is not None and not lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail={"error": "restore_in_progress"})

    app.state.maintenance = True
    _log("starting")
    try:
        _log("stopping indexer")
        stop_fn = getattr(app.state, "stop_indexer", None) or stop_indexer
        stop_fn(timeout=10.0)
        _log("indexer stopped")
    except Exception:
        if dev:
            _log("warn: stop_indexer raised (ignored)")

    def _dispose_all():
        state = getattr(request.app, "state", None)
        eng = None
        if state is not None:
            state_db = getattr(state, "db", None)
            eng = getattr(state_db, "engine", None) or getattr(state, "engine", None)
        try:
            if eng is not None and hasattr(eng, "dispose"):
                eng.dispose()
        except Exception:
            pass
        try:
            dispose_engine()
        except Exception:
            pass

    try:
        res = _import_commit(
            req.path,
            req.password,
            dispose_call=_dispose_all,
            dev_mode=dev,
            log_func=_log,
        )
        if not res.get("ok"):
            err = res.get("error", "commit_failed")
            if err in IMPORT_ERROR_CODES:
                raise HTTPException(status_code=400, detail={"error": err, **({"info": res.get("info")} if dev and res.get("info") else {})})
            detail = {"error": "commit_failed"}
            if dev and res.get("info"):
                detail["info"] = res["info"]
            raise HTTPException(status_code=400, detail=detail)
        return res
    finally:
        app.state.maintenance = False
        try:
            start_fn = getattr(app.state, "start_indexer", None) or start_indexer
            start_fn()
        except Exception:
            pass
        try:
            if lock is not None and lock.locked():
                lock.release()
        except Exception:
            pass


# --- Debug: journal info (auth required; does NOT require writes on) ---
@protected.get("/dev/journal/info")
def journal_info(n: int = 5):
    journal_path = JOURNALS_DIR / "inventory.jsonl"
    exists = journal_path.exists()
    lines: List[str] = []
    if exists:
        try:
            from collections import deque

            with journal_path.open("r", encoding="utf-8") as handle:
                lines = list(deque(handle, maxlen=max(1, min(int(n), 200))))
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


class InventoryRun(BaseModel):
    inputs: Dict[int, float] = Field(default_factory=dict)
    outputs: Dict[int, float] = Field(default_factory=dict)
    note: Optional[str] = None


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


@app.post("/app/inventory/run")
def inventory_run(
    body: InventoryRun,
    token: str = Depends(require_token),
    _writes: None = Depends(require_writes),
):
    inputs = {int(k): float(v) for k, v in (body.inputs or {}).items()}
    outputs = {int(k): float(v) for k, v in (body.outputs or {}).items()}
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
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Invalid IDs",
                    "missing_items": missing,
                    "missing_vendors": [],
                },
            )

        cur = con.cursor()
        try:
            cur.execute("BEGIN")
            for iid, delta in deltas.items():
                cur.execute(
                    "UPDATE items SET qty_stored = COALESCE(qty_stored, 0) + ? WHERE id = ?",
                    (delta, iid),
                )
            con.commit()
        except Exception:
            con.rollback()
            raise

    snapshot_version = int(time.time())
    record = {
        "ts": snapshot_version,
        "op": "inventory_run",
        "inputs": inputs,
        "outputs": outputs,
        "deltas": deltas,
        "note": body.note,
        "snapshot_version": snapshot_version,
    }
    _append_inventory(record)

    return {"ok": True, "deltas": deltas, "snapshot_version": snapshot_version}


def _append_inventory(entry: dict) -> None:
    try:
        append_inventory(entry)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to append inventory journal entry")


@protected.get("/dev/ping_plugin")
def dev_ping_plugin():
    """
    Spawns a sandboxed plugin host that connects over a unique pipe,
    performs hello+ping, then exits. Returns {"ok": true} if handshake worked.
    """

    if (
        os.name != "nt"
        or NamedPipeServer is None
        or PluginBroker is None
        or handle_connection is None
        or spawn_sandboxed is None
    ):
        raise HTTPException(status_code=501, detail="windows_only")

    pipe = r"\\.\pipe\buscore-" + str(uuid.uuid4())
    broker = PluginBroker()
    server = NamedPipeServer(pipe)
    server.start(lambda conn: handle_connection(conn, broker))

    cmd = (
        f'"{sys.executable}" -m tgc.plugin_host.main '
        f'--pipe-name "{pipe}" --plugin-id test'
    )

    ph = th = hjob = None
    try:
        ph, th, hjob = spawn_sandboxed(cmd)
        try:
            import win32con  # type: ignore
            import win32event  # type: ignore
            import win32process  # type: ignore
        except Exception as exc:  # pragma: no cover - missing pywin32
            raise HTTPException(status_code=500, detail="win32_runtime_missing") from exc

        wait_rc = win32event.WaitForSingleObject(ph, 5000)
        # Best-effort: stop server; the job will kill the host on close
        server.stop()
        if wait_rc != win32con.WAIT_OBJECT_0:
            raise HTTPException(status_code=504, detail="plugin_timeout")
        exit_code = win32process.GetExitCodeProcess(ph)
        if exit_code != 0:
            raise HTTPException(status_code=500, detail="plugin_failed")
    finally:
        if os.name == "nt":
            try:
                import win32file  # type: ignore
            except Exception:
                win32file = None  # type: ignore
            if "win32file" in locals() and win32file is not None:  # pragma: no cover - windows only
                for handle in (th, ph, hjob):
                    if handle:
                        try:
                            win32file.CloseHandle(handle)
                        except Exception:
                            pass
        server.stop()

    return {"ok": True}


INDEX_STATE_PATH = os.path.join("data", "index_state.json")


def _load_index_state() -> Dict[str, Any]:
    try:
        with open(INDEX_STATE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, dict):
                if not isinstance(data.get("drive"), dict):
                    data["drive"] = {}
                if not isinstance(data.get("local"), dict):
                    data["local"] = {}
                return data
    except Exception:
        pass
    return {"drive": {}, "local": {}}


def _save_index_state(state: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(INDEX_STATE_PATH), exist_ok=True)
    tmp_path = INDEX_STATE_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp_path, INDEX_STATE_PATH)


def compute_local_roots_signature(broker) -> str:
    try:
        roots = broker.service_call("local_fs", "status", {}).get("roots", [])
    except Exception:
        roots = []
    normed = []
    for root in roots:
        if isinstance(root, str):
            normed.append(os.path.normcase(os.path.normpath(root)))
    payload = "|".join(sorted(normed))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _drive_start_page_token(broker) -> Dict[str, Any]:
    try:
        result = broker.service_call("google_drive", "get_start_page_token", {})
    except Exception:
        return {"ok": False, "token": None}
    if not isinstance(result, dict):
        return {"ok": False, "token": None}
    token = result.get("token")
    ok = bool(result.get("ok")) and bool(token)
    return {"ok": ok, "token": token}


def _index_status_payload(broker=None) -> Dict[str, Any]:
    broker = broker or _broker()
    state = _load_index_state()
    if not isinstance(state, dict):
        state = {"drive": {}, "local": {}}

    drive_state = state.get("drive") if isinstance(state.get("drive"), dict) else {}
    local_state = state.get("local") if isinstance(state.get("local"), dict) else {}

    drive_provider = None
    local_provider = None
    if hasattr(broker, "get_provider"):
        try:
            drive_provider = broker.get_provider("google_drive")
        except Exception:
            drive_provider = None
        try:
            local_provider = broker.get_provider("local_fs")
        except Exception:
            local_provider = None
    if drive_provider is None:
        current_drive_token = drive_state.get("token") if isinstance(drive_state, dict) else None
        last_drive_token = current_drive_token
        drive_up_to_date = True
    else:
        drive_token_result = _drive_start_page_token(broker)
        current_drive_token = drive_token_result.get("token")
        last_drive_token = drive_state.get("token") if isinstance(drive_state, dict) else None
        drive_up_to_date = bool(
            drive_token_result.get("ok")
            and current_drive_token
            and last_drive_token
            and current_drive_token == last_drive_token
        )

    if local_provider is None:
        current_sig = local_state.get("roots_sig") if isinstance(local_state, dict) else None
        last_sig = current_sig
        local_up_to_date = True
    else:
        current_sig = compute_local_roots_signature(broker)
        last_sig = local_state.get("roots_sig") if isinstance(local_state, dict) else None
        local_up_to_date = bool(current_sig and last_sig and current_sig == last_sig)

    return {
        "drive": {
            "current_token": current_drive_token,
            "last_token": last_drive_token,
            "up_to_date": drive_up_to_date,
        },
        "local": {
            "current_sig": current_sig,
            "last_sig": last_sig,
            "up_to_date": local_up_to_date,
        },
        "overall_up_to_date": bool(drive_up_to_date and local_up_to_date),
    }


def _catalog_background_scan(broker, source: str, scope: str, label: str) -> bool:
    stream_id = None
    missing = [
        name
        for name in ("catalog_open", "catalog_next", "catalog_close")
        if not hasattr(broker, name)
    ]
    if missing:
        INDEX_LOGGER.debug(
            f"[index] {label}: missing catalog methods; skipping scan"
        )
        return False
    try:
        opened = broker.catalog_open(
            source,
            scope,
            {"recursive": True, "page_size": 500, "fingerprint": False},
        )
        stream_id = opened.get("stream_id") if isinstance(opened, dict) else None
        if not stream_id:
            log(f"[index] {label}: catalog_open failed")
            return False
        total = 0
        while True:
            if INDEX_STOP_EVENT.is_set() or INDEX_PAUSE_EVENT.is_set():
                log(f"[index] {label}: stop requested")
                return False
            page = broker.catalog_next(stream_id, 500, 700)
            if not isinstance(page, dict):
                break
            items = page.get("items")
            if isinstance(items, list):
                total += len(items)
            if page.get("done"):
                break
        log(f"[index] {label}: indexed {total} items")
        return True
    except Exception as exc:
        log(f"[index] {label}: error={type(exc).__name__}")
        return False
    finally:
        if stream_id:
            try:
                broker.catalog_close(stream_id)
            except Exception:
                pass


def _background_index_worker(initial_status: Optional[Dict[str, Any]] = None) -> None:
    INDEX_IDLE_EVENT.clear()
    try:
        if _index_disabled():
            INDEX_LOGGER.debug("[index] background: disabled via BUS_DISABLE_INDEX")
            return
        if INDEX_PAUSE_EVENT.is_set() or INDEX_STOP_EVENT.is_set():
            log("[index] background: pause requested (pre-start)")
            _dispose_index_handles()
            return

        try:
            broker = _broker()
        except Exception as exc:
            log(f"[index] background: broker_unavailable error={type(exc).__name__}")
            return

        if INDEX_STOP_EVENT.is_set() or INDEX_PAUSE_EVENT.is_set():
            log("[index] background: stop requested (pre-start)")
            _dispose_index_handles()
            return

        status = initial_status or _index_status_payload(broker)
        drive_needed = not bool(status.get("drive", {}).get("up_to_date"))
        local_needed = not bool(status.get("local", {}).get("up_to_date"))
        if not drive_needed and not local_needed:
            log("[index] background: already up-to-date")
            return

        log(
            f"[index] background: start drive_needed={drive_needed} local_needed={local_needed}"
        )

        drive_success = True
        local_success = True

        if drive_needed:
            drive_success = _catalog_background_scan(
                broker, "google_drive", "allDrives", "Drive"
            )
        if local_needed:
            local_success = _catalog_background_scan(
                broker, "local_fs", "local_roots", "Local"
            )

        if drive_success and local_success:
            updated = _index_status_payload(broker)
            state = _load_index_state()
            if not isinstance(state, dict):
                state = {"drive": {}, "local": {}}
            changed = False
            drive_token = updated.get("drive", {}).get("current_token")
            local_sig = updated.get("local", {}).get("current_sig")
            if drive_token:
                state.setdefault("drive", {})["token"] = drive_token
                changed = True
            if local_sig:
                state.setdefault("local", {})["roots_sig"] = local_sig
                changed = True
            if changed:
                state["updated_at"] = int(time.time())
                try:
                    _save_index_state(state)
                    log("[index] background: state persisted")
                except Exception as exc:
                    log(f"[index] background: persist_failed error={type(exc).__name__}")
            else:
                log("[index] background: nothing to persist")
        else:
            log(
                f"[index] background: incomplete drive_ok={drive_success} local_ok={local_success}"
            )
    finally:
        _dispose_index_handles()
        INDEX_IDLE_EVENT.set()


async def _run_background_index(initial_status: Optional[Dict[str, Any]] = None) -> None:
    if INDEX_STOP_EVENT.is_set() or INDEX_PAUSE_EVENT.is_set():
        INDEX_IDLE_EVENT.set()
        log("[index] background: paused; skipping run")
        return
    try:
        await asyncio.to_thread(_background_index_worker, initial_status)
    except Exception as exc:
        log(f"[index] background: worker_exception error={type(exc).__name__}")


def _decode_local_id(local_id: str) -> str:
    """Decode a local:<b64url(path)> identifier into an absolute path."""

    try:
        b64 = local_id.split(":", 1)[1]
        pad = "=" * (-len(b64) % 4)
        return base64.urlsafe_b64decode(b64 + pad).decode()
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=400, detail="bad_local_id") from exc


def _allowed_local_path(path: str) -> bool:
    """Return True if the path is within the configured local roots."""

    broker = _broker()
    try:
        settings = broker._catalog._providers["local_fs"]._settings()  # type: ignore[attr-defined]
        roots = [os.path.abspath(p) for p in settings.get("local_roots", [])]
    except Exception:
        roots = []
    ap = os.path.abspath(path)
    return any(os.path.commonpath([ap, root]) == root for root in roots)


def _list_windows_drives() -> List[Dict[str, Any]]:
    drives: List[Dict[str, Any]] = []
    try:
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        letters = [chr(ord("A") + i) for i in range(26) if bitmask & (1 << i)]
        get_drive_type_w = ctypes.windll.kernel32.GetDriveTypeW
        drive_types = {
            0: "unknown",
            1: "invalid",
            2: "removable",
            3: "fixed",
            4: "remote",
            5: "cdrom",
            6: "ramdisk",
        }
        get_volume_information_w = ctypes.windll.kernel32.GetVolumeInformationW
        for letter in letters:
            root = f"{letter}:\\"
            dtype = drive_types.get(get_drive_type_w(root), "unknown")
            label_buf = ctypes.create_unicode_buffer(256)
            fs_buf = ctypes.create_unicode_buffer(256)
            serial = wintypes.DWORD()
            max_comp = wintypes.DWORD()
            flags = wintypes.DWORD()
            try:
                ok = get_volume_information_w(
                    root,
                    label_buf,
                    256,
                    ctypes.byref(serial),
                    ctypes.byref(max_comp),
                    ctypes.byref(flags),
                    fs_buf,
                    256,
                )
                label = label_buf.value if ok else ""
            except Exception:
                label = ""
            drives.append({"path": root, "label": label, "type": dtype})
    except Exception:
        pass
    return drives


def _list_posix_mounts() -> List[Dict[str, Any]]:
    mounts: List[Dict[str, Any]] = []
    try:
        with open("/proc/mounts", "r", encoding="utf-8") as handle:
            seen: set[str] = set()
            for line in handle:
                parts = line.split()
                if len(parts) >= 2:
                    mount_point = parts[1]
                    if mount_point not in seen and (
                        mount_point == "/"
                        or mount_point.startswith("/mnt")
                        or mount_point.startswith("/Volumes")
                    ):
                        seen.add(mount_point)
                        mounts.append({"path": mount_point, "label": "", "type": "mount"})
    except Exception:
        for fallback in ("/", "/mnt", "/Volumes"):
            if os.path.exists(fallback):
                mounts.append({"path": fallback, "label": "", "type": "mount"})
    return mounts


def _with_run_id(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(payload)
    payload.setdefault("run_id", RUN_ID)
    return payload


def _prune_oauth_states() -> None:
    if not _OAUTH_STATES:
        return
    now = time.time()
    expired = [key for key, meta in _OAUTH_STATES.items() if meta.get("expires_at", 0) <= now]
    for key in expired:
        _OAUTH_STATES.pop(key, None)


@app.get("/ui/plugins/{plugin_id}")
@app.get("/ui/plugins/{plugin_id}/{resource_path:path}")
def ui_plugin_asset(plugin_id: str, resource_path: str = "index.html") -> FileResponse:
    path = _resolve_plugin_ui_path(plugin_id, resource_path)
    if not path:
        raise HTTPException(status_code=404, detail="ui_asset_not_found")
    return FileResponse(path)


def _load_google_client() -> tuple[str, str]:
    client_id = Secrets.get("google_drive", "client_id")
    client_secret = Secrets.get("google_drive", "client_secret")
    if not client_id or not client_secret:
        raise ValueError("missing_client")
    return client_id, client_secret


class GoogleStartIn(BaseModel):
    redirect: str | None = None


class GoogleSettingsIn(BaseModel):
    client_id: str | None = None
    client_secret: str | None = None


class GoogleSettingsOut(BaseModel):
    connected: bool
    has_client_id: bool
    client_id_mask: str | None
    has_client_secret: bool


def _mask_secret(value: Optional[str]) -> str | None:
    if not value:
        return None
    return "..." + value[-4:]


@protected.get("/settings/google", response_model=GoogleSettingsOut)
def settings_google_get(response: Response) -> GoogleSettingsOut:
    response.headers["Cache-Control"] = "no-store"

    client_id = Secrets.get("google_drive", "client_id") or ""
    client_secret = Secrets.get("google_drive", "client_secret") or ""
    refresh_token = Secrets.get("google_drive", "oauth_refresh") or ""

    has_client_id = bool(client_id)
    has_client_secret = bool(client_secret)
    connected = bool(refresh_token)

    return GoogleSettingsOut(
        connected=connected,
        has_client_id=has_client_id,
        client_id_mask=_mask_secret(client_id) if has_client_id else None,
        has_client_secret=has_client_secret,
    )


@protected.post("/settings/google")
def settings_google_post(
    payload: GoogleSettingsIn,
    response: Response,
    _writes: None = Depends(require_writes),
) -> Dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"

    updated: List[str] = []
    try:
        if payload.client_id is not None:
            Secrets.set("google_drive", "client_id", payload.client_id)
            updated.append("client_id")
        if payload.client_secret is not None:
            Secrets.set("google_drive", "client_secret", payload.client_secret)
            updated.append("client_secret")
    except SecretError as exc:
        raise HTTPException(status_code=500, detail="secret_store_error") from exc

    if updated:
        log(f"settings.google updated: fields={','.join(updated)}")

    return {"ok": True}


@protected.delete("/settings/google")
def settings_google_delete(
    response: Response, _writes: None = Depends(require_writes)
) -> Dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"

    for key in ("client_id", "client_secret", "oauth_refresh"):
        try:
            Secrets.delete("google_drive", key)
        except SecretError:
            continue

    log("settings.google cleared")
    return {"ok": True}


@protected.get("/settings/reader", response_model=None)
def get_reader_settings() -> Dict[str, Any]:
    return _reader_load()


@protected.post("/settings/reader", response_model=None)
def post_reader_settings(
    payload: Dict[str, Any] = Body(default={}),
    _writes: None = Depends(require_writes),
) -> Dict[str, Any]:  # type: ignore[assignment]
    payload = payload if isinstance(payload, dict) else {}

    if "local_roots" in payload:
        candidate_roots = payload.get("local_roots")
        if isinstance(candidate_roots, list):
            _reader_set_roots(candidate_roots)

    _reader_save(payload)
    return {"ok": True, "settings": _reader_load()}


@protected.post("/catalog/open", response_model=None)
def catalog_open(body: Dict[str, Any], _writes: None = Depends(require_writes)):
    src = body.get("source") if isinstance(body, dict) else None
    scope = body.get("scope") if isinstance(body, dict) else None
    opts = body.get("options") if isinstance(body, dict) else None
    if not src or not scope:
        raise HTTPException(status_code=400, detail="missing source/scope")
    options = opts if isinstance(opts, dict) else {}
    return _broker().catalog_open(src, scope, options)


@protected.post("/catalog/next", response_model=None)
def catalog_next(body: Dict[str, Any], _writes: None = Depends(require_writes)):
    payload = body if isinstance(body, dict) else {}
    sid = payload.get("stream_id")
    max_items = int(payload.get("max_items", 500) or 500)
    time_budget_ms = int(payload.get("time_budget_ms", 700) or 700)
    if not sid:
        raise HTTPException(status_code=400, detail="missing stream_id")
    return _broker().catalog_next(str(sid), max_items, time_budget_ms)


@protected.post("/catalog/close", response_model=None)
def catalog_close(body: Dict[str, Any], _writes: None = Depends(require_writes)):
    payload = body if isinstance(body, dict) else {}
    sid = payload.get("stream_id")
    if not sid:
        raise HTTPException(status_code=400, detail="missing stream_id")
    return _broker().catalog_close(str(sid))


@protected.get("/index/state", response_model=None)
def index_state_get():
    return _load_index_state()


@protected.post("/index/state", response_model=None)
def index_state_set(
    body: Dict[str, Any] = Body(default={}),
    _writes: None = Depends(require_writes),
):  # type: ignore[assignment]
    state = _load_index_state()
    payload = body if isinstance(body, dict) else {}
    for key in ("drive", "local"):
        if key in payload and isinstance(payload[key], dict):
            state[key] = payload[key]
    state["updated_at"] = int(time.time())
    _save_index_state(state)
    return {"ok": True, "state": state}


@protected.get("/index/status", response_model=None)
def index_status():
    broker = _broker()
    return _index_status_payload(broker)


async def _auto_index_if_stale() -> None:
    global BACKGROUND_INDEX_TASK, INDEX_LOOP
    if _index_disabled():
        INDEX_LOGGER.debug("[index] background: startup skip (BUS_DISABLE_INDEX)")
        return
    INDEX_LOOP = asyncio.get_running_loop()
    try:
        status = _index_status_payload(_broker())
    except Exception as exc:
        log(f"[index] background: status_check_failed error={type(exc).__name__}")
        return
    if INDEX_STOP_EVENT.is_set() or INDEX_PAUSE_EVENT.is_set():
        log("[index] background: startup skip (paused)")
        return
    if status.get("overall_up_to_date"):
        log("[index] background: startup skip (up-to-date)")
        return
    if BACKGROUND_INDEX_TASK and not BACKGROUND_INDEX_TASK.done():
        return
    log("[index] background: scheduling startup refresh")
    BACKGROUND_INDEX_TASK = asyncio.create_task(_run_background_index(status))


@protected.get("/drive/available_drives", response_model=None)
def drive_available_drives() -> Dict[str, Any]:
    return _broker().service_call("google_drive", "list_drives", {})


@oauth.post("/oauth/google/start", response_model=None)
def oauth_google_start(
    body: GoogleStartIn | None = Body(default=None),
    _ctx=Depends(require_token_ctx),
):
    _prune_oauth_states()
    payload = body or GoogleStartIn()
    try:
        client_id, _ = _load_google_client()
    except ValueError:
        error_response = JSONResponse({"error": "missing_client"}, status_code=400)
        error_response.headers["Cache-Control"] = "no-store"
        return error_response

    redirect_uri = "http://127.0.0.1:8765/oauth/google/callback"
    if payload.redirect:
        candidate = str(payload.redirect).strip()
        if candidate:
            redirect_uri = candidate

    state = _mk_state()
    _OAUTH_STATES[state] = {
        "redirect": redirect_uri,
        "expires_at": time.time() + 600,
    }

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/drive.readonly",
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    response = JSONResponse({"auth_url": auth_url, "state": state})
    response.headers["Cache-Control"] = "no-store"
    return response


@oauth.get("/oauth/google/callback", response_model=None)
def oauth_google_callback(request: Request):
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if not state or not _check_state(state):
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail={"error": "unauthorized"})

    if not code:
        raise HTTPException(status_code=400, detail="Missing code")

    _prune_oauth_states()
    meta = _OAUTH_STATES.pop(state, None)
    if not meta:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail={"error": "unauthorized"})

    try:
        client_id, client_secret = _load_google_client()
    except ValueError:
        raise HTTPException(status_code=400, detail="missing_client") from None

    default_redirect = "http://127.0.0.1:8765/oauth/google/callback"
    redirect_uri = str(meta.get("redirect") or default_redirect)
    data = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }

    try:
        response = requests.post(
            "https://oauth2.googleapis.com/token",
            data=data,
            timeout=5,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # pragma: no cover - network failure path
        raise HTTPException(status_code=502, detail="oauth_exchange_failed") from exc

    refresh_token = payload.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=400, detail="missing_refresh_token")

    try:
        Secrets.set("google_drive", "oauth_refresh", refresh_token)
    except SecretError as exc:
        raise HTTPException(status_code=500, detail="secret_store_error") from exc

    return RedirectResponse(url="/ui?connected=google_drive", status_code=302)


@oauth.post("/oauth/google/revoke", response_model=None)
def oauth_google_revoke(_ctx=Depends(require_token_ctx)):
    token = Secrets.get("google_drive", "oauth_refresh")
    if token:
        try:
            requests.post(
                "https://oauth2.googleapis.com/revoke",
                data={"token": token},
                timeout=5,
            )
        except Exception:
            pass
        try:
            Secrets.delete("google_drive", "oauth_refresh")
        except SecretError:
            pass
    try:
        get_broker().clear_provider_cache("google_drive")
    except Exception:
        pass
    response = JSONResponse({"ok": True})
    response.headers["Cache-Control"] = "no-store"
    return response


@oauth.get("/oauth/google/status", response_model=None)
def oauth_google_status(_ctx=Depends(require_token_ctx)):
    token = Secrets.get("google_drive", "oauth_refresh")
    connected = bool(token)
    response = JSONResponse({"connected": connected})
    response.headers["Cache-Control"] = "no-store"
    return response


@protected.get("/policy")
def get_policy() -> Dict[str, Any]:
    return load_policy().model_dump()


@protected.post("/policy")
def set_policy(
    policy: Policy = Body(...), _writes: None = Depends(require_writes)
) -> Dict[str, Any]:
    save_policy(policy)
    return policy.model_dump()


@protected.post("/plans")
def create_plan(
    plan: Plan = Body(...), _writes: None = Depends(require_writes)
) -> Dict[str, Any]:
    normalized = plan.model_copy(update={"status": PlanStatus.DRAFT, "stats": {}})
    save_plan(normalized)
    return normalized.model_dump()


@protected.get("/plans")
def plans_index() -> List[Dict[str, Any]]:
    return list_plans()


@protected.get("/plans/{plan_id}")
def plans_get(plan_id: str) -> Dict[str, Any]:
    plan = get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="plan_not_found")
    return plan.model_dump()


@protected.post("/plans/{plan_id}/preview")
def plans_preview(plan_id: str, _writes: None = Depends(require_writes)) -> Dict[str, Any]:
    plan = get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="plan_not_found")
    stats = preview_plan(plan)
    updated = plan.model_copy(update={"status": PlanStatus.PREVIEWED, "stats": stats})
    save_plan(updated)
    return {"ok": True, "stats": stats}


@protected.post("/plans/{plan_id}/commit")
def plans_commit(
    plan_id: str,
    request: Request,
    _writes: None = Depends(require_writes),
) -> Dict[str, Any]:
    plan = get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="plan_not_found")
    require_owner_commit(request)
    summary = commit_local(plan)
    status = PlanStatus.COMMITTED if summary.get("ok") else PlanStatus.FAILED
    stats = dict(plan.stats or {})
    stats["last_commit"] = summary
    updated = plan.model_copy(update={"status": status, "stats": stats})
    save_plan(updated)
    return summary


@protected.post("/plans/{plan_id}/export")
def plans_export(plan_id: str, _writes: None = Depends(require_writes)) -> Response:
    plan = get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="plan_not_found")
    return JSONResponse(plan.model_dump())


@protected.get("/plugins")
def plugins() -> Dict[str, Any]:
    core = _require_core()
    out = core.plugin_list()
    return _with_run_id({"plugins": out})


def _get_plugin_by_id(service_id: str):
    try:
        from core.plugins.loader import get_plugin  # type: ignore
    except Exception:
        return None
    return get_plugin(service_id)


@protected.post("/plugins/{service_id}/read", response_model=None)
def plugin_read(
    service_id: str,
    body: Dict[str, Any] = Body(default={}),
    _writes: None = Depends(require_writes),
):  # type: ignore[assignment]
    plugin = _get_plugin_by_id(service_id)
    if not plugin or not hasattr(plugin, "read"):
        raise HTTPException(status_code=404, detail="plugin or op not found")
    try:
        from core.plugins.loader import plugin_descriptor  # type: ignore
    except Exception:
        descriptor = None
    else:
        descriptor = plugin_descriptor(service_id)
    if descriptor and not bool(descriptor.get("enabled", True)):
        raise HTTPException(status_code=403, detail="plugin_disabled")
    op = body.get("op") if isinstance(body, dict) else None
    params = body.get("params") if isinstance(body, dict) else None
    if not isinstance(params, dict):
        params = {}
    try:
        return plugin.read(op, params)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"read failed: {type(exc).__name__}") from exc


@protected.post("/plugins/{pid}/enable", response_model=None)
def plugin_enable(
    pid: str,
    body: Dict[str, Any] = Body(default={}),
    _writes: None = Depends(require_writes),
):  # type: ignore[assignment]
    try:
        from core.plugins.loader import (  # type: ignore
            get_plugin,
            plugin_descriptor,
            set_plugin_enabled,
        )
    except Exception as exc:  # pragma: no cover - loader import failure
        raise HTTPException(status_code=500, detail="plugin_toggle_unavailable") from exc

    plugin = get_plugin(pid)
    descriptor = plugin_descriptor(pid)
    if not plugin and descriptor is None:
        raise HTTPException(status_code=404, detail="plugin_not_found")

    enabled_flag = True
    if isinstance(body, dict) and "enabled" in body:
        enabled_flag = bool(body.get("enabled"))

    set_plugin_enabled(pid, enabled_flag)
    descriptor = plugin_descriptor(pid) or {"enabled": enabled_flag}
    return {"ok": True, "id": pid, "enabled": bool(descriptor.get("enabled", True))}


@protected.post("/probe")
def probe(
    body: Any = Body(default=None), _writes: None = Depends(require_writes)
) -> Dict[str, Any]:
    core = _require_core()
    services: List[str]
    if body is None:
        services = sorted({svc for item in core.plugin_list() for svc in item.get("services", [])})
    elif isinstance(body, dict) and isinstance(body.get("services"), list):
        services = [str(s) for s in body.get("services", [])]
    elif isinstance(body, list):
        services = [str(s) for s in body]
    else:
        services = []
    results = core.probe_services(services)
    if "reader" in services:
        plugin = _get_plugin_by_id("reader")
        if plugin and hasattr(plugin, "probe"):
            try:
                probe_result = plugin.probe()
            except Exception as exc:
                probe_result = {
                    "ok": False,
                    "detail": "probe_exception",
                    "error": type(exc).__name__,
                }
            results["reader"] = probe_result
            try:
                registry.update_from_probe(
                    "reader",
                    ["catalog.list", "catalog.search"],
                    probe_result,
                )
            except Exception:
                pass
    payload = {
        "bootstrap": core.bootstrap,
        "results": results,
        "probe_timeout_sec": PROBE_TIMEOUT_SEC,
    }
    return _with_run_id(payload)


@protected.get("/capabilities")
def get_capabilities() -> Dict[str, Any]:
    manifest = registry.emit_manifest_async()
    return _with_run_id(manifest)


@protected.post("/execTransform")
def exec_transform(
    body: Dict[str, Any] = Body(...),
    _writes: None = Depends(require_writes),
) -> Dict[str, Any]:
    core = _require_core()
    plugin = str(body.get("plugin") or "").strip()
    fn = str(body.get("fn") or "").strip()
    idempotency_key = str(body.get("idempotency_key") or "").strip()
    if not plugin or not fn or not idempotency_key:
        raise HTTPException(status_code=400, detail="Missing plugin/fn/idempotency_key")
    input_payload = body.get("input") or {}
    limits = body.get("limits") or {}
    outcome = core.transform(
        plugin_id=plugin,
        fn=fn,
        input_payload=input_payload,
        limits=limits,
        idempotency_key=idempotency_key,
    )
    proposal = outcome.get("proposal")
    policy = outcome.get("policy")
    if isinstance(policy, PolicyDecision):
        policy_block = {"decision": policy.decision, "reasons": list(policy.reasons)}
    elif isinstance(policy, dict):
        policy_block = {
            "decision": str(policy.get("decision", "deny")),
            "reasons": list(policy.get("reasons", [])),
        }
    else:
        policy_block = {"decision": "deny", "reasons": ["unknown_policy"]}
    return _with_run_id({"proposal": proposal, "policy": policy_block})


@protected.post("/policy.simulate")
def policy_simulate(
    body: Dict[str, Any] = Body(...),
    _writes: None = Depends(require_writes),
) -> Dict[str, Any]:
    core = _require_core()
    intent = str(body.get("intent") or "").strip()
    metadata = body.get("metadata") or {}
    decision = core.policy.simulate(intent, metadata)
    payload = {
        "decision": decision.decision,
        "reasons": list(decision.reasons),
    }
    return _with_run_id(payload)


@protected.post("/nodes.manifest.sync")
def manifest_sync(
    body: Dict[str, Any] = Body(...),
    _writes: None = Depends(require_writes),
) -> Dict[str, Any]:
    manifest = body.get("manifest")
    if not isinstance(manifest, dict):
        raise HTTPException(status_code=400, detail="invalid_manifest")
    if not registry.validate_signature(manifest):
        raise HTTPException(status_code=400, detail="signature_invalid")
    return _with_run_id({"ok": True})


@protected.get("/transparency.report")
def transparency_report() -> Dict[str, Any]:
    core = _require_core()
    report = core.transparency_report()
    report["manifest_path"] = str(MANIFEST_PATH)
    return _with_run_id(report)


@protected.get("/logs")
def logs() -> Dict[str, Any]:
    path = LOG_FILE or (LOGS / "core.log")
    if not path.exists():
        return _with_run_id({"logs": []})
    lines = path.read_text(encoding="utf-8").splitlines()[-200:]
    return _with_run_id({"logs": lines})


@protected.get("/local/available_drives", response_model=None)
def local_available_drives() -> Dict[str, Any]:
    if os.name == "nt":
        return {"drives": _list_windows_drives()}
    return {"drives": _list_posix_mounts()}


@protected.get("/local/validate_path", response_model=None)
def local_validate_path(path: str = Query(..., min_length=1)) -> Dict[str, Any]:
    abs_path = os.path.abspath(path)
    if not os.path.exists(abs_path):
        return {"ok": False, "reason": "not_found", "path": abs_path}
    if not os.path.isdir(abs_path):
        return {"ok": False, "reason": "not_directory", "path": abs_path}
    return {"ok": True, "path": abs_path}


@protected.post("/open/local", response_model=None)
def open_local(
    payload: Dict[str, Any], _writes: None = Depends(require_writes)
) -> Dict[str, Any]:
    """Open a local file or folder in the system file explorer."""

    item_id = payload.get("id") if isinstance(payload, dict) else None
    if not item_id or not isinstance(item_id, str) or not item_id.startswith("local:"):
        raise HTTPException(status_code=400, detail="missing_local_id")

    path = _decode_local_id(item_id)
    if not _allowed_local_path(path):
        raise HTTPException(status_code=403, detail="path_not_allowed")

    try:
        if os.name == "nt":
            if os.path.isfile(path):
                subprocess.Popen(["explorer", "/select,", path])
            else:
                os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as exc:  # pragma: no cover - platform specific
        raise HTTPException(status_code=500, detail="open_failed") from exc

    return {"ok": True}


@protected.post("/server/restart", response_model=None)
def server_restart(_writes: None = Depends(require_writes)) -> Dict[str, Any]:
    """Exit the running process so it can be restarted manually."""

    try:
        import threading

        threading.Timer(0.25, lambda: os._exit(0)).start()
        return {"ok": True, "message": "Exiting process; restart manually."}
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail="restart_failed") from exc


# Dev endpoints: require both auth and dev mode.
app.include_router(
    dev_routes.router,
    dependencies=[Depends(require_token_ctx), Depends(require_dev)],
)

app.include_router(oauth)
app.include_router(protected)

async def _start_indexer_event() -> None:
    try:
        app.state.start_indexer()
        if is_dev():
            log("[index] control: started in worker")
    except Exception:
        if is_dev():
            log("[index] control: start failed (ignored)")


async def _stop_indexer_event() -> None:
    try:
        app.state.stop_indexer()
    except Exception:
        pass


def create_app():
    init_app_state(app)
    app.state.pause_indexer = pause_indexer
    app.state.resume_indexer = resume_indexer
    app.state.stop_indexer = stop_indexer
    app.state.start_indexer = start_indexer
    if not getattr(app.state, "_domain_routes_registered", False):
        app.include_router(items_router, prefix="/app")
        app.include_router(vendors_router, prefix="/app")
        app.include_router(recipes_router, prefix="/app")
        app.include_router(manufacturing_router, prefix="/app")
        app.include_router(manufacturing_public_router, prefix="/app")
        app.include_router(logs_api.public_router)
        app.include_router(logs_api.router)
        app.include_router(ledger_public_router, prefix="/app")
        app.include_router(ledger_router, prefix="/app")
        # Finance v1: MUST be /app/finance/...
        app.include_router(finance_router, prefix="/app")
        app.include_router(transactions_routes.router, prefix="/app")
        app.include_router(config_routes.router, prefix="/app")
        app.state._domain_routes_registered = True
    return app


APP = create_app()

def build_app():
    global CORE, RUN_ID, SESSION_TOKEN, LOG_FILE
    policy_path = Path("config/policy.json")
    CORE = CoreAlpha(policy_path=policy_path)
    RUN_ID = CORE.run_id
    SESSION_TOKEN = secrets.token_urlsafe(24)
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "session_token.txt").write_text(SESSION_TOKEN, encoding="utf-8")
    CORE.configure_session_token(SESSION_TOKEN)
    app.state.broker = get_broker()
    LOG_FILE = LOGS / f"core_{RUN_ID}.log"
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    banner = f"[trust] mode={CORE.policy.mode} telemetry=off data={DATA} logs={LOGS}"
    print(banner)
    log(banner)
    return app, SESSION_TOKEN


__all__ = [
    "app",
    "APP",
    "APP_DIR",
    "DATA_DIR",
    "DB_URL",
    "UI_DIR",
    "UI_STATIC_DIR",
    "build_app",
    "create_app",
    "SESSION_TOKEN",
]
