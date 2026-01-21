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

"""Utilities for encrypted export and import of the BUS Core database."""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Callable, Dict, Optional

from core.appdb.engine import dispose_engine
from core.backup.restore_commit import (
    archive_journals,
    cleanup_sidecars,
    close_all_db_handles,
    same_dir_temp,
    wal_checkpoint,
)

from core.backup.crypto import (
    CONTAINER_VERSION,
    ContainerHeader,
    decrypt_bytes,
    encrypt_bytes,
)
# --- canonical paths (no writes to /exports on Linux) ---
from core.config.paths import (
    DB_PATH as APP_DB,
    APP_DIR,
    APP_ROOT as BUS_ROOT,
    DATA_DIR,
    JOURNAL_DIR,
    EXPORTS_DIR,
)
from core.platform.winfile import robust_replace, wait_for_exclusive

# Ensure required dirs exist (idempotent)
for _p in (APP_DIR, DATA_DIR, JOURNAL_DIR, EXPORTS_DIR, BUS_ROOT):
    _p.mkdir(parents=True, exist_ok=True)

# Safety guard: if BUS_ROOT ever resolves to filesystem root, fallback to APP_DIR
try:
    if str(BUS_ROOT.resolve()) == "/":
        # Avoid writing to /
        BUS_ROOT = APP_DIR
except Exception:
    BUS_ROOT = APP_DIR

# Optional: trace once at import (helps Docker users debug)
try:
    print(
        f"[export-paths] APP_DIR={APP_DIR} BUS_ROOT={BUS_ROOT} "
        f"DATA_DIR={DATA_DIR} EXPORTS_DIR={EXPORTS_DIR}"
    )
except Exception:
    pass


def _connect_readonly(db_path: Path):
    # Prefer immutable read-only; fallback to plain ro
    uri1 = f"file:{db_path.as_posix()}?mode=ro&immutable=1"
    try:
        return sqlite3.connect(uri1, uri=True)
    except sqlite3.Error:
        uri2 = f"file:{db_path.as_posix()}?mode=ro"
        return sqlite3.connect(uri2, uri=True)


def _count_rows(db_path: Path) -> Dict[str, int]:
    counts: Dict[str, int] = {"vendors": 0, "items": 0, "tasks": 0, "attachments": 0}
    if not db_path.exists():
        return counts
    with _connect_readonly(db_path) as con:
        cur = con.cursor()
        for t in counts.keys():
            try:
                cur.execute(f"SELECT COUNT(1) FROM {t}")
                row = cur.fetchone()
                counts[t] = int(row[0]) if row else 0
            except sqlite3.Error:
                counts[t] = 0
    return counts


def _safe_under(root: Path, target: Path) -> bool:
    try:
        root_resolved = root.resolve()
        target_resolved = target.resolve()
    except FileNotFoundError:
        target_resolved = target.parent.resolve() / target.name
        root_resolved = root.resolve()
    try:
        common = os.path.commonpath([root_resolved, target_resolved])
    except ValueError:
        return False
    return Path(common) == root_resolved


def _retry_unlink(p: Path, attempts: int = 10, delay: float = 0.1):
    for _ in range(attempts):
        try:
            p.unlink(missing_ok=True)
            return
        except PermissionError:
            time.sleep(delay)


def list_exports() -> list[dict[str, object]]:
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, object]] = []
    for path in sorted(EXPORTS_DIR.glob("*.db.gcm"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            stat = path.stat()
        except OSError:
            continue
        entries.append(
            {
                "name": path.name,
                "path": str(path),
                "modified": stat.st_mtime,
                "bytes": stat.st_size,
            }
        )
    return entries


def stage_uploaded_backup(upload_name: str, data: bytes) -> Dict[str, object]:
    safe_name = Path(upload_name or "upload.db.gcm").name
    ts = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    target = EXPORTS_DIR / f"upload-{ts}-{safe_name}"
    tmp_file: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=EXPORTS_DIR, delete=False) as tf:
            tf.write(data)
            tf.flush()
            os.fsync(tf.fileno())
            tmp_file = Path(tf.name)
        os.replace(tmp_file, target)
        return {"ok": True, "path": str(target), "bytes_written": len(data)}
    except Exception:
        if tmp_file is not None:
            _retry_unlink(tmp_file)
        return {"ok": False, "error": "upload_failed"}


def export_db(password: str) -> Dict[str, object]:
    if not password:
        return {"ok": False, "error": "password_required"}
    if not APP_DB.exists():
        return {"ok": False, "error": "missing_db"}

    fd, tmp_name = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        with sqlite3.connect(str(APP_DB)) as source, sqlite3.connect(tmp_name) as dest:
            source.backup(dest)
        plaintext = tmp_path.read_bytes()

        blob, header = encrypt_bytes(password, plaintext)
        ts = time.strftime("%Y%m%d-%H%M%S", time.localtime())
        export_path = EXPORTS_DIR / f"BUSCore-backup-{ts}.db.gcm"
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile("wb", dir=EXPORTS_DIR, delete=False) as tmp_file:
            tmp_path_bin = Path(tmp_file.name)
            tmp_file.write(blob)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        os.replace(tmp_path_bin, export_path)

        return {
            "ok": True,
            "path": str(export_path),
            "bytes_written": len(blob),
            "kdf": header.kdf_id,
        }
    finally:
        _retry_unlink(tmp_path)


def _load_and_decrypt(path: Path, password: str) -> tuple[bytes, ContainerHeader]:
    if not password:
        raise ValueError("password_required")

    if not _safe_under(EXPORTS_DIR, path):
        raise PermissionError("path_out_of_roots")
    if not path.exists() or not path.is_file():
        raise FileNotFoundError("cannot_read_file")

    try:
        blob = path.read_bytes()
    except Exception as exc:  # pragma: no cover - read errors aggregated
        raise ValueError("cannot_read_file") from exc

    plaintext, header = decrypt_bytes(password, blob)
    return plaintext, header


def import_preview(path: str, password: str) -> Dict[str, object]:
    try:
        plaintext, header = _load_and_decrypt(Path(path), password)
    except (PermissionError, FileNotFoundError, ValueError) as exc:
        msg = str(exc)
        if msg not in {
            "path_out_of_roots",
            "cannot_read_file",
            "bad_container",
            "decrypt_failed",
            "password_required",
        }:
            msg = "bad_container"
        return {"ok": False, "error": msg}

    if header.version != CONTAINER_VERSION:
        return {
            "ok": False,
            "error": "incompatible_schema",
            "expected": CONTAINER_VERSION,
            "found": header.version,
        }

    fd, tmp_path_str = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    tmp_path = Path(tmp_path_str)
    schema_version: int | None = None
    try:
        tmp_path.write_bytes(plaintext)
        try:
            preview_counts = _count_rows(tmp_path)
        except sqlite3.Error:
            return {"ok": False, "error": "bad_container"}
        try:
            with _connect_readonly(tmp_path) as con:
                cur = con.cursor()
                cur.execute("PRAGMA user_version")
                row = cur.fetchone()
                schema_version = int(row[0]) if row else 0
        except sqlite3.Error:
            schema_version = None
    finally:
        _retry_unlink(tmp_path)

    response: Dict[str, object] = {
        "ok": True,
        "table_counts": preview_counts,
        "schema_version": schema_version,
    }
    return response


def import_commit(
    path: str,
    password: str,
    dispose_call: Optional[Callable[[], None]] = None,
    dev_mode: bool = False,
    log_func: Optional[Callable[[str], None]] = None,
) -> Dict[str, object]:
    def _log(msg: str) -> None:
        if log_func is None:
            return
        try:
            log_func(msg)
        except Exception:
            pass

    try:
        plaintext, header = _load_and_decrypt(Path(path), password)
    except (PermissionError, FileNotFoundError, ValueError) as exc:
        msg = str(exc)
        if msg not in {
            "path_out_of_roots",
            "cannot_read_file",
            "bad_container",
            "decrypt_failed",
            "password_required",
        }:
            msg = "bad_container"
        return {"ok": False, "error": msg}

    if header.version != CONTAINER_VERSION:
        return {
            "ok": False,
            "error": "incompatible_schema",
            "expected": CONTAINER_VERSION,
            "found": header.version,
        }

    tmp_db_path: Path | None = None
    try:
        tmp_db_path = same_dir_temp(APP_DB.parent, "restore-db")
        with tmp_db_path.open("wb") as tf:
            tf.write(plaintext)
            tf.flush()
            os.fsync(tf.fileno())

        try:
            with _connect_readonly(tmp_db_path) as con:
                con.execute("PRAGMA schema_version")
        except sqlite3.Error:
            _retry_unlink(tmp_db_path)
            return {"ok": False, "error": "bad_container"}

        ts = time.strftime("%Y%m%d-%H%M%S", time.localtime())
        APP_DB.parent.mkdir(parents=True, exist_ok=True)
        JOURNAL_DIR.mkdir(parents=True, exist_ok=True)

        dispose_fn = dispose_call or dispose_engine

        # First sweep: dispose engines/pools and close stray connections
        _log("disposing db handles")
        close_all_db_handles(dispose_fn)
        _log("checkpoint wal")
        wal_checkpoint(APP_DB)
        # Second sweep right before replace to ensure handles are gone
        close_all_db_handles(None)

        cleanup_sidecars(APP_DB)
        _log("waiting for exclusive handle on dest")
        ok, err = wait_for_exclusive(APP_DB, attempts=8, sleep_s=0.25)
        if not ok:
            raise RuntimeError(f"exclusive_timeout:win32={err}")

        _log("replacing database file")
        ok, err = robust_replace(tmp_db_path, APP_DB, attempts=20, sleep_s=0.25)
        if not ok:
            raise RuntimeError(f"replace_failed:win32={err}")
        _log("replace complete")

        ts_str = ts
        archive_journals(JOURNAL_DIR, ts_str)
        _log("journals archived")

        audit_path = JOURNAL_DIR / "plugin_audit.jsonl"
        audit_entry = {
            "ts": int(time.time()),
            "action": "import",
            "src": str(Path(path).resolve()),
            "manifest": {"version": header.version},
        }
        try:
            with _connect_readonly(APP_DB) as con:
                audit_entry["preview_counts"] = {**_count_rows(APP_DB)}
        except sqlite3.Error:
            audit_entry["preview_counts"] = {}

        with audit_path.open("a", encoding="utf-8") as audit_file:
            audit_file.write(json.dumps(audit_entry, separators=(',', ':')) + "\n")
    except Exception as exc:
        _log(f"error: {exc}")
        if tmp_db_path is not None:
            _retry_unlink(tmp_db_path)
        err_res: Dict[str, object] = {"ok": False, "error": "commit_failed"}
        if dev_mode:
            err_res["info"] = f"{type(exc).__name__}:{getattr(exc, 'winerror', None)}:{getattr(exc, 'errno', None)}:{exc}"
        return err_res
    else:
        _retry_unlink(tmp_db_path)

    return {"ok": True, "replaced": True, "restart_required": True}
