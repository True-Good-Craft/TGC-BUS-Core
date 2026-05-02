# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations
import os, json, ssl, socket
from urllib import request, error
from urllib.parse import urlparse
from typing import Dict, Any, List

from core.contracts.plugin_v2 import PluginV2
from core.services.conn_broker import ConnectionBroker, ClientHandle
from core.secrets import Secrets

# ---- minimal config (no secrets logged) ----
_NOTION_VERSION = (os.environ.get("NOTION_API_VERSION") or "2022-06-28").strip()

def _cfg_token() -> str:
    # prefer persisted secret
    val = Secrets.get("notion", "token")
    if val:
        return val.strip()
    # fallback for first run / CI
    return (os.environ.get("NOTION_TOKEN") or "").strip()

def _cfg_roots() -> List[str]:
    raw = (os.environ.get("NOTION_ROOT_PAGE_IDS") or "").strip()
    return [x.strip() for x in raw.split(",") if x.strip()] if raw else []

def _is_configured() -> bool:
    return bool(_cfg_token())


def _is_allowed_notion_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and (parsed.hostname or "").lower() == "api.notion.com"

# ---- tiny HTTP helper with tight timeout (no SDK, no side effects) ----
def _http_get_json(url: str, headers: Dict[str, str], timeout: float = 2.0) -> Dict[str, Any]:
    if not _is_allowed_notion_url(url):
        return {"_error": "notion_url_not_allowed"}
    req = request.Request(url, headers=headers or {})
    ctx = ssl.create_default_context()
    socket.setdefaulttimeout(timeout)
    try:
        # url is restricted to https://api.notion.com before opening.
        with request.urlopen(req, context=ctx, timeout=timeout) as resp:  # nosec B310
            data = resp.read() or b""
            try:
                return json.loads(data.decode("utf-8"))
            except Exception:
                return {"_raw": data.decode("utf-8", errors="ignore")}
    except error.HTTPError as e:
        return {"_http_error": e.code, "_reason": getattr(e, "reason", "")}
    except Exception as e:
        return {"_error": str(e)}

# ---- Notion plugin (read-only) ----
class Plugin(PluginV2):
    """
    Notion (read-only) v0.01.0 — Core-compatible
    Env:
      - NOTION_TOKEN (required) — internal integration token (bot)
      - NOTION_ROOT_PAGE_IDS (optional, CSV)
      - NOTION_API_VERSION (optional, default 2022-06-28)
    Behavior:
      - Hidden until configured (no token).
      - Probe: GET /v1/users/me (2s timeout), no SDK.
      - Provides capability: notion.pages.read
      - No writes; no auto-crawl.
    """
    id = "notion"
    name = "Notion (read-only)"
    version = "0.01.0"
    api_version = "2"

    def describe(self):
        # Stay invisible unless configured -> /probe won’t touch it accidentally
        if not _is_configured():
            return {"services": [], "scopes": []}
        return {"services": ["notion"], "scopes": ["read_base"]}

    def capabilities(self):
        return {
            "provides": ["notion.pages.read"],
            "requires": [],       # Core decides readiness via probe + policy
            "trust_tier": 1,
            "stages": ["service"],
        }

    def register_broker(self, broker: ConnectionBroker):
        if not _is_configured():
            return  # do not register if missing token

        token = _cfg_token()
        roots = _cfg_roots()

        def provider(scope: str):
            # Lightweight handle only, no network work here
            handle = {
                "base": "https://api.notion.com/v1",
                "headers": {
                    "Authorization": f"Bearer {token}",
                    "Notion-Version": _NOTION_VERSION,
                    "Accept": "application/json",
                    "User-Agent": "TGC-Controller/notion-0.01.0",
                },
                "roots": roots,
            }
            return ClientHandle(service="notion", scope=scope, handle=handle)

        def probe(handle: ClientHandle) -> Dict[str, Any]:
            # Bounded, read-only health check
            h = handle.handle or {}
            url = f"{h.get('base')}/users/me"
            info = _http_get_json(url, headers=h.get("headers", {}), timeout=2.0)

            if "_error" in info:
                return {"ok": False, "detail": "notion_probe_error", "error": info["_error"]}
            if info.get("_http_error") == 401:
                return {"ok": False, "detail": "notion_unauthorized"}
            if info.get("_http_error") in (403, 404, 500):
                return {"ok": False, "detail": f"notion_http_{info.get('_http_error')}"}

            # Basic plausibility: any JSON is a pass here (read-only capability)
            return {"ok": True, "detail": "notion_ready"}

        broker.register("notion", provider=provider, probe=probe)
