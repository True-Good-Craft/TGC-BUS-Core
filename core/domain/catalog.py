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
import os, json, time, uuid
from typing import Any, Dict, List


class CatalogManager:
    """
    Manages read streams and optional persistence of sanitized metadata.
    """

    def __init__(self, logger, providers: Dict[str, Any], persist_root: str = "data/catalog"):
        self._log = logger("core.catalog")
        self._providers = providers
        self._streams: Dict[str, Dict[str, Any]] = {}
        self._root = persist_root
        os.makedirs(self._root, exist_ok=True)

    def open(self, source: str, scope: str, options: Dict[str, Any]) -> Dict[str, Any]:
        pr = self._providers.get(source)
        if not pr:
            return {"error": "unknown_source"}
        recursive = bool(options.get("recursive", True))
        page_size = int(options.get("page_size", 200))
        cursor = pr.stream_open(scope, recursive, page_size)
        sid = str(uuid.uuid4())
        self._streams[sid] = {
            "id": sid,
            "source": source,
            "cursor": cursor,
            "created_at": time.time(),
            "scope": scope,
            "options": {
                "recursive": recursive,
                "page_size": page_size,
                "fingerprint": bool(options.get("fingerprint", False)),
            },
        }
        return {"stream_id": sid, "cursor": cursor}

    def next(
        self, stream_id: str, max_items: int, time_budget_ms: int = 700
    ) -> Dict[str, Any]:
        st = self._streams.get(stream_id)
        if not st:
            return {"error": "unknown_stream"}
        pr = self._providers.get(st["source"])
        if not pr:
            return {"error": "unknown_source"}

        deadline = time.perf_counter() + max(0.2, (time_budget_ms or 700) / 1000.0)
        max_items = int(max_items or 500)
        items_accum: List[Dict[str, Any]] = []

        while len(items_accum) < max_items and time.perf_counter() < deadline:
            remaining = max_items - len(items_accum)
            items, cursor, done = pr.stream_next(st["cursor"], remaining)
            st["cursor"] = cursor
            if items:
                sanitized = [self._sanitize(i, st) for i in items]
                sanitized = [i for i in sanitized if i]
                if sanitized:
                    self._persist(st["source"], sanitized)
                    items_accum.extend(sanitized)
            if done:
                return {"items": items_accum, "cursor": cursor, "done": True}

        return {"items": items_accum, "cursor": st["cursor"], "done": False}

    def close(self, stream_id: str) -> Dict[str, Any]:
        st = self._streams.pop(stream_id, None)
        if not st:
            return {"ok": False}
        pr = self._providers.get(st["source"])
        try:
            pr.stream_close(st["cursor"])
        except Exception:  # Best-effort cleanup; provider stream may already be closed.
            pass
        return {"ok": True}

    def _sanitize(self, item: Dict[str, Any], st: Dict[str, Any]) -> Dict[str, Any]:
        allow = {
            "source",
            "id",
            "parent_ids",
            "name",
            "type",
            "mimeType",
            "has_children",
            "size",
            "modifiedTime",
            "driveId",
            "path",
            "fingerprint",
        }
        clean = {k: v for k, v in item.items() if k in allow and v is not None}
        if (
            st["options"].get("fingerprint")
            and item.get("source") == "local_fs"
            and clean.get("type") == "file"
        ):
            try:
                import base64, hashlib

                b64 = clean["id"].split(":", 1)[1]
                pad = "=" * (-len(b64) % 4)
                path = base64.urlsafe_b64decode(b64 + pad).decode()
                h = hashlib.sha256()
                with open(path, "rb") as f:
                    for chunk in iter(lambda: f.read(1024 * 1024), b""):
                        h.update(chunk)
                fp = {"sha256": h.hexdigest()}
                clean["fingerprint"] = {**clean.get("fingerprint", {}), **fp}
            except Exception:  # Optional fingerprint metadata; catalog item remains usable without it.
                pass
        return clean

    def _persist(self, source: str, items: List[Dict[str, Any]]) -> None:
        dirp = os.path.join(self._root, source)
        os.makedirs(dirp, exist_ok=True)
        fp = os.path.join(dirp, "catalog.ndjson")
        with open(fp, "a", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
