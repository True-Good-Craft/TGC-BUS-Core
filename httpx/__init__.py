# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin, urlsplit

from ._client import USE_CLIENT_DEFAULT, UseClientDefault
from . import _types


class Headers:
    def __init__(self, data: Optional[Dict[str, str]] = None) -> None:
        self._items: List[tuple[str, str]] = []
        if data:
            for k, v in data.items():
                self._items.append((k, v))

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        for k, v in reversed(self._items):
            if k.lower() == key.lower():
                return v
        return default

    def __contains__(self, key: str) -> bool:
        return any(k.lower() == key.lower() for k, _ in self._items)

    def items(self) -> Iterable[tuple[str, str]]:
        return list(self._items)

    def multi_items(self) -> List[tuple[str, str]]:
        return list(self._items)

    def update(self, other: Dict[str, str]) -> None:
        for k, v in other.items():
            self._items.append((k, v))


class URL:
    def __init__(self, url: str) -> None:
        self._parts = urlsplit(url)
        self.scheme = self._parts.scheme or "http"
        self.netloc = (self._parts.netloc or "").encode()
        self.path = self._parts.path or "/"
        self.query = (self._parts.query or "").encode()
        raw_path = self.path
        if self._parts.query:
            raw_path += f"?{self._parts.query}"
        self.raw_path = raw_path.encode()
        self._url = url

    def __str__(self) -> str:  # pragma: no cover - debug helper
        return self._url


class Request:
    def __init__(self, method: str, url: str, headers: Optional[Headers] = None, content: Any = None):
        self.method = method
        self.url = url if isinstance(url, URL) else URL(url)
        self.headers = headers or Headers()
        self._content = content

    def read(self) -> Any:
        return self._content


class ByteStream:
    def __init__(self, data: bytes):
        self._data = data

    def read(self) -> bytes:
        return self._data


class Response:
    def __init__(self, status_code: int, headers: Optional[List[tuple[str, str]]] = None, stream: Any = b"", request: Request | None = None, **_: Any):
        self.status_code = status_code
        self.headers = headers or []
        self.request = request
        if isinstance(stream, ByteStream):
            self._content = stream.read()
        elif hasattr(stream, "read"):
            self._content = stream.read()
        else:
            self._content = stream or b""

    @property
    def content(self) -> bytes:
        return self._content

    @property
    def text(self) -> str:
        try:
            return self._content.decode("utf-8")
        except Exception:
            return str(self._content)

    def json(self) -> Any:
        return json.loads(self.text)


class BaseTransport:
    def handle_request(self, request: Request) -> Response:  # pragma: no cover - interface
        raise NotImplementedError


class Client:
    def __init__(
        self,
        base_url: str = "",
        headers: Optional[dict[str, str]] = None,
        transport: Optional[BaseTransport] = None,
        follow_redirects: bool = True,
        cookies: Any = None,
    ) -> None:
        self.base_url = base_url
        self.headers = Headers(headers or {})
        self._transport = transport
        self.follow_redirects = follow_redirects
        self.cookies = cookies

    def _merge_url(self, url: str | URL) -> URL:
        if isinstance(url, URL):
            return url
        absolute = url if url.startswith("http") else urljoin(self.base_url, url)
        return URL(absolute)

    def build_request(self, method: str, url: str | URL, **kwargs: Any) -> Request:
        headers = Headers({k: v for k, v in self.headers.items()})
        extra_headers = kwargs.get("headers") or {}
        headers.update({k: v for k, v in (extra_headers or {}).items()})
        if "json" in kwargs and kwargs["json"] is not None:
            content = json.dumps(kwargs["json"])
            headers.update({"Content-Type": "application/json"})
        else:
            content = kwargs.get("content") or kwargs.get("data")

        target_url = self._merge_url(url)
        params = kwargs.get("params")
        if params:
            from urllib.parse import urlencode

            query_string = urlencode(params, doseq=True)
            sep = "&" if target_url.query else "?"
            target_url = URL(f"{target_url._url}{sep}{query_string}")

        return Request(method, str(target_url), headers=headers, content=content)

    def request(self, method: str, url: str | URL, **kwargs: Any) -> Response:
        request = self.build_request(method, url, **kwargs)
        if not self._transport:
            raise RuntimeError("No transport configured for httpx test stub")
        return self._transport.handle_request(request)

    def get(self, url: str | URL, **kwargs: Any) -> Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str | URL, **kwargs: Any) -> Response:
        return self.request("POST", url, **kwargs)

    def put(self, url: str | URL, **kwargs: Any) -> Response:
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str | URL, **kwargs: Any) -> Response:
        return self.request("DELETE", url, **kwargs)


__all__ = [
    "AuthTypes",
    "BaseTransport",
    "ByteStream",
    "Client",
    "CookieTypes",
    "HeaderTypes",
    "Headers",
    "QueryParamTypes",
    "Request",
    "RequestContent",
    "RequestFiles",
    "Response",
    "TimeoutTypes",
    "URL",
    "USE_CLIENT_DEFAULT",
    "UseClientDefault",
]

# Expose typing placeholders
AuthTypes = _types.AuthTypes
CookieTypes = _types.CookieTypes
HeaderTypes = _types.HeaderTypes
QueryParamTypes = _types.QueryParamTypes
RequestContent = _types.RequestContent
RequestFiles = _types.RequestFiles
TimeoutTypes = _types.TimeoutTypes
