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
import json, os, hmac, hashlib, time, threading, tempfile
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, List, Any, Optional

from core.config.paths import STATE_DIR
from core.version import VERSION

def _state_dir() -> Path:
    # Windows: %LOCALAPPDATA%\BUSCore\state ; Others: ~/.tgc/state
    if os.name == "nt":
        return STATE_DIR
    return Path.home() / ".tgc" / "state"

MANIFEST_PATH = _state_dir() / "system_manifest.json"
KEY_PATH      = _state_dir() / "capabilities_hmac.key"

@dataclass
class Capability:
    cap: str
    provider: str
    status: str = "blocked"           # ready | blocked | pending | deprecated
    policy: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)  # non-secret metadata

class CapabilityRegistry:
    """Core-owned registry. Single writer. Thread-safe. No secrets."""
    def __init__(self, plugin_api_version: str = "2") -> None:
        self._lock = threading.Lock()
        self._caps: Dict[str, Capability] = {}
        self._plugin_api_version = plugin_api_version
        _state_dir().mkdir(parents=True, exist_ok=True)
        if not KEY_PATH.exists():
            KEY_PATH.write_bytes(os.urandom(32))

    def upsert(self, cap: str, *, provider: str, status: str = "ready",
               policy: Optional[Dict[str, Any]] = None, meta: Optional[Dict[str, Any]] = None) -> None:
        with self._lock:
            self._caps[cap] = Capability(cap=cap, provider=provider, status=status,
                                         policy=policy or {}, meta=meta or {})

    def delete(self, cap: str) -> None:
        with self._lock:
            self._caps.pop(cap, None)

    def list(self) -> List[Capability]:
        with self._lock:
            return list(self._caps.values())

    def update_from_probe(
        self,
        service_id: str,
        capabilities: List[str],
        probe: Dict[str, Any],
    ) -> None:
        allowed = bool(probe.get("ok"))
        status = "ready" if allowed else "blocked"
        reason = None
        if not allowed:
            for key in ("status", "detail", "error"):
                value = probe.get(key)
                if value:
                    reason = str(value)
                    break
            if reason is None:
                reason = "probe_failed"
        meta_probe = {k: v for k, v in probe.items() if k != "ok"}
        for capability in capabilities:
            if not isinstance(capability, str):
                continue
            policy = {"allowed": allowed, "reason": reason if not allowed else None}
            meta = {"probe": meta_probe}
            self.upsert(capability, provider=service_id, status=status, policy=policy, meta=meta)
        self.emit_manifest_async()

    def export(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {
                name: {
                    "provider": cap.provider,
                    "status": cap.status,
                    "policy": dict(cap.policy),
                    "meta": dict(cap.meta),
                }
                for name, cap in self._caps.items()
            }

    def _sign(self, payload: bytes) -> str:
        key = KEY_PATH.read_bytes()
        return hmac.new(key, payload, hashlib.sha256).hexdigest()

    def _manifest_dict(self) -> Dict[str, Any]:
        """Build the manifest dict WITHOUT signature (internal)."""
        caps = [asdict(cap) for cap in self.list()]
        return {
            "core_version": VERSION,
            "plugin_api_version": self._plugin_api_version,
            "schema_version": "1",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "capabilities": caps,
        }

    def build_manifest(self) -> Dict[str, Any]:
        """Return signed manifest JSON dict (no disk writes, no blocking)."""
        base_no_sig = self._manifest_dict()
        payload = json.dumps(base_no_sig, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        sig = self._sign(payload)
        out = dict(base_no_sig)
        out["signature"] = sig
        return out

    def _atomic_write(self, path: Path, content: str) -> None:
        """Windows-safe atomic-ish write: temp file + replace."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=str(path.parent)) as tf:
            tf.write(content)
            tmp_name = tf.name
        Path(tmp_name).replace(path)

    def emit_manifest(self) -> Dict[str, Any]:
        """Synchronous write (kept for compatibility)."""
        out = self.build_manifest()
        out.setdefault(
            "license",
            {
                "core": "PolyForm-Noncommercial-1.0.0",
                "core_url": "https://polyformproject.org/licenses/noncommercial/1.0.0/",
            },
        )
        try:
            self._atomic_write(MANIFEST_PATH, json.dumps(out, indent=2))
        except Exception as e:
            out = dict(out)
            out["_write_error"] = str(e)
        return out

    def emit_manifest_async(self, timeout_sec: float = 1.5) -> Dict[str, Any]:
        """
        Return manifest immediately; write file in a background thread.
        Never blocks the caller longer than building JSON/signing.
        """
        out = self.build_manifest()
        out.setdefault(
            "license",
            {
                "core": "PolyForm-Noncommercial-1.0.0",
                "core_url": "https://polyformproject.org/licenses/noncommercial/1.0.0/",
            },
        )

        def _writer() -> None:
            try:
                self._atomic_write(MANIFEST_PATH, json.dumps(out, indent=2))
            except Exception:  # Non-fatal async cache write; caller already receives the manifest payload.
                pass

        t = threading.Thread(target=_writer, daemon=True)
        t.start()
        return out

    def validate_signature(self, manifest: Dict[str, Any]) -> bool:
        signature = manifest.get("signature")
        if not isinstance(signature, str):
            return False
        base = dict(manifest)
        base.pop("signature", None)
        payload = json.dumps(base, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        expected = self._sign(payload)
        return hmac.compare_digest(signature, expected)
