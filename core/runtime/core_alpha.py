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

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.services.capabilities import registry
from core.services.capabilities.registry import MANIFEST_PATH
from core.domain.bootstrap import get_broker, set_broker
from core.contracts.plugin_v2 import PluginV2
from core.runtime.crypto import decrypt, encrypt
from core.runtime.journal import JournalManager
from core.runtime.policy import PolicyEngine
from core.runtime.sandbox import SandboxError, run_transform
from core.secrets import Secrets
from core.version import VERSION
from tgc.bootstrap_fs import DATA, LOGS, ensure_first_run


@dataclass
class PluginRecord:
    id: str
    name: str
    version: str
    services: List[str]
    scopes: List[str]
    manifest: Dict[str, Any]
    configured: bool
    instance: PluginV2 = field(repr=False)


class CoreAlpha:
    def __init__(self, *, policy_path: Path) -> None:
        self.run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        self.bootstrap = ensure_first_run()
        self.policy = PolicyEngine(policy_path)
        self.journal = JournalManager(DATA)
        set_broker()
        self.broker = get_broker()
        self.ready = True
        self._lock = threading.Lock()
        self._plugins: List[PluginRecord] = []
        self.session_token: Optional[str] = None
        self._load_plugins()
        self._register_core_capabilities()

    @property
    def plugins(self) -> List[PluginRecord]:
        return list(self._plugins)

    def _load_plugins(self) -> None:
        from core.plugins_alpha import discover_alpha_plugins

        plugins: List[PluginRecord] = []
        for plugin in discover_alpha_plugins():
            manifest = plugin.manifest()
            try:
                desc = plugin.describe() or {}
            except Exception:
                desc = {}
            services = [str(s) for s in desc.get("services", []) if isinstance(s, str)]
            scopes = [str(s) for s in desc.get("scopes", []) if isinstance(s, str)]
            configured = bool(services)
            record = PluginRecord(
                id=str(getattr(plugin, "id", plugin.__class__.__name__)),
                name=str(getattr(plugin, "name", plugin.__class__.__name__)),
                version=str(getattr(plugin, "version", "0")),
                services=services,
                scopes=scopes,
                manifest=manifest,
                configured=configured,
                instance=plugin,
            )
            plugins.append(record)
            self._register_capabilities(record)
            if configured and hasattr(plugin, "register_broker"):
                try:
                    plugin.register_broker(self.broker)
                except Exception:  # Optional plugin broker hook; plugin still loads without broker registration.
                    pass
        self._plugins = plugins
        try:
            from core.plugins.loader import all_plugins

            for module in all_plugins().values():
                register_fn = getattr(module, "register_broker", None)
                if callable(register_fn):
                    try:
                        register_fn(self.broker)
                    except Exception:  # Optional plugin broker hook; one plugin must not block others.
                        continue
        except Exception:  # Compatibility fallback: plugin loader may be unavailable in minimal runtimes.
            pass
        registry.emit_manifest_async()

    def _register_capabilities(self, record: PluginRecord) -> None:
        provides = record.manifest.get("provides", [])
        requires = record.manifest.get("requires", [])
        if not isinstance(provides, list):
            provides = []
        status = "pending" if record.configured else "blocked"
        reason = None if record.configured else "plugin_not_configured"
        for cap in provides:
            policy_block = {"allowed": record.configured, "reason": reason}
            if requires:
                policy_block["requires"] = requires
            registry.upsert(cap, provider=record.id, status=status, policy=policy_block)

    def _register_core_capabilities(self) -> None:
        client_id = Secrets.get("google_drive", "client_id")
        client_secret = Secrets.get("google_drive", "client_secret")
        refresh_token = Secrets.get("google_drive", "oauth_refresh")
        oauth_ready = bool(client_id and client_secret and refresh_token)
        registry.upsert(
            "auth.google.oauth",
            provider="core",
            status="ready" if oauth_ready else "blocked",
            policy={
                "allowed": oauth_ready,
                "reason": None if oauth_ready else "missing_credentials",
            },
            meta={
                "has_client": bool(client_id and client_secret),
                "has_refresh": bool(refresh_token),
            },
        )

        try:
            drive_status = self.broker.service_call("google_drive", "status", {}) or {}
        except Exception:
            drive_status = {}
        drive_configured = bool(drive_status.get("configured"))
        drive_exchange = bool(drive_status.get("can_exchange_token"))
        drive_ready = drive_exchange
        drive_policy = {"allowed": drive_ready}
        if not drive_ready:
            drive_policy["reason"] = "not_configured" if not drive_configured else "token_unavailable"
        registry.upsert(
            "drive.files.read",
            provider="core",
            status="ready" if drive_ready else "blocked",
            policy=drive_policy,
            meta={
                "configured": drive_configured,
                "can_exchange_token": drive_exchange,
            },
        )

        try:
            local_status = self.broker.service_call("local_fs", "status", {}) or {}
        except Exception:
            local_status = {}
        local_configured = bool(local_status.get("configured"))
        roots = local_status.get("roots") if isinstance(local_status.get("roots"), list) else []
        registry.upsert(
            "local.files.read",
            provider="core",
            status="ready" if local_configured else "blocked",
            policy={
                "allowed": local_configured,
                "reason": None if local_configured else "no_roots",
            },
            meta={"configured": local_configured, "roots_count": len(roots or [])},
        )
        registry.emit_manifest_async()

    def configure_session_token(self, token: str) -> None:
        self.session_token = token

    # ---- primitives ----
    def read(self, source: str, selector: Dict[str, Any], limits: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        decision = self.policy.evaluate("read", {"source": source, **(selector or {})})
        return {
            "source": source,
            "selector": selector or {},
            "limits": limits or {},
            "allowed": decision.allowed,
            "reasons": list(decision.reasons),
        }

    def transform(
        self,
        *,
        plugin_id: str,
        fn: str,
        input_payload: Dict[str, Any],
        limits: Optional[Dict[str, Any]],
        idempotency_key: str,
    ) -> Dict[str, Any]:
        metadata = {"plugin": plugin_id, "fn": fn}
        policy_decision = self.policy.evaluate("transform", metadata)
        if not policy_decision.allowed:
            return {"proposal": None, "policy": policy_decision}
        payload = {"input": input_payload, "limits": limits or {}}
        try:
            result = run_transform(plugin_id, fn, payload)
        except SandboxError as exc:
            return {"proposal": {"error": str(exc)}, "policy": policy_decision}
        proposal = result.get("proposal") or {}
        inputs_hash = hashlib.sha256(json.dumps(input_payload, sort_keys=True).encode("utf-8")).hexdigest()
        proposal_hash = hashlib.sha256(json.dumps(proposal, sort_keys=True).encode("utf-8")).hexdigest()
        try:
            self.journal.prepare(
                run_id=self.run_id,
                actor=plugin_id,
                intent="transform",
                idempotency_key=idempotency_key,
                inputs_hash=inputs_hash,
                proposal_hash=proposal_hash,
                policy_version=self.policy.version,
            )
        except ValueError as exc:
            return {"proposal": {"error": str(exc)}, "policy": policy_decision}
        for record in self._plugins:
            if record.id == plugin_id:
                for cap in record.manifest.get("provides", []):
                    registry.upsert(
                        cap,
                        provider=plugin_id,
                        status="ready",
                        policy={"allowed": True},
                    )
        registry.emit_manifest_async()
        return {"proposal": proposal, "policy": policy_decision}

    def write(self, target: str, proposal: Dict[str, Any], idempotency_key: str) -> Dict[str, Any]:
        metadata = {"target": target}
        decision = self.policy.evaluate("write", metadata)
        if not decision.allowed:
            return {"status": "denied", "policy": decision}
        inputs_hash = hashlib.sha256(json.dumps({"target": target}, sort_keys=True).encode("utf-8")).hexdigest()
        proposal_hash = hashlib.sha256(json.dumps(proposal, sort_keys=True).encode("utf-8")).hexdigest()
        try:
            journal_entry = self.journal.prepare(
                run_id=self.run_id,
                actor="core",
                intent="write",
                idempotency_key=idempotency_key,
                inputs_hash=inputs_hash,
                proposal_hash=proposal_hash,
                policy_version=self.policy.version,
            )
        except ValueError as exc:
            return {"status": "error", "policy": decision, "error": str(exc)}
        self.journal.commit(journal_entry["journal_id"], result="commit")
        return {"status": "committed", "policy": decision, "journal_id": journal_entry["journal_id"]}

    def encrypt(self, dek_id: str, chunks: List[Any]) -> List[str]:
        return encrypt(dek_id, chunks)

    def decrypt(self, dek_id: str, chunks: List[str]) -> List[str]:
        return decrypt(dek_id, chunks)

    # ---- transparency ----
    def transparency_report(self) -> Dict[str, Any]:
        enabled = [p.id for p in self._plugins if p.configured]
        caps = [
            {
                "cap": cap.cap,
                "provider": cap.provider,
                "status": cap.status,
                "policy": cap.policy,
            }
            for cap in registry.list()
        ]
        return {
            "version": VERSION,
            "policy_mode": self.policy.mode,
            "telemetry": "off",
            "enabled_plugins": enabled,
            "capability_summary": caps,
            "journal_path": str(self.journal.journal_path),
            "audit_path": str(self.journal.audit_path),
            "manifest_path": str(MANIFEST_PATH),
            "data_paths": [str(DATA), str(LOGS)],
            "retention_policy": {"journal": "manual", "logs": "manual"},
        }

    def plugin_list(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        descriptors: Dict[str, Dict[str, Any]] = {}
        try:
            from core.plugins.loader import iter_descriptors

            descriptors = {str(d.get("id")): d for d in iter_descriptors() if isinstance(d, dict)}
        except Exception:
            descriptors = {}
        seen: set[str] = set()
        for record in self._plugins:
            if not record.configured:
                continue
            descriptor = descriptors.get(record.id, {})
            name = str(descriptor.get("name") or record.name)
            version = str(descriptor.get("version") or record.version)
            services = record.services or []
            scopes = record.scopes or []
            builtin = bool(descriptor.get("builtin")) if descriptor else False
            enabled = bool(descriptor.get("enabled", True)) if descriptor else True
            out.append(
                {
                    "id": record.id,
                    "name": name,
                    "services": services,
                    "scopes": scopes,
                    "version": version,
                    "builtin": builtin,
                    "enabled": enabled,
                    "ui": descriptor.get("ui") if descriptor and descriptor.get("ui") else {},
                }
            )
            seen.add(record.id)
        for pid, descriptor in descriptors.items():
            if pid in seen:
                continue
            services = descriptor.get("services")
            scopes = descriptor.get("scopes")
            out.append(
                {
                    "id": pid,
                    "name": str(descriptor.get("name") or pid),
                    "services": [str(s) for s in services] if isinstance(services, list) else [],
                    "scopes": [str(s) for s in scopes] if isinstance(scopes, list) else [],
                    "version": str(descriptor.get("version") or ""),
                    "builtin": bool(descriptor.get("builtin")),
                    "enabled": bool(descriptor.get("enabled", True)),
                }
            )
        return out

    def update_capabilities_after_probe(self, results: Dict[str, Dict[str, Any]]) -> None:
        for record in self._plugins:
            if not record.configured:
                continue
            service_ok = any(results.get(svc, {}).get("ok") for svc in record.services)
            status = "ready" if service_ok else "blocked"
            policy = {"allowed": service_ok}
            if not service_ok:
                policy["reason"] = "probe_failed"
            for cap in record.manifest.get("provides", []):
                registry.upsert(cap, provider=record.id, status=status, policy=policy)
        registry.emit_manifest_async()

    def probe_services(self, services: List[str]) -> Dict[str, Any]:
        from core.runtime.probe import probe_services

        results = probe_services(self.broker, services)
        self.update_capabilities_after_probe(results)
        return results


__all__ = ["CoreAlpha", "PluginRecord"]
