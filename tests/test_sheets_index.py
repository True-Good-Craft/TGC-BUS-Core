# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

pytestmark = pytest.mark.unit

pytest.importorskip("tgc.actions.sheets_index", reason="optional tgc.actions not present in this repo")
from tgc.actions.sheets_index import build_sheets_index, write_sheets_index_markdown

SPREADSHEET_MIME = "application/vnd.google-apps.spreadsheet"
FOLDER_MIME = "application/vnd.google-apps.folder"


def _drive_item(file_id, name, mime_type, *, modified="2024-01-01T00:00:00Z"):
    return {
        "id": file_id,
        "name": name,
        "mimeType": mime_type,
        "modifiedTime": modified,
    }


def test_build_sheets_index_collects_nested_metadata(monkeypatch):
    drive_payloads = {
        "root": [
            _drive_item("folder-1", "Reports", FOLDER_MIME),
            _drive_item("sheet-1", "Sales", SPREADSHEET_MIME, modified="2024-01-02T00:00:00Z"),
        ],
        "folder-1": [
            _drive_item("sheet-2", "Budget/2024", SPREADSHEET_MIME, modified="2024-01-03T00:00:00Z"),
        ],
    }

    drive_calls = []

    def fake_list(root_ids, *, limits=None, config=None):
        root = root_ids[0] if root_ids else None
        drive_calls.append((tuple(root_ids), limits))
        return [dict(entry) for entry in drive_payloads.get(root, [])]

    monkeypatch.setattr(
        "tgc.actions.sheets_index.drive_adapter.list_drive_files",
        fake_list,
    )

    metadata_map = {
        "sheet-1": {
            "spreadsheetId": "sheet-1",
            "title": "Sales Tracker",
            "sheets": [
                {"sheetId": 10, "title": "Summary", "index": 0, "rowCount": 20, "columnCount": 5},
                {"sheetId": 11, "title": "Data", "index": 1, "rowCount": 100, "columnCount": 8},
            ],
        },
        "sheet-2": {
            "spreadsheetId": "sheet-2",
            "title": "Budget",  # type: ignore[dict-item]
            "sheets": [
                {"sheetId": 12, "title": "Totals", "index": 0, "rowCount": 50, "columnCount": 6},
            ],
        },
    }

    metadata_calls = []

    def fake_metadata(spreadsheet_id, *, credentials, timeout):
        metadata_calls.append((spreadsheet_id, timeout))
        return dict(metadata_map[spreadsheet_id])

    monkeypatch.setattr(
        "tgc.actions.sheets_index.sheets_adapter.get_spreadsheet_metadata",
        fake_metadata,
    )

    config = {
        "drive_config": {"token": "token"},
        "sheets_credentials": {"client_email": "svc@example.com"},
        "quiet": True,
    }

    rows = build_sheets_index(None, "root", config)

    assert [row["spreadsheetId"] for row in rows] == ["sheet-1", "sheet-1", "sheet-2"]
    assert rows[0]["sheetTitle"] == "Summary"
    assert rows[1]["sheetTitle"] == "Data"
    assert rows[2]["parentPath"] == "/Reports"
    assert rows[2]["sheetTitle"] == "Totals"
    assert rows[2]["modifiedTime"] == "2024-01-03T00:00:00Z"
    assert rows[2]["url"] == "https://docs.google.com/spreadsheets/d/sheet-2"

    # Drive listed the root and then the child folder
    assert [call[0][0] for call in drive_calls] == ["root", "folder-1"]
    # Metadata requested for each spreadsheet
    assert [call[0] for call in metadata_calls] == ["sheet-1", "sheet-2"]


def test_build_sheets_index_respects_max_items(monkeypatch):
    drive_payloads = {
        "root": [
            _drive_item("sheet-1", "One", SPREADSHEET_MIME),
            _drive_item("sheet-2", "Two", SPREADSHEET_MIME),
        ]
    }

    monkeypatch.setattr(
        "tgc.actions.sheets_index.drive_adapter.list_drive_files",
        lambda root_ids, *, limits=None, config=None: [
            dict(entry) for entry in drive_payloads.get(root_ids[0], [])
        ],
    )

    def fake_metadata(spreadsheet_id, *, credentials, timeout):
        return {
            "spreadsheetId": spreadsheet_id,
            "title": spreadsheet_id,
            "sheets": [{"sheetId": 1, "title": "Sheet1", "index": 0, "rowCount": 1, "columnCount": 1}],
        }

    monkeypatch.setattr(
        "tgc.actions.sheets_index.sheets_adapter.get_spreadsheet_metadata",
        fake_metadata,
    )

    config = {
        "drive_config": {"token": "token"},
        "sheets_credentials": {"client_email": "svc@example.com"},
        "quiet": True,
    }

    rows = build_sheets_index({"max_items": 1}, "root", config)

    assert {row["spreadsheetId"] for row in rows} == {"sheet-1"}


def test_build_sheets_index_respects_max_requests(monkeypatch):
    def fake_list(root_ids, *, limits=None, config=None):
        return [_drive_item("sheet-1", "One", SPREADSHEET_MIME)]

    monkeypatch.setattr(
        "tgc.actions.sheets_index.drive_adapter.list_drive_files",
        fake_list,
    )

    metadata_called = False

    def fake_metadata(spreadsheet_id, *, credentials, timeout):  # pragma: no cover - should not run
        nonlocal metadata_called
        metadata_called = True
        return {}

    monkeypatch.setattr(
        "tgc.actions.sheets_index.sheets_adapter.get_spreadsheet_metadata",
        fake_metadata,
    )

    config = {
        "drive_config": {"token": "token"},
        "sheets_credentials": {"client_email": "svc@example.com"},
        "quiet": True,
    }

    rows = build_sheets_index({"max_requests": 1}, "root", config)

    assert rows == []
    assert metadata_called is False


def test_build_sheets_index_respects_max_seconds(monkeypatch):
    called = False

    def fake_list(root_ids, *, limits=None, config=None):  # pragma: no cover - should not run
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(
        "tgc.actions.sheets_index.drive_adapter.list_drive_files",
        fake_list,
    )

    monkeypatch.setattr(
        "tgc.actions.sheets_index.sheets_adapter.get_spreadsheet_metadata",
        lambda spreadsheet_id, *, credentials, timeout: {},
    )

    config = {
        "drive_config": {"token": "token"},
        "sheets_credentials": {"client_email": "svc@example.com"},
        "quiet": True,
    }

    rows = build_sheets_index({"max_seconds": 0}, "root", config)

    assert rows == []
    assert called is False


def test_write_sheets_index_markdown_writes_sorted_table(tmp_path):
    rows = [
        {
            "spreadsheetId": "S2",
            "spreadsheetTitle": "Budget",
            "sheetId": 22,
            "sheetTitle": "Summary",
            "sheetIndex": 1,
            "rows": 20,
            "cols": 5,
            "modifiedTime": "2024-02-02T00:00:00Z",
            "parentPath": "/Finance",
        },
        {
            "spreadsheetId": "S1",
            "spreadsheetTitle": "Analytics",
            "sheetId": 11,
            "sheetTitle": "Data",
            "sheetIndex": 0,
            "rows": 100,
            "cols": 10,
            "modifiedTime": "2024-02-01T00:00:00Z",
            "parentPath": "/Ops",
        },
    ]

    output_paths = write_sheets_index_markdown(tmp_path, rows)

    assert output_paths == [tmp_path / "sheets_index.md"]
    content = output_paths[0].read_text(encoding="utf-8").splitlines()

    assert content[0] == "# Master Index — Google Sheets"
    assert "Total spreadsheets: 2 • Total tabs: 2" in content[2]
    # Sorted alphabetically by spreadsheet title, then sheet index
    data_rows = [
        line
        for line in content
        if line.startswith("| ") and not line.startswith("| Spreadsheet") and not line.startswith("| ---")
    ]
    assert data_rows[0].startswith("| Analytics | Data | 100 | 10 | 2024-02-01T00:00:00Z | S1 | 11 | /Ops |")
    assert data_rows[1].startswith("| Budget | Summary | 20 | 5 | 2024-02-02T00:00:00Z | S2 | 22 | /Finance |")


def test_write_sheets_index_markdown_counts_unique_spreadsheets(tmp_path):
    rows = [
        {
            "spreadsheetId": "S1",
            "spreadsheetTitle": "Analytics",
            "sheetId": 11,
            "sheetTitle": "Data",
            "sheetIndex": 0,
            "rows": 100,
            "cols": 10,
            "modifiedTime": "2024-02-01T00:00:00Z",
            "parentPath": "/Ops",
        },
        {
            "spreadsheetId": "S1",
            "spreadsheetTitle": "Analytics",
            "sheetId": 12,
            "sheetTitle": "Pivot",
            "sheetIndex": 1,
            "rows": 50,
            "cols": 6,
            "modifiedTime": "2024-02-03T00:00:00Z",
            "parentPath": "/Ops",
        },
    ]

    (tmp_path / "nested").mkdir()
    output_paths = write_sheets_index_markdown(tmp_path / "nested", rows)

    assert output_paths == [tmp_path / "nested" / "sheets_index.md"]
    content = output_paths[0].read_text(encoding="utf-8").splitlines()

    assert content[0] == "# Master Index — Google Sheets"
    assert content[2] == "Total spreadsheets: 1 • Total tabs: 2"


def test_write_sheets_index_markdown_splits_large_dataset(tmp_path):
    rows = [
        {
            "spreadsheetId": f"S{index // 2}",
            "spreadsheetTitle": f"Sheet {index // 2}",
            "sheetId": index,
            "sheetTitle": f"Tab {index}",
            "sheetIndex": index,
            "rows": index,
            "cols": index,
            "modifiedTime": "2024-01-01T00:00:00Z",
            "parentPath": "/",
        }
        for index in range(6_001)
    ]

    paths = write_sheets_index_markdown(tmp_path, rows)

    assert paths == [tmp_path / "sheets_index_1.md", tmp_path / "sheets_index_2.md"]
    first_lines = paths[0].read_text(encoding="utf-8").splitlines()
    assert first_lines[0] == "# Master Index — Google Sheets"
    assert "Total spreadsheets: " in first_lines[2]
    second_count = sum(
        1
        for line in paths[1].read_text(encoding="utf-8").splitlines()
        if line.startswith("| ") and not line.startswith("| Spreadsheet") and not line.startswith("| ---")
    )
    # Remaining rows beyond the first 5,000 go into the second chunk
    assert second_count == 1_001
