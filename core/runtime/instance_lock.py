# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.appdata.paths import state_dir
from core.version import VERSION

LOCK_ENV_PATH = "BUS_CORE_DB_LOCK_PATH"
LOCK_ENV_TOKEN = "BUS_CORE_DB_LOCK_TOKEN"
LOCK_ENV_DB = "BUS_CORE_DB_LOCK_DB"


class InstanceOwnershipError(RuntimeError):
    """Raised when a live BUS Core owner already holds a database lock."""

    def __init__(self, message: str, *, db_path: str | Path | None = None) -> None:
        super().__init__(message)
        self.db_path = str(db_path) if db_path is not None else None


@dataclass(frozen=True)
class LockMetadata:
    pid: int
    db_path: str
    app_root: str
    started_at: int
    port: int | None
    version: str
    token: str | None = None


@dataclass
class InstanceLock:
    path: Path
    metadata: LockMetadata
    owned: bool = True

    def release(self) -> None:
        if not self.owned:
            return
        try:
            existing = _read_lock(self.path)
        except Exception:
            existing = None
        if existing is not None and _same_token_or_pid(existing, self.metadata):
            try:
                self.path.unlink()
            except FileNotFoundError:  # Best-effort cleanup; lock file may already be gone.
                pass
        self.owned = False


_OWNED_LOCKS: dict[str, InstanceLock] = {}


def _canonical_db_path(db_path: str | Path) -> Path:
    return Path(db_path).expanduser().resolve()


def lock_path_for_db(db_path: str | Path) -> Path:
    canonical = str(_canonical_db_path(db_path)).casefold()
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return state_dir() / f"db-owner-{digest}.lock.json"


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if not handle:
                return ctypes.GetLastError() == 5
            exit_code = wintypes.DWORD()
            try:
                if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return False
                return exit_code.value == 259
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:
            return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _metadata_from_payload(payload: dict[str, Any]) -> LockMetadata:
    return LockMetadata(
        pid=int(payload["pid"]),
        db_path=str(payload["db_path"]),
        app_root=str(payload.get("app_root") or ""),
        started_at=int(payload.get("started_at") or 0),
        port=int(payload["port"]) if payload.get("port") is not None else None,
        version=str(payload.get("version") or ""),
        token=str(payload.get("token") or "") or None,
    )


def _read_lock(path: Path) -> LockMetadata:
    return _metadata_from_payload(json.loads(path.read_text(encoding="utf-8")))


def _write_lock_atomically(path: Path, metadata: LockMetadata) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": metadata.pid,
        "db_path": metadata.db_path,
        "app_root": metadata.app_root,
        "started_at": metadata.started_at,
        "port": metadata.port,
        "version": metadata.version,
        "token": metadata.token,
    }
    with path.open("x", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)


def _same_db(left: LockMetadata, right_db: Path) -> bool:
    try:
        return _canonical_db_path(left.db_path) == right_db
    except Exception:
        return False


def _same_token_or_pid(left: LockMetadata, right: LockMetadata) -> bool:
    if left.token and right.token and left.token == right.token:
        return True
    return left.pid == right.pid


def _lock_message(existing: LockMetadata, target_db: Path, lock_path: Path) -> str:
    return (
        "BUS Core is already running for this database. "
        f"pid={existing.pid} db_path={existing.db_path} port={existing.port} "
        f"started_at={existing.started_at} version={existing.version} lock={lock_path} "
        f"current_db={target_db}"
    )


def acquire_db_owner_lock(
    db_path: str | Path,
    *,
    app_root: str | Path,
    port: int | None,
    export_env: bool = False,
) -> InstanceLock:
    target_db = _canonical_db_path(db_path)
    lock_path = lock_path_for_db(target_db)
    cache_key = str(target_db).casefold()
    cached = _OWNED_LOCKS.get(cache_key)
    if cached and cached.owned:
        return cached

    env_path = os.environ.get(LOCK_ENV_PATH)
    env_token = os.environ.get(LOCK_ENV_TOKEN)
    env_db = os.environ.get(LOCK_ENV_DB)
    if env_path and env_token and env_db:
        try:
            if Path(env_path).resolve() == lock_path.resolve() and _canonical_db_path(env_db) == target_db:
                existing = _read_lock(lock_path)
                if existing.token == env_token and _same_db(existing, target_db):
                    inherited = InstanceLock(lock_path, existing, owned=False)
                    _OWNED_LOCKS[cache_key] = inherited
                    return inherited
        except Exception:  # Compatibility fallback: inherited lock env may be stale or unreadable.
            pass

    metadata = LockMetadata(
        pid=os.getpid(),
        db_path=str(target_db),
        app_root=str(Path(app_root).expanduser().resolve()),
        started_at=int(time.time()),
        port=port,
        version=VERSION,
        token=secrets.token_urlsafe(24),
    )

    while True:
        try:
            _write_lock_atomically(lock_path, metadata)
            lock = InstanceLock(lock_path, metadata)
            _OWNED_LOCKS[cache_key] = lock
            if export_env:
                os.environ[LOCK_ENV_PATH] = str(lock_path)
                os.environ[LOCK_ENV_TOKEN] = metadata.token or ""
                os.environ[LOCK_ENV_DB] = str(target_db)
            return lock
        except FileExistsError:  # Expected fallback: lock contention is resolved by reading the owner.
            pass

        try:
            existing = _read_lock(lock_path)
        except Exception as exc:
            raise InstanceOwnershipError(
                f"db_ownership_lock_invalid path={lock_path}; refusing startup for safety"
            ) from exc

        if _same_token_or_pid(existing, metadata) and _same_db(existing, target_db):
            lock = InstanceLock(lock_path, existing, owned=False)
            _OWNED_LOCKS[cache_key] = lock
            return lock

        if _pid_is_alive(existing.pid):
            raise InstanceOwnershipError(_lock_message(existing, target_db, lock_path), db_path=target_db)

        try:
            lock_path.unlink()
        except FileNotFoundError:
            continue


def release_owned_db_locks() -> None:
    for lock in list(_OWNED_LOCKS.values()):
        lock.release()
    _OWNED_LOCKS.clear()


__all__ = [
    "InstanceLock",
    "InstanceOwnershipError",
    "LockMetadata",
    "acquire_db_owner_lock",
    "lock_path_for_db",
    "release_owned_db_locks",
]
