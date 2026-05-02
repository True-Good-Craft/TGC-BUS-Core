import base64
from pathlib import Path


class _FakeLocalProvider:
    def __init__(self, roots: list[str]):
        self._roots = roots

    def _settings(self):
        return {"local_roots": self._roots}


class _FakeCatalog:
    def __init__(self, roots: list[str]):
        self._providers = {"local_fs": _FakeLocalProvider(roots)}


class _FakeBroker:
    def __init__(self, roots: list[str]):
        self._catalog = _FakeCatalog(roots)


def _encode_local_id(path: str) -> str:
    encoded = base64.urlsafe_b64encode(path.encode("utf-8")).decode("ascii").rstrip("=")
    return f"local:{encoded}"


def test_local_validate_path_rejects_outside_root(bus_client, monkeypatch, tmp_path: Path):
    client = bus_client["client"]
    api_http = bus_client["api_http"]
    allowed_root = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed_root.mkdir()
    outside.mkdir()

    monkeypatch.setattr(api_http, "_broker", lambda: _FakeBroker([str(allowed_root)]))

    response = client.get("/local/validate_path", params={"path": str(outside)})

    assert response.status_code == 200
    assert response.json() == {"ok": False, "reason": "path_not_allowed"}


def test_open_local_uses_resolved_safe_file_path(bus_client, monkeypatch, tmp_path: Path):
    client = bus_client["client"]
    api_http = bus_client["api_http"]
    allowed_root = tmp_path / "allowed"
    safe_file = allowed_root / "nested" / "file.txt"
    safe_file.parent.mkdir(parents=True)
    safe_file.write_text("ok", encoding="utf-8")
    captured: dict[str, object] = {}

    monkeypatch.setattr(api_http, "_broker", lambda: _FakeBroker([str(allowed_root)]))

    def _fake_popen(args, *unused_args, **unused_kwargs):
        captured["args"] = args
        return object()

    monkeypatch.setattr(api_http.subprocess, "Popen", _fake_popen)

    response = client.post("/open/local", json={"id": _encode_local_id(str(safe_file))})

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert captured["args"] == ["explorer", "/select,", str(safe_file.resolve(strict=False))]


def test_open_local_rejects_traversal_path(bus_client, monkeypatch, tmp_path: Path):
    client = bus_client["client"]
    api_http = bus_client["api_http"]
    allowed_root = tmp_path / "allowed"
    safe_file = allowed_root / "nested" / "file.txt"
    safe_file.parent.mkdir(parents=True)
    safe_file.write_text("ok", encoding="utf-8")
    traversal_path = str(allowed_root / "nested" / ".." / "nested" / "file.txt")

    monkeypatch.setattr(api_http, "_broker", lambda: _FakeBroker([str(allowed_root)]))

    response = client.post("/open/local", json={"id": _encode_local_id(traversal_path)})

    assert response.status_code == 403
    assert response.json() == {"detail": "path_not_allowed"}


def test_open_local_rejects_path_outside_root(bus_client, monkeypatch, tmp_path: Path):
    client = bus_client["client"]
    api_http = bus_client["api_http"]
    allowed_root = tmp_path / "allowed"
    outside_file = tmp_path / "outside.txt"
    allowed_root.mkdir()
    outside_file.write_text("bad", encoding="utf-8")

    monkeypatch.setattr(api_http, "_broker", lambda: _FakeBroker([str(allowed_root)]))

    response = client.post("/open/local", json={"id": _encode_local_id(str(outside_file))})

    assert response.status_code == 403
    assert response.json() == {"detail": "path_not_allowed"}