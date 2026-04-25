from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path

import pytest


def _write_lock(path: Path, *, pid: int, db_path: Path, port: int | None = 8765) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "pid": pid,
                "db_path": str(db_path.resolve()),
                "app_root": str(db_path.parent.resolve()),
                "started_at": 1777078704,
                "port": port,
                "version": "1.0.4",
                "token": "existing-owner-token",
            }
        ),
        encoding="utf-8",
    )


def _import_launcher(monkeypatch: pytest.MonkeyPatch):
    _stub_crypto(monkeypatch)
    fake_pystray = types.SimpleNamespace(Menu=object, MenuItem=object, Icon=object)
    monkeypatch.setitem(sys.modules, "pystray", fake_pystray)
    sys.modules.pop("launcher", None)
    return importlib.import_module("launcher")


def _stub_crypto(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeFernet:
        @staticmethod
        def generate_key() -> bytes:
            return b"0" * 44

        def __init__(self, key: bytes) -> None:
            self.key = key

        def encrypt(self, data: bytes) -> bytes:
            return data

        def decrypt(self, data: bytes) -> bytes:
            return data

    class FakeAESGCM:
        def __init__(self, key: bytes) -> None:
            self.key = key

        def encrypt(self, nonce: bytes, data: bytes, associated_data) -> bytes:
            return data + (b"0" * 16)

        def decrypt(self, nonce: bytes, data: bytes, associated_data) -> bytes:
            return data[:-16]

    class FakeInvalidSignature(Exception):
        pass

    class FakeEd25519PublicKey:
        @staticmethod
        def from_public_bytes(_data: bytes):
            return FakeEd25519PublicKey()

        def verify(self, _signature: bytes, _data: bytes) -> None:
            return None

    crypto_pkg = types.ModuleType("cryptography")
    exceptions_mod = types.ModuleType("cryptography.exceptions")
    hazmat_mod = types.ModuleType("cryptography.hazmat")
    primitives_mod = types.ModuleType("cryptography.hazmat.primitives")
    asymmetric_mod = types.ModuleType("cryptography.hazmat.primitives.asymmetric")
    ed25519_mod = types.ModuleType("cryptography.hazmat.primitives.asymmetric.ed25519")
    ciphers_mod = types.ModuleType("cryptography.hazmat.primitives.ciphers")
    aead_mod = types.ModuleType("cryptography.hazmat.primitives.ciphers.aead")
    fernet_mod = types.ModuleType("cryptography.fernet")
    exceptions_mod.InvalidSignature = FakeInvalidSignature
    ed25519_mod.Ed25519PublicKey = FakeEd25519PublicKey
    aead_mod.AESGCM = FakeAESGCM
    fernet_mod.Fernet = FakeFernet
    fernet_mod.InvalidToken = ValueError
    monkeypatch.setitem(sys.modules, "cryptography", crypto_pkg)
    monkeypatch.setitem(sys.modules, "cryptography.exceptions", exceptions_mod)
    monkeypatch.setitem(sys.modules, "cryptography.hazmat", hazmat_mod)
    monkeypatch.setitem(sys.modules, "cryptography.hazmat.primitives", primitives_mod)
    monkeypatch.setitem(sys.modules, "cryptography.hazmat.primitives.asymmetric", asymmetric_mod)
    monkeypatch.setitem(sys.modules, "cryptography.hazmat.primitives.asymmetric.ed25519", ed25519_mod)
    monkeypatch.setitem(sys.modules, "cryptography.hazmat.primitives.ciphers", ciphers_mod)
    monkeypatch.setitem(sys.modules, "cryptography.hazmat.primitives.ciphers.aead", aead_mod)
    monkeypatch.setitem(sys.modules, "cryptography.fernet", fernet_mod)


def _stub_windows_broker(monkeypatch: pytest.MonkeyPatch) -> None:
    pipes_mod = types.ModuleType("core.broker.pipes")
    service_mod = types.ModuleType("core.broker.service")
    sandbox_mod = types.ModuleType("core.win.sandbox")
    pipes_mod.NamedPipeServer = object
    service_mod.PluginBroker = object
    service_mod.handle_connection = lambda *args, **kwargs: None
    sandbox_mod.spawn_sandboxed = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "core.broker.pipes", pipes_mod)
    monkeypatch.setitem(sys.modules, "core.broker.service", service_mod)
    monkeypatch.setitem(sys.modules, "core.win.sandbox", sandbox_mod)


def test_launcher_preflight_blocks_live_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "data" / "app.db"
    monkeypatch.setenv("BUS_DB", str(db_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    monkeypatch.delenv("BUS_CORE_DB_LOCK_PATH", raising=False)
    monkeypatch.delenv("BUS_CORE_DB_LOCK_TOKEN", raising=False)
    monkeypatch.delenv("BUS_CORE_DB_LOCK_DB", raising=False)

    import core.runtime.instance_lock as instance_lock

    instance_lock = importlib.reload(instance_lock)
    lock_path = instance_lock.lock_path_for_db(db_path)
    _write_lock(lock_path, pid=123456, db_path=db_path, port=9999)
    monkeypatch.setattr(instance_lock, "_pid_is_alive", lambda _pid: True)

    launcher = _import_launcher(monkeypatch)

    with pytest.raises(instance_lock.InstanceOwnershipError) as exc:
        launcher.acquire_launcher_db_lock(8765)

    message = str(exc.value)
    assert "BUS Core is already running for this database." in message
    assert "pid=123456" in message
    assert f"db_path={db_path.resolve()}" in message
    assert "port=9999" in message


def test_launcher_duplicate_exit_uses_friendly_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    db_path = tmp_path / "data" / "app.db"
    monkeypatch.setenv("BUS_DB", str(db_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    logged: list[str] = []

    import core.runtime.instance_lock as instance_lock

    instance_lock = importlib.reload(instance_lock)
    launcher = _import_launcher(monkeypatch)
    monkeypatch.setattr(launcher, "_write_launcher_log", logged.append)

    with pytest.raises(SystemExit) as exc:
        launcher._exit_already_running(
            instance_lock.InstanceOwnershipError(
                "BUS Core is already running for this database. pid=123456 port=9999",
                db_path=db_path.resolve(),
            )
        )

    assert exc.value.code == 2
    assert capsys.readouterr().out == (
        "BUS Core is already running.\n\n"
        f"Database:\n{db_path.resolve()}\n\n"
        "Close the existing BUS Core window before starting another copy.\n"
    )
    assert logged == ["BUS Core is already running for this database. pid=123456 port=9999"]


def test_launcher_preflight_recovers_stale_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "data" / "app.db"
    monkeypatch.setenv("BUS_DB", str(db_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    monkeypatch.delenv("BUS_CORE_DB_LOCK_PATH", raising=False)
    monkeypatch.delenv("BUS_CORE_DB_LOCK_TOKEN", raising=False)
    monkeypatch.delenv("BUS_CORE_DB_LOCK_DB", raising=False)

    import core.runtime.instance_lock as instance_lock

    instance_lock = importlib.reload(instance_lock)
    lock_path = instance_lock.lock_path_for_db(db_path)
    _write_lock(lock_path, pid=123456, db_path=db_path)
    monkeypatch.setattr(instance_lock, "_pid_is_alive", lambda _pid: False)

    launcher = _import_launcher(monkeypatch)
    lock = launcher.acquire_launcher_db_lock(8765)
    try:
        assert lock.path == lock_path
        assert lock.metadata.pid != 123456
        assert lock.metadata.db_path == str(db_path.resolve())
        assert lock_path.exists()
    finally:
        lock.release()


def test_different_bus_db_paths_are_independent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    import core.runtime.instance_lock as instance_lock

    instance_lock = importlib.reload(instance_lock)
    db_one = tmp_path / "one" / "app.db"
    db_two = tmp_path / "two" / "app.db"
    lock_path = instance_lock.lock_path_for_db(db_one)
    _write_lock(lock_path, pid=123456, db_path=db_one)
    monkeypatch.setattr(instance_lock, "_pid_is_alive", lambda _pid: True)

    lock = instance_lock.acquire_db_owner_lock(db_two, app_root=tmp_path, port=8766)
    try:
        assert lock.metadata.db_path == str(db_two.resolve())
    finally:
        lock.release()


def test_server_only_startup_still_blocks_on_live_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "data" / "app.db"
    monkeypatch.setenv("BUS_DB", str(db_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    monkeypatch.delenv("BUS_CORE_DB_LOCK_PATH", raising=False)
    monkeypatch.delenv("BUS_CORE_DB_LOCK_TOKEN", raising=False)
    monkeypatch.delenv("BUS_CORE_DB_LOCK_DB", raising=False)

    import core.runtime.instance_lock as instance_lock

    instance_lock = importlib.reload(instance_lock)
    lock_path = instance_lock.lock_path_for_db(db_path)
    _write_lock(lock_path, pid=123456, db_path=db_path)
    monkeypatch.setattr(instance_lock, "_pid_is_alive", lambda _pid: True)

    for module_name in ("core.api.http", "core.appdb.engine", "core.config.paths"):
        sys.modules.pop(module_name, None)
    _stub_crypto(monkeypatch)
    _stub_windows_broker(monkeypatch)
    api_http = importlib.import_module("core.api.http")

    from fastapi.testclient import TestClient

    with pytest.raises(instance_lock.InstanceOwnershipError):
        with TestClient(api_http.APP):
            pass
