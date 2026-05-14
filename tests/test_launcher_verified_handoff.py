from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


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


def _import_launcher(monkeypatch: pytest.MonkeyPatch):
    _stub_crypto(monkeypatch)
    fake_pystray = types.SimpleNamespace(Menu=object, MenuItem=object, Icon=object)
    monkeypatch.setitem(sys.modules, "pystray", fake_pystray)
    sys.modules.pop("launcher", None)
    return importlib.import_module("launcher")


def _state(version: str, exe_path: Path) -> dict:
    return {"verified_ready": {"version": version, "exe_path": str(exe_path), "sha256": "a" * 64}}


def test_no_verified_ready_keeps_current(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    launcher = _import_launcher(monkeypatch)

    chosen = launcher._verified_ready_candidate(
        state={"verified_ready": None},
        cache_root=tmp_path / "updates",
        current_version="1.0.4",
        current_executable=None,
    )

    assert chosen is None


def test_verified_ready_older_or_equal_is_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    launcher = _import_launcher(monkeypatch)
    root = tmp_path / "updates"
    exe = root / "versions" / "1.0.4" / "BUS-Core.exe"
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"test")

    chosen_equal = launcher._verified_ready_candidate(
        state=_state("1.0.4", exe),
        cache_root=root,
        current_version="1.0.4",
        current_executable=None,
    )
    chosen_older = launcher._verified_ready_candidate(
        state=_state("1.0.3", exe),
        cache_root=root,
        current_version="1.0.4",
        current_executable=None,
    )

    assert chosen_equal is None
    assert chosen_older is None


def test_verified_ready_newer_current_only_is_ignored(monkeypatch: pytest.MonkeyPatch):
    launcher = _import_launcher(monkeypatch)

    action, selection = launcher._decide_verified_launch_action(
        verified_launch_policy="current_only",
        candidate={"version": "1.0.5", "exe_path": "C:/tmp/BUS-Core.exe"},
        ask_user=lambda _version: True,
    )

    assert action == "current"
    assert selection is None


def test_verified_ready_newer_always_newest_launches(monkeypatch: pytest.MonkeyPatch):
    launcher = _import_launcher(monkeypatch)
    calls: list[tuple[str, int, bool]] = []
    monkeypatch.setattr(
        launcher,
        "_launch_verified_executable",
        lambda *, exe_path, port, force_dev: calls.append((exe_path, port, force_dev)) or True,
    )
    monkeypatch.setattr(
        launcher.update_cache,
        "cache_root",
        lambda: Path("C:/cache"),
    )
    monkeypatch.setattr(
        launcher.update_cache,
        "read_state",
        lambda _root, active_version: {
            "verified_ready": {
                "version": "1.2.0",
                "exe_path": "C:/cache/versions/1.2.0/BUS-Core.exe",
                "sha256": "a" * 64,
            }
        },
    )
    monkeypatch.setattr(
        launcher.Path,
        "exists",
        lambda self: str(self).replace("\\", "/") == "C:/cache/versions/1.2.0/BUS-Core.exe",
    )
    monkeypatch.setattr(
        launcher.Path,
        "is_file",
        lambda self: str(self).replace("\\", "/") == "C:/cache/versions/1.2.0/BUS-Core.exe",
    )

    launched = launcher._maybe_handoff_to_verified_ready(
        verified_launch_policy="always_newest",
        port=8765,
        force_dev=False,
    )

    assert launched is True
    assert len(calls) == 1
    assert calls[0][0].replace("\\", "/") == "C:/cache/versions/1.2.0/BUS-Core.exe"
    assert calls[0][1:] == (8765, False)


def test_verified_ready_newer_ask_yes_attempts_launch(monkeypatch: pytest.MonkeyPatch):
    launcher = _import_launcher(monkeypatch)
    calls: list[tuple[str, int, bool]] = []
    monkeypatch.setattr(launcher.os, "name", "nt", raising=False)
    monkeypatch.setattr(
        launcher,
        "_ask_windows_use_verified",
        lambda _version: True,
    )
    monkeypatch.setattr(
        launcher,
        "_launch_verified_executable",
        lambda *, exe_path, port, force_dev: calls.append((exe_path, port, force_dev)) or True,
    )
    monkeypatch.setattr(
        launcher.update_cache,
        "cache_root",
        lambda: Path("C:/cache"),
    )
    monkeypatch.setattr(
        launcher.update_cache,
        "read_state",
        lambda _root, active_version: {
            "verified_ready": {
                "version": "1.2.1",
                "exe_path": "C:/cache/versions/1.2.1/BUS-Core.exe",
                "sha256": "a" * 64,
            }
        },
    )
    monkeypatch.setattr(
        launcher.Path,
        "exists",
        lambda self: str(self).replace("\\", "/") == "C:/cache/versions/1.2.1/BUS-Core.exe",
    )
    monkeypatch.setattr(
        launcher.Path,
        "is_file",
        lambda self: str(self).replace("\\", "/") == "C:/cache/versions/1.2.1/BUS-Core.exe",
    )

    launched = launcher._maybe_handoff_to_verified_ready(
        verified_launch_policy="ask",
        port=8765,
        force_dev=False,
    )

    assert launched is True
    assert len(calls) == 1


def test_verified_ready_newer_ask_no_does_not_launch(monkeypatch: pytest.MonkeyPatch):
    launcher = _import_launcher(monkeypatch)
    calls: list[tuple[str, int, bool]] = []
    monkeypatch.setattr(launcher.os, "name", "nt", raising=False)
    monkeypatch.setattr(
        launcher,
        "_ask_windows_use_verified",
        lambda _version: False,
    )
    monkeypatch.setattr(
        launcher,
        "_launch_verified_executable",
        lambda *, exe_path, port, force_dev: calls.append((exe_path, port, force_dev)) or True,
    )
    monkeypatch.setattr(
        launcher.update_cache,
        "cache_root",
        lambda: Path("C:/cache"),
    )
    monkeypatch.setattr(
        launcher.update_cache,
        "read_state",
        lambda _root, active_version: {
            "verified_ready": {
                "version": "1.2.2",
                "exe_path": "C:/cache/versions/1.2.2/BUS-Core.exe",
                "sha256": "a" * 64,
            }
        },
    )
    monkeypatch.setattr(
        launcher.Path,
        "exists",
        lambda self: str(self).replace("\\", "/") == "C:/cache/versions/1.2.2/BUS-Core.exe",
    )
    monkeypatch.setattr(
        launcher.Path,
        "is_file",
        lambda self: str(self).replace("\\", "/") == "C:/cache/versions/1.2.2/BUS-Core.exe",
    )

    launched = launcher._maybe_handoff_to_verified_ready(
        verified_launch_policy="ask",
        port=8765,
        force_dev=False,
    )

    assert launched is False
    assert calls == []


def test_verified_ready_newer_ask_yes_launches(monkeypatch: pytest.MonkeyPatch):
    launcher = _import_launcher(monkeypatch)
    monkeypatch.setattr(launcher.os, "name", "nt", raising=False)

    action, selection = launcher._decide_verified_launch_action(
        verified_launch_policy="ask",
        candidate={"version": "1.0.6", "exe_path": "C:/tmp/BUS-Core.exe"},
        ask_user=lambda _version: True,
    )

    assert action == "launch"
    assert selection is not None
    assert selection["version"] == "1.0.6"


def test_verified_ready_newer_ask_no_keeps_current(monkeypatch: pytest.MonkeyPatch):
    launcher = _import_launcher(monkeypatch)
    monkeypatch.setattr(launcher.os, "name", "nt", raising=False)

    action, selection = launcher._decide_verified_launch_action(
        verified_launch_policy="ask",
        candidate={"version": "1.0.6", "exe_path": "C:/tmp/BUS-Core.exe"},
        ask_user=lambda _version: False,
    )

    assert action == "current"
    assert selection is None


def test_invalid_or_missing_exe_path_is_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    launcher = _import_launcher(monkeypatch)
    root = tmp_path / "updates"

    missing = launcher._verified_ready_candidate(
        state={"verified_ready": {"version": "1.0.5", "exe_path": str(root / "versions" / "1.0.5" / "BUS-Core.exe"), "sha256": "a" * 64}},
        cache_root=root,
        current_version="1.0.4",
        current_executable=None,
    )
    invalid = launcher._verified_ready_candidate(
        state={"verified_ready": {"version": "1.0.5", "exe_path": "", "sha256": "a" * 64}},
        cache_root=root,
        current_version="1.0.4",
        current_executable=None,
    )

    assert missing is None
    assert invalid is None


def test_verified_ready_candidate_selects_newest_semver(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    launcher = _import_launcher(monkeypatch)
    root = tmp_path / "updates"
    exe_111 = root / "versions" / "1.1.1" / "BUS-Core.exe"
    exe_120 = root / "versions" / "1.2.0" / "BUS-Core.exe"
    exe_111.parent.mkdir(parents=True, exist_ok=True)
    exe_120.parent.mkdir(parents=True, exist_ok=True)
    exe_111.write_bytes(b"old")
    exe_120.write_bytes(b"new")

    chosen = launcher._verified_ready_candidate(
        state={
            "verified_ready_versions": {
                "1.1.1": {"1" * 64: {"version": "1.1.1", "sha256": "1" * 64, "exe_path": str(exe_111)}},
                "1.2.0": {"2" * 64: {"version": "1.2.0", "sha256": "2" * 64, "exe_path": str(exe_120)}},
            }
        },
        cache_root=root,
        current_version="1.1.1",
        current_executable=None,
    )

    assert chosen == {"version": "1.2.0", "exe_path": str(exe_120.resolve(strict=False))}


def test_launch_failure_falls_back_to_current(monkeypatch: pytest.MonkeyPatch):
    launcher = _import_launcher(monkeypatch)
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("boom")))

    launched = launcher._launch_verified_executable(
        exe_path="C:/cache/versions/1.0.5/BUS-Core.exe",
        port=8765,
        force_dev=False,
    )

    assert launched is False


def test_non_windows_ask_defaults_to_current(monkeypatch: pytest.MonkeyPatch):
    launcher = _import_launcher(monkeypatch)
    monkeypatch.setattr(launcher.os, "name", "posix", raising=False)

    action, selection = launcher._decide_verified_launch_action(
        verified_launch_policy="ask",
        candidate={"version": "1.0.6", "exe_path": "C:/tmp/BUS-Core.exe"},
        ask_user=lambda _version: True,
    )

    assert action == "current"
    assert selection is None
