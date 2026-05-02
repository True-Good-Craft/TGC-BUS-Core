# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Reader plugin: multi-source read-only catalog (Drive + Local MVP).
Safe version that does NOT depend on broker.http_session to avoid AttributeError.
"""

from __future__ import annotations
import os
import time
import base64
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import requests  # assumed available; if not, please `pip install requests`

SERVICE_ID = "reader"
VERSION = "1.1.0"

_broker = None
_log = None

# ---------------- utils ----------------

def _b64u(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")

def _ub64u(s: str) -> str:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad).decode()

def _logger():
    return _log

def _http_session(name: str) -> requests.Session:
    """
    Prefer a local session; do not call broker.http_session (it may not exist).
    """
    s = requests.Session()
    s.headers.update({"User-Agent": f"BUSCore/{SERVICE_ID}-{VERSION}"})
    # conservative timeouts via mount adapters could be added later
    return s

def _get_secret(ns: str, key: str) -> Optional[str]:
    get = getattr(_broker, "get_secret", None)
    if callable(get):
        try:
            return get(ns, key)
        except Exception:
            return None
    return None

def _settings() -> Dict[str, Any]:
    # Mirror defaults; Core Settings UI may override behavior server-side.
    return {
        "enabled": {"drive": True, "local": True, "notion": False, "smb": False},
        "local_roots": []
    }

# ---------------- Google helpers ----------------

def _google_client() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    get = getattr(_broker, "get_secret", lambda *_: None)
    # client id / secret across common namespaces
    cid = (
        get("google_oauth", "client_id")
        or get("oauth.google", "client_id")
        or get("google", "client_id")
        or get("google_drive", "client_id")
    )
    cs = (
        get("google_oauth", "client_secret")
        or get("oauth.google", "client_secret")
        or get("google", "client_secret")
        or get("google_drive", "client_secret")
    )
    # refresh token across common namespaces (drive keeps it most often)
    rt = (
        get("google_drive", "refresh_token")
        or get("oauth.google", "refresh_token")
        or get("google_oauth", "refresh_token")
        or get("google", "refresh_token")
    )
    return cid, cs, rt

def _google_access_token() -> Optional[str]:
    cid, cs, rt = _google_client()
    if not (cid and cs and rt):
        return None
    try:
        s = _http_session("reader.oauth")
        resp = s.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": cid,
                "client_secret": cs,
                "grant_type": "refresh_token",
                "refresh_token": rt,
            },
            timeout=8,
        )
        if resp.status_code != 200:
            return None
        return resp.json().get("access_token")
    except Exception:
        return None

# ---------------- Drive adapter ----------------

def _drive_children(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    params: { parent_id: str, page_size: int=200, page_token?: str }
    parent_id:
      - 'drive:root'          -> My Drive root + synthetic 'Shared drives'
      - 'drive:shared'        -> lists shared drives
      - 'drive:drive/<id>:root' -> root of a specific shared drive
      - 'drive:<fileId>'      -> children of a folder/file id
    """
    token = _google_access_token()
    if not token:
        return {"children": [], "next_page_token": None}

    parent_id = params.get("parent_id", "drive:root")
    page_size = int(params.get("page_size", 200))
    page_token = params.get("page_token")
    s = _http_session("reader.drive")
    s.headers.update({"Authorization": f"Bearer {token}"})

    def _files_list(q: str, corpora: str = "allDrives", drive_id: Optional[str] = None) -> Dict[str, Any]:
        try:
            base = "https://www.googleapis.com/drive/v3/files"
            query = {
                "q": q,
                "fields": "nextPageToken,files(id,name,mimeType,parents,driveId,shortcutDetails,modifiedTime,size)",
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
            r = s.get(url, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception:
            return {"files": [], "nextPageToken": None}

    def _node(obj: Dict[str, Any]) -> Dict[str, Any]:
        mime = obj.get("mimeType", "")
        is_folder = mime == "application/vnd.google-apps.folder"
        is_shortcut = mime == "application/vnd.google-apps.shortcut"
        return {
            "id": f"drive:{obj['id']}",
            "name": obj.get("name", obj["id"]),
            "type": "folder" if is_folder else ("shortcut" if is_shortcut else "file"),
            "mimeType": mime,
            "has_children": bool(is_folder or is_shortcut),
            "modifiedTime": obj.get("modifiedTime"),
            "size": int(obj["size"]) if str(obj.get("size", "")).isdigit() else None,
            "driveId": obj.get("driveId"),
        }

    # 1) Synthetic list of Shared drives
    if parent_id == "drive:shared":
        try:
            r = s.get(
                "https://www.googleapis.com/drive/v3/drives"
                "?fields=nextPageToken,drives(id,name)&pageSize=100",
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            children = [{
                "id": f"drive:drive/{d['id']}:root",
                "name": d["name"],
                "type": "folder",
                "mimeType": "application/vnd.google-apps.folder",
                "has_children": True,
                "driveId": d["id"],
            } for d in data.get("drives", [])]
            return {"children": children, "next_page_token": data.get("nextPageToken")}
        except Exception:
            return {"children": [], "next_page_token": None}

    # 2) My Drive root, plus synthetic Shared drives entry
    if parent_id == "drive:root":
        data = _files_list("'root' in parents and trashed=false")
        files = data.get("files", [])
        children = [{
            "id": "drive:shared",
            "name": "Shared drives",
            "type": "folder",
            "mimeType": "application/vnd.google-apps.folder",
            "has_children": True
        }] + [_node(f) for f in files]
        return {"children": children, "next_page_token": data.get("nextPageToken")}

    # 3) Specific shared drive root
    if parent_id.startswith("drive:drive/") and parent_id.endswith(":root"):
        drive_id = parent_id.split("/")[1].split(":")[0]
        data = _files_list("'root' in parents and trashed=false", corpora="drive", drive_id=drive_id)
        return {"children": [_node(f) for f in data.get("files", [])],
                "next_page_token": data.get("nextPageToken")}

    # 4) Generic folder children
    if parent_id.startswith("drive:"):
        fid = parent_id.split(":", 1)[1]
        data = _files_list(f"'{fid}' in parents and trashed=false")
        return {"children": [_node(f) for f in data.get("files", [])],
                "next_page_token": data.get("nextPageToken")}

    return {"children": [], "next_page_token": None}

# ---------------- Local adapter ----------------

def _local_children(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    params: { parent_id: 'local:root' | 'local:<b64-abs-path>' }
    """
    cfg = _settings()
    roots: List[str] = [os.path.abspath(p) for p in cfg.get("local_roots", [])]
    parent_id = params.get("parent_id", "local:root")

    def _mk_node(path: str) -> Dict[str, Any]:
        name = os.path.basename(path) or path
        try:
            is_dir = os.path.isdir(path)
            size = None if is_dir else os.path.getsize(path)
        except Exception:
            is_dir, size = False, None
        return {
            "id": f"local:{_b64u(path)}",
            "name": name,
            "type": "folder" if is_dir else "file",
            "mimeType": None,
            "has_children": is_dir,
            "size": size,
        }

    if parent_id == "local:root":
        return {"children": [_mk_node(p) for p in roots], "next_page_token": None}

    if parent_id.startswith("local:"):
        path = _ub64u(parent_id.split(":", 1)[1])
        apath = os.path.abspath(path)
        # must stay within an allow-listed root
        if not any(os.path.commonpath([apath, r]) == r for r in roots):
            return {"children": [], "next_page_token": None}
        try:
            entries: List[Dict[str, Any]] = []
            with os.scandir(apath) as it:
                for e in it:
                    if e.is_symlink():
                        continue
                    full = os.path.join(apath, e.name)
                    entries.append(_mk_node(full))
            entries.sort(key=lambda x: (x["type"] != "folder", x["name"].lower()))
            return {"children": entries, "next_page_token": None}
        except Exception:
            return {"children": [], "next_page_token": None}

    return {"children": [], "next_page_token": None}

# ---------------- PluginV2 surface ----------------

def describe() -> Dict[str, Any]:
    return {
        "id": SERVICE_ID,
        "version": VERSION,
        "summary": "Unified reader for Drive/Local (read-only)",
        "capabilities": ["catalog.list", "catalog.search"],
        "requires": ["oauth_refresh_token (drive) or local_roots (local)"],
    }

def register_broker(broker) -> None:
    global _broker, _log
    _broker = broker
    _log = getattr(broker, "logger", lambda *_: None)(SERVICE_ID)
    if _log and hasattr(_log, "info"):
        try:
            _log.info("registered", service=SERVICE_ID, version=VERSION)
        except Exception:  # Optional plugin logger; reader broker still registers without it.
            pass

def probe(timeout_s: float = 0.9) -> Dict[str, Any]:
    start = time.perf_counter()
    cfg = _settings()
    enabled = cfg["enabled"]
    ok_sources = []
    if enabled.get("drive"):
        cid, cs, rt = _google_client()
        if cid and cs and rt:
            ok_sources.append("drive")
    if enabled.get("local"):
        if cfg.get("local_roots"):
            ok_sources.append("local")
    status = "ok" if ok_sources else "unconfigured"
    return {
        "ok": bool(ok_sources),
        "status": status,
        "latency_ms": int((time.perf_counter() - start) * 1000),
        "details": ",".join(ok_sources) or "no sources configured",
    }

def views() -> List[Dict[str, Any]]:
    return [{
        "id": "reader",
        "title": "Reader",
        "ui": "tree",
        "op": "children"
    }]

def read(op: str, params: Dict[str, Any]) -> Dict[str, Any]:
    cfg = _settings()
    enabled = cfg["enabled"]
    source = params.get("source", "drive")
    try:
        if op == "children":
            if source == "drive" and enabled.get("drive"):
                return _drive_children(params)
            if source == "local" and enabled.get("local"):
                return _local_children(params)
            return {"children": [], "next_page_token": None}
        if op == "search":
            if source == "drive" and enabled.get("drive"):
                token = _google_access_token()
                if not token:
                    return {"items": []}
                s = _http_session("reader.drive")
                s.headers.update({"Authorization": f"Bearer {token}"})
                q = params.get("q", "").strip()
                if not q:
                    return {"items": []}
                url = (
                    "https://www.googleapis.com/drive/v3/files"
                    "?q=" + urllib.parse.quote(f"name contains '{q}' and trashed=false") +
                    "&pageSize=" + str(int(params.get("limit", 25))) +
                    "&fields=files(id,name,mimeType,modifiedTime,size)"
                    "&supportsAllDrives=true&includeItemsFromAllDrives=true&corpora=allDrives"
                )
                try:
                    r = s.get(url, timeout=10)
                    r.raise_for_status()
                    return {"items": r.json().get("files", [])}
                except Exception:
                    return {"items": []}
            return {"items": []}
        # --- NEW: auto-check source readiness (no secrets) ---
        if op == "autocheck":
            out = {}
            try:
                s_drive = _broker.service_call("google_drive", "status", {})
                out["drive"] = {
                    "configured": bool(s_drive.get("configured")),
                    "can_exchange_token": bool(s_drive.get("can_exchange_token")),
                }
            except Exception:
                out["drive"] = {"configured": False, "can_exchange_token": False}
            try:
                s_local = _broker.service_call("local_fs", "status", {})
                out["local"] = {"configured": bool(s_local.get("configured"))}
            except Exception:
                out["local"] = {"configured": False}
            return out

        # --- NEW: start full pull via Core catalog (returns stream_id; no I/O in plugin) ---
        if op == "start_full_pull":
            source = params.get("source", "drive")   # "drive" | "local"
            recursive = bool(params.get("recursive", True))
            page_size = int(params.get("page_size", 500))
            fingerprint = bool(params.get("fingerprint", False))  # metadata-only default

            if source == "drive":
                opened = _broker.catalog_open("google_drive", "allDrives", {
                    "recursive": recursive,
                    "page_size": page_size,
                    "fingerprint": fingerprint
                })
                return opened  # {stream_id, cursor}
            if source == "local":
                opened = _broker.catalog_open("local_fs", "local_roots", {
                    "recursive": recursive,
                    "page_size": page_size,
                    "fingerprint": fingerprint
                })
                return opened
            return {"error": "unknown_source"}
    except Exception:
        # Never leak internal errors or secrets; keep it deterministic
        if op == "children":
            return {"children": [], "next_page_token": None}
        if op == "search":
            return {"items": []}
        if op == "autocheck":
            return {
                "drive": {"configured": False, "can_exchange_token": False},
                "local": {"configured": False},
            }
        if op == "start_full_pull":
            return {"error": "failed"}
    return {"error": "unknown_op"}
