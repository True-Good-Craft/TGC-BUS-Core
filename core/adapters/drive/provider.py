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
import time, urllib.parse
from typing import Any, Callable, Dict, Optional, List, Tuple
import requests

CANON_CLIENT_NS = "google"
CANON_DRIVE_NS  = "google_drive"

FIELDS = "id,name,mimeType,parents,driveId,shortcutDetails,modifiedTime,size,md5Checksum"


class GoogleDriveProvider:
    """
    Core-owned. Exchanges refresh->access token and performs Drive API calls.
    Never exposes tokens or secrets externally.
    """

    def __init__(self, secrets, logger, settings_loader: Callable[[], Dict[str, Any]]):
        self._secrets = secrets
        self._log = logger("provider.google_drive")
        self._settings_loader = settings_loader
        self._sess = requests.Session()
        self._sess.headers.update({"User-Agent": "BUSCore/drive-provider"})
        self._cached_token: Optional[str] = None
        self._cached_refresh: Optional[str] = None
        self._expires_at: float = 0.0

    # ----- token handling (Core-only) -----
    def _now(self) -> float:
        return time.time()

    def _get_client(self) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        cid = self._secrets.get(CANON_CLIENT_NS, "client_id") or self._secrets.get(
            CANON_DRIVE_NS, "client_id"
        )
        cs = self._secrets.get(CANON_CLIENT_NS, "client_secret") or self._secrets.get(
            CANON_DRIVE_NS, "client_secret"
        )
        rt = self._secrets.get(CANON_DRIVE_NS, "refresh_token") or self._secrets.get(
            CANON_DRIVE_NS, "oauth_refresh"
        )
        return cid, cs, rt

    def _access_token(self) -> Optional[str]:
        cid, cs, rt = self._get_client()
        if not (cid and cs and rt):
            self.clear_cache()
            return None
        if (
            self._cached_token
            and self._cached_refresh == rt
            and self._now() < (self._expires_at - 60)
        ):
            return self._cached_token
        try:
            r = self._sess.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": cid,
                    "client_secret": cs,
                    "grant_type": "refresh_token",
                    "refresh_token": rt,
                },
                timeout=8,
            )
            if r.status_code != 200:
                return None
            data = r.json()
            tok = data.get("access_token")
            ttl = int(data.get("expires_in", 3600))
            if tok:
                self._cached_token = tok
                self._cached_refresh = rt
                self._expires_at = self._now() + max(300, min(ttl, 3600))
                return tok
        except Exception:  # Optional external auth fallback; caller treats this as a cache miss.
            pass
        return None

    def clear_cache(self) -> None:
        self._cached_token = None
        self._cached_refresh = None
        self._expires_at = 0.0

    def _auth_get(self, url: str, timeout: int = 10):
        tok = self._access_token()
        if not tok:
            return None, 401
        r = self._sess.get(url, headers={"Authorization": f"Bearer {tok}"}, timeout=timeout)
        return r, r.status_code

    def _drive_includes(self) -> Dict[str, Any]:
        try:
            settings = self._settings_loader()
        except Exception:
            return {}
        if not isinstance(settings, dict):
            return {}
        di = settings.get("drive_includes", {})
        return di if isinstance(di, dict) else {}

    def list_drives(self) -> Dict[str, Any]:
        url = "https://www.googleapis.com/drive/v3/drives?fields=nextPageToken,drives(id,name)&pageSize=100"
        r, code = self._auth_get(url)
        if code != 200 or r is None:
            return {"drives": []}
        try:
            data = r.json()
        except Exception:
            return {"drives": []}
        return {"drives": data.get("drives", [])}

    def get_start_page_token(self) -> Dict[str, Any]:
        url = "https://www.googleapis.com/drive/v3/changes/startPageToken?supportsAllDrives=true"
        try:
            status = self.status()
            if not (status.get("configured") and status.get("can_exchange_token")):
                return {"ok": False, "reason": "not_configured", "token": None}
            r, code = self._auth_get(url)
            if code != 200 or r is None:
                self._log.warning("drive.get_start_page_token http_error %s", code)
                return {"ok": False, "reason": "http_error", "token": None}
            payload = r.json()
            token = payload.get("startPageToken") if isinstance(payload, dict) else None
            if not token:
                self._log.warning("drive.get_start_page_token missing token")
                return {"ok": False, "reason": "missing_token", "token": None}
            return {"ok": True, "token": token}
        except Exception as exc:
            self._log.warning("drive.get_start_page_token failed: %s", exc)
            return {"ok": False, "reason": "exception", "token": None}

    # ----- basic status/children (for UI tree) -----
    def status(self) -> Dict[str, Any]:
        cid, cs, rt = self._get_client()
        return {"configured": bool(cid and cs and rt), "can_exchange_token": bool(self._access_token())}

    def list_children(
        self, *, parent_id: str, page_size: int = 200, page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        def node(obj: Dict[str, Any]) -> Dict[str, Any]:
            mime = obj.get("mimeType", "")
            is_folder = mime == "application/vnd.google-apps.folder"
            is_shortcut = mime == "application/vnd.google-apps.shortcut"
            return {
                "source": "google_drive",
                "id": f"drive:{obj['id']}",
                "parent_ids": obj.get("parents", []),
                "name": obj.get("name", obj["id"]),
                "type": "folder" if is_folder else ("shortcut" if is_shortcut else "file"),
                "mimeType": mime,
                "has_children": bool(is_folder or is_shortcut),
                "modifiedTime": obj.get("modifiedTime"),
                "size": int(obj["size"]) if str(obj.get("size", "")).isdigit() else None,
                "driveId": obj.get("driveId"),
                "fingerprint": {"md5": obj.get("md5Checksum")} if obj.get("md5Checksum") else None,
            }

        if parent_id == "drive:shared":
            url = "https://www.googleapis.com/drive/v3/drives?fields=nextPageToken,drives(id,name)&pageSize=100"
            r, code = self._auth_get(url)
            if code != 200 or r is None:
                return {"children": [], "next_page_token": None}
            data = r.json()
            children = [
                {
                    "source": "google_drive",
                    "id": f"drive:drive/{d['id']}:root",
                    "parent_ids": [],
                    "name": d["name"],
                    "type": "folder",
                    "mimeType": "application/vnd.google-apps.folder",
                    "has_children": True,
                    "driveId": d["id"],
                }
                for d in data.get("drives", [])
            ]
            return {"children": children, "next_page_token": data.get("nextPageToken")}

        def files_list(q: str, corpora: str = "allDrives", drive_id: Optional[str] = None):
            base = "https://www.googleapis.com/drive/v3/files"
            query = {
                "q": q,
                "fields": f"nextPageToken,files({FIELDS})",
                "includeItemsFromAllDrives": "true",
                "supportsAllDrives": "true",
                "corpora": corpora,
                "pageSize": page_size,
            }
            if page_token:
                query["pageToken"] = page_token
            if drive_id:
                query["driveId"] = drive_id
            url = f"{base}?{urllib.parse.urlencode(query)}"
            r, code = self._auth_get(url)
            if code != 200 or r is None:
                return {"files": [], "nextPageToken": None}
            return r.json()

        if parent_id == "drive:root":
            data = files_list("'root' in parents and trashed=false")
            files = data.get("files", [])
            children = [
                {
                    "source": "google_drive",
                    "id": "drive:shared",
                    "parent_ids": [],
                    "name": "Shared drives",
                    "type": "folder",
                    "mimeType": "application/vnd.google-apps.folder",
                    "has_children": True,
                }
            ] + [node(f) for f in files]
            return {"children": children, "next_page_token": data.get("nextPageToken")}

        if parent_id.startswith("drive:drive/") and parent_id.endswith(":root"):
            drive_id = parent_id.split("/")[1].split(":")[0]
            data = files_list("'root' in parents and trashed=false", corpora="drive", drive_id=drive_id)
            return {"children": [node(f) for f in data.get("files", [])], "next_page_token": data.get("nextPageToken")}

        if parent_id.startswith("drive:"):
            fid = parent_id.split(":", 1)[1]
            data = files_list(f"'{fid}' in parents and trashed=false")
            return {"children": [node(f) for f in data.get("files", [])], "next_page_token": data.get("nextPageToken")}

        return {"children": [], "next_page_token": None}

    # ----- catalog streaming (recursive, paged, metadata-only) -----
    def stream_open(self, scope: str, recursive: bool, page_size: int) -> Dict[str, Any]:
        di = self._drive_includes()
        queue: List[Dict[str, Any]] = []

        if di.get("include_my_drive", True):
            root_id = di.get("my_drive_root_id") or "drive:root"
            root_str = str(root_id)
            if not root_str.startswith("drive:"):
                root_str = f"drive:{root_str}"
            queue.append({"parent_id": root_str})

        if di.get("include_shared_drives", True):
            ids = di.get("shared_drive_ids", [])
            if isinstance(ids, list) and ids:
                for drive_id in ids:
                    did = str(drive_id)
                    queue.append({"parent_id": f"drive:drive/{did}:root"})
            else:
                queue.append({"parent_id": "drive:shared"})

        cursor = {
            "scope": scope or "allDrives",
            "recursive": bool(recursive),
            "page_size": int(page_size or 200),
            "queue": queue,
            "page_token": None,
            "phase": "walk",
        }
        return cursor

    def stream_next(
        self, cursor: Dict[str, Any], max_items: int
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any], bool]:
        out: List[Dict[str, Any]] = []
        page_size = min(int(cursor.get("page_size", 200)), 1000)
        recursive = bool(cursor.get("recursive"))
        scope = cursor.get("scope")
        if cursor.get("phase") == "init":
            if scope == "allDrives":
                cursor["queue"] = [{"parent_id": "drive:root"}]
            elif scope == "myDrive":
                cursor["queue"] = [{"parent_id": "drive:root"}]
            elif scope and scope.startswith("sharedDrives/"):
                drive_id = scope.split("/", 1)[1]
                cursor["queue"] = [{"parent_id": f"drive:drive/{drive_id}:root"}]
            else:
                cursor["queue"] = [{"parent_id": "drive:root"}]
            cursor["phase"] = "walk"

        while len(out) < max_items and cursor["queue"]:
            head = cursor["queue"][0]
            parent_id = head["parent_id"]
            ptok = head.get("page_token")
            res = self.list_children(parent_id=parent_id, page_size=page_size, page_token=ptok)
            children = res.get("children", [])
            out.extend(children)
            next_tok = res.get("next_page_token")
            if next_tok:
                head["page_token"] = next_tok
            else:
                cursor["queue"].pop(0)
                if recursive:
                    for c in children:
                        if c.get("type") in {"folder", "shortcut"}:
                            cursor["queue"].append({"parent_id": c["id"]})

        done = not cursor["queue"]
        return out, cursor, done

    def stream_close(self, cursor: Dict[str, Any]) -> None:
        return
