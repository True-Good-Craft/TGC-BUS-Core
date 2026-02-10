# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

import importlib
import re
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


def test_export_round_trip_and_filename(modules, tmp_path):
    export_module, crypto = modules
    app_db = export_module.APP_DB
    app_db.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(app_db) as con:
        con.execute("create table sample (val text)")
        con.execute("insert into sample (val) values ('hello')")
        con.commit()

    res = export_module.export_db("pw")
    assert res["ok"] is True
    export_path = Path(res["path"])

    assert export_path.parent == export_module.EXPORTS_DIR
    assert re.match(r"BUSCore-backup-\d{8}-\d{6}\.db\.gcm", export_path.name)
    assert export_path.exists()
    assert res["bytes_written"] == export_path.stat().st_size

    blob = export_path.read_bytes()
    plaintext, header = crypto.decrypt_bytes("pw", blob)
    assert header.version == crypto.CONTAINER_VERSION

    restored = tmp_path / "restored.db"
    restored.write_bytes(plaintext)

    with sqlite3.connect(restored) as con:
        row = con.execute("select val from sample").fetchone()
        assert row[0] == "hello"
