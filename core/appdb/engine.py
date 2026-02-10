# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from core.appdata.paths import resolve_db_path, legacy_repo_db  # SoT helpers

# --- Path & URL -------------------------------------------------------------

env_db = os.environ.get("BUS_DB")
# New default: AppData target; one-time migrate repo DB if present
target_path = Path(resolve_db_path())
target_path.parent.mkdir(parents=True, exist_ok=True)

source = "ENV" if env_db else "APPDATA"

# One-time migration: if legacy repo DB exists and AppData DB does not, copy it
legacy = legacy_repo_db()
if not env_db:
    try:
        if legacy.exists() and (not target_path.exists()):
            legacy.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(legacy.read_bytes())
            source = "APPDATA (migrated from repo)"
    except Exception:
        # Non-fatal; proceed with empty AppData DB if copy fails
        pass

DB_PATH: Path = target_path
print(f"[db] BUS_DB ({source}) -> {DB_PATH}")


def _sqlite_url(p: Path) -> str:
    """Windows-safe sqlite+pysqlite URL with exactly 3 slashes.

    Example:
      C:/path/to/repo/data/app.db
      -> sqlite+pysqlite:///C:/path/to/repo/data/app.db
    """
    posix = p.resolve().as_posix()
    # If it starts with a drive letter, leave it; otherwise strip leading slashes.
    if re.match(r"^[A-Za-z]:/", posix):
        return f"sqlite+pysqlite:///{posix}"
    return f"sqlite+pysqlite:///{posix}"


DB_URL = _sqlite_url(DB_PATH)

# --- Engine & Session -------------------------------------------------------

ENGINE: Optional[Engine] = None
SessionLocal = sessionmaker(autocommit=False, autoflush=False, future=True)


def get_engine() -> Engine:
    """Create the global engine lazily so the reloader does not open the DB."""

    global ENGINE
    global DB_PATH
    global DB_URL
    current_path = Path(resolve_db_path())
    if current_path != DB_PATH:
        DB_PATH = current_path
        DB_URL = _sqlite_url(DB_PATH)
        if ENGINE is not None:
            ENGINE.dispose()
            ENGINE = None
        SessionLocal.configure(bind=None)
    if ENGINE is None:
        ENGINE = create_engine(
            DB_URL,
            future=True,
            connect_args={"check_same_thread": False},
            poolclass=NullPool,
        )
        SessionLocal.configure(bind=ENGINE)
    else:
        SessionLocal.configure(bind=ENGINE)
    return ENGINE


def dispose_engine() -> None:
    """Dispose and clear the global engine so handles drop immediately."""

    global ENGINE
    if ENGINE is not None:
        try:
            ENGINE.dispose()
        finally:
            ENGINE = None
            SessionLocal.configure(bind=None)


def get_session() -> Generator:
    db = SessionLocal(bind=get_engine())
    try:
        yield db
    finally:
        db.close()


# --- Debug helper (used by /dev/db/where) -----------------------------------


def debug_db_where() -> dict:
    resolved = str(DB_PATH.resolve())
    pragma = []
    with get_engine().connect() as conn:
        try:
            pragma = list(conn.execute(text("PRAGMA database_list")))
        except Exception:
            pragma = []
    return {
        "engine_url": DB_URL,
        "database": DB_PATH.as_posix(),
        "resolved_fs_path": resolved,
        "pragma": [tuple(row) for row in pragma],
    }
