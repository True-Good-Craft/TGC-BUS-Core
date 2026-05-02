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

import json
import os
from pathlib import Path
from typing import Optional

import getpass  # noqa: F401  # retained for potential future secure input use

from core.config.paths import APP_ROOT

try:
    import keyring
    from keyring.errors import KeyringError

    KEYRING_AVAILABLE = True
except Exception:  # pragma: no cover - best-effort optional dependency
    keyring = None  # type: ignore[assignment]

    class KeyringError(Exception):
        ...

    KEYRING_AVAILABLE = False

from cryptography.fernet import Fernet, InvalidToken


class SecretError(Exception):
    ...


def _app_id() -> str:
    return "tgc-controller"


def _namespace(plugin_id: str, key: str) -> str:
    return f"{plugin_id}:{key}"


# ---- file-fallback (encrypted) ----


def _state_dir() -> Path:
    if os.name == "nt":
        return APP_ROOT / "secrets"
    return Path.home() / ".tgc" / "secrets"


_KEY_PATH = _state_dir() / "master.key"
_STORE_PATH = _state_dir() / "secrets.json.enc"


def _ensure_dirs() -> None:
    _state_dir().mkdir(parents=True, exist_ok=True)


def _load_or_create_master_key() -> bytes:
    _ensure_dirs()
    if _KEY_PATH.exists():
        return _KEY_PATH.read_bytes()
    key = Fernet.generate_key()
    _KEY_PATH.write_bytes(key)
    if KEYRING_AVAILABLE and keyring is not None:
        try:
            # also copy to OS keyring as backup (non-fatal)
            keyring.set_password(_app_id(), "master_key_backup", key.decode("utf-8"))
        except KeyringError:  # Optional keyring backup; encrypted file key remains authoritative.
            pass
    return key


def _load_store_bytes() -> bytes:
    if not _STORE_PATH.exists():
        return b""
    return _STORE_PATH.read_bytes()


def _save_store_bytes(data: bytes) -> None:
    _ensure_dirs()
    tmp = _STORE_PATH.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(_STORE_PATH)


def _file_get(plugin_id: str, key: str) -> Optional[str]:
    key_bytes = _load_or_create_master_key()
    f = Fernet(key_bytes)
    raw = _load_store_bytes()
    if not raw:
        return None
    try:
        dec = f.decrypt(raw)
        obj = json.loads(dec.decode("utf-8"))
        return obj.get(plugin_id, {}).get(key)
    except (InvalidToken, json.JSONDecodeError):
        raise SecretError("Secret store corrupt or key mismatch")


def _file_set(plugin_id: str, key: str, value: str) -> None:
    key_bytes = _load_or_create_master_key()
    f = Fernet(key_bytes)
    raw = _load_store_bytes()
    data = {}
    if raw:
        try:
            dec = f.decrypt(raw)
            data = json.loads(dec.decode("utf-8"))
        except Exception:
            # start fresh if unreadable, but do not lose existing file silently
            raise SecretError("Secret store corrupt; refusing to overwrite")
    data.setdefault(plugin_id, {})[key] = value
    enc = f.encrypt(json.dumps(data, separators=(",", ":")).encode("utf-8"))
    _save_store_bytes(enc)


# ---- public facade ----


class Secrets:
    """
    Core-managed secrets. Prefers OS keyring; falls back to encrypted file.
    Namespacing: per-plugin keys.
    Retrieval is in-process only (no HTTP).
    """

    @staticmethod
    def get(plugin_id: str, key: str) -> Optional[str]:
        ns = _namespace(plugin_id, key)
        # Try OS keyring
        if KEYRING_AVAILABLE and keyring is not None:
            try:
                val = keyring.get_password(_app_id(), ns)
                if val is not None:
                    return val
            except KeyringError:  # Compatibility fallback: OS keyring unavailable; use encrypted file store.
                pass
        # Fallback
        return _file_get(plugin_id, key)

    @staticmethod
    def set(plugin_id: str, key: str, value: str) -> None:
        if value is None or value == "":
            raise SecretError("Empty secret")
        ns = _namespace(plugin_id, key)
        # Try OS keyring
        if KEYRING_AVAILABLE and keyring is not None:
            try:
                keyring.set_password(_app_id(), ns, value)
                return
            except KeyringError:  # Compatibility fallback: OS keyring unavailable; use encrypted file store.
                pass
        # Fallback
        _file_set(plugin_id, key, value)

    @staticmethod
    def delete(plugin_id: str, key: str) -> None:
        ns = _namespace(plugin_id, key)
        ok = False
        if KEYRING_AVAILABLE and keyring is not None:
            try:
                keyring.delete_password(_app_id(), ns)
                ok = True
            except KeyringError:  # Compatibility fallback: secret may already be absent from keyring.
                pass
        # Update fallback store
        try:
            key_bytes = _load_or_create_master_key()
            f = Fernet(key_bytes)
            raw = _load_store_bytes()
            if raw:
                dec = f.decrypt(raw)
                data = json.loads(dec.decode("utf-8"))
                if plugin_id in data and key in data[plugin_id]:
                    del data[plugin_id][key]
                    enc = f.encrypt(json.dumps(data, separators=(",", ":")).encode("utf-8"))
                    _save_store_bytes(enc)
                    ok = True
        except Exception as exc:
            raise SecretError("Secret delete failed") from exc
        if not ok:
            raise SecretError("Secret not found")
