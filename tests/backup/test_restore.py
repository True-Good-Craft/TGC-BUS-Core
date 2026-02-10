# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

import importlib
import sqlite3
from pathlib import Path

import pytest

from tests.conftest import reset_bus_modules

pytestmark = pytest.mark.integration

@pytest.fixture()
def modules(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "lad"))
    monkeypatch.setenv("BUS_DB", str(tmp_path / "lad" / "app" / "app.db"))

    reset_bus_modules(
        [
            "core.utils.export",
            "core.config.paths",
            "core.backup.crypto",
        ]
    )

    crypto = importlib.import_module("core.backup.crypto")
    export = importlib.import_module("core.utils.export")

    crypto = importlib.reload(crypto)
    export = importlib.reload(export)
    return export, crypto


def _write_container(crypto, exports_dir: Path, plaintext: bytes, password: str, version: int | None = None):
    blob, _ = crypto.encrypt_bytes(password, plaintext, version=version or crypto.CONTAINER_VERSION)
    path = exports_dir / "restore_test.db.gcm"
    path.write_bytes(blob)
    return path


def test_preview_rejects_incompatible_schema(modules):
    export_module, crypto = modules
    exports_dir = export_module.EXPORTS_DIR
    exports_dir.mkdir(parents=True, exist_ok=True)
    payload = b"not-a-sqlite-db"
    container_path = _write_container(
        crypto,
        exports_dir,
        payload,
        "pw",
        version=crypto.CONTAINER_VERSION + 1,
    )

    res = export_module.import_preview(str(container_path), "pw")

    assert res == {
        "ok": False,
        "error": "incompatible_schema",
        "expected": crypto.CONTAINER_VERSION,
        "found": crypto.CONTAINER_VERSION + 1,
    }


def test_commit_replaces_db_and_archives_journals(modules):
    export_module, crypto = modules
    app_db = export_module.APP_DB
    journal_dir = export_module.JOURNAL_DIR
    exports_dir = export_module.EXPORTS_DIR

    app_db.parent.mkdir(parents=True, exist_ok=True)
    journal_dir.mkdir(parents=True, exist_ok=True)
    exports_dir.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(app_db) as con:
        con.execute("create table sample (val text)")
        con.execute("insert into sample (val) values ('old')")
        con.commit()

    for name in ("inventory.jsonl", "manufacturing.jsonl"):
        (journal_dir / name).write_text("old\n", encoding="utf-8")

    restore_db = app_db.parent / "restore.db"
    with sqlite3.connect(restore_db) as con:
        con.execute("create table sample (val text)")
        con.execute("insert into sample (val) values ('new')")
        con.execute("PRAGMA user_version=7")
        con.commit()

    container_path = _write_container(
        crypto,
        exports_dir,
        restore_db.read_bytes(),
        "pw",
        version=crypto.CONTAINER_VERSION,
    )

    res = export_module.import_commit(str(container_path), "pw")

    assert res == {"ok": True, "replaced": True, "restart_required": True}

    with sqlite3.connect(app_db) as con:
        row = con.execute("select val from sample").fetchone()
        assert row[0] == "new"

    archived = list(journal_dir.glob("*.jsonl.pre-restore-*"))
    assert len(archived) == 2
    assert all(path.read_text(encoding="utf-8").startswith("old") for path in archived)

    for name in ("inventory.jsonl", "manufacturing.jsonl"):
        fresh = journal_dir / name
        assert fresh.exists()
        assert fresh.read_text(encoding="utf-8") == ""
