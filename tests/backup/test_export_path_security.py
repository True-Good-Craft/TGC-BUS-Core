import importlib

import pytest

from tests.conftest import reset_bus_modules


@pytest.fixture()
def modules(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "lad"))
    monkeypatch.setenv("BUS_DB", str(tmp_path / "lad" / "app" / "app.db"))

    reset_bus_modules(
        [
            "core.utils.export",
            "core.utils.pathsafe",
            "core.config.paths",
            "core.backup.crypto",
        ]
    )

    export = importlib.import_module("core.utils.export")
    return importlib.reload(export)


@pytest.mark.parametrize(
    "dangerous_path",
    [
        "../escape.db.gcm",
        "..\\escape.db.gcm",
        "/etc/passwd",
        r"C:\Windows\System32\drivers\etc\hosts",
        r"\\server\share\file",
        r"\\?\C:\Windows\bad",
        "bad\x00name",
    ],
)
def test_import_preview_and_commit_reject_paths_outside_exports(modules, dangerous_path: str):
    export_module = modules

    preview = export_module.import_preview(dangerous_path, "pw")
    commit = export_module.import_commit(dangerous_path, "pw")

    assert preview == {"ok": False, "error": "path_out_of_roots"}
    assert commit == {"ok": False, "error": "path_out_of_roots"}