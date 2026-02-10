# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
from typing import Any, Dict, List
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest.importorskip("tgc.actions.master_index", reason="optional tgc.actions not present in this repo")
from tgc.actions.master_index import MasterIndexAction
from tgc.config import AppConfig, NotionConfig
from tgc.controller import Controller
from tgc.master_index_controller import (
    MasterIndexData,
    TraversalLimits,
    collect_drive_files,
    collect_notion_pages,
)
from tgc.notion.api import NotionAPIError
from tgc.notion.module import NotionAccessModule
from tgc.modules.google_drive import DriveModuleConfig, GoogleDriveModule
from tgc.organization import OrganizationProfile
from tgc.reporting import RunContext, write_drive_files_markdown


class FakeNotionModule(NotionAccessModule):
    def __init__(self, client):
        super().__init__(
            NotionConfig(
                module_enabled=True,
                token="token",
                root_ids=["root"],
                page_size=50,
                max_depth=0,
            )
        )
        self._fake_client = client

    def _build_client(self):  # type: ignore[override]
        return self._fake_client, None


class FakeNotionClient:
    def __init__(self):
        self.pages = {
            "page-1": {
                "id": "page-1",
                "properties": {
                    "title": {"type": "title", "title": [{"plain_text": "Root Page"}]}
                },
                "url": "https://notion.so/page-1",
                "last_edited_time": "2023-10-10T00:00:00.000Z",
            },
            "db-row": {
                "id": "db-row",
                "properties": {
                    "Name": {"type": "title", "title": [{"plain_text": "Database Row"}]}
                },
                "url": "https://notion.so/db-row",
                "last_edited_time": "2023-10-10T01:00:00.000Z",
            },
        }
        self.children = {
            "page-1": {
                "results": [
                    {"type": "child_page", "id": "child-1"},
                    {"type": "link_to_page", "id": "link-1", "link_to_page": {"type": "page_id", "page_id": "linked"}},
                ],
                "has_more": False,
            }
        }
        self.pages["child-1"] = {
            "id": "child-1",
            "properties": {
                "title": {"type": "title", "title": [{"plain_text": "Child"}]}
            },
            "url": "https://notion.so/child-1",
            "last_edited_time": "2023-10-10T02:00:00.000Z",
        }
        self.pages["linked"] = {
            "id": "linked",
            "properties": {
                "title": {"type": "title", "title": [{"plain_text": "Linked"}]}
            },
            "url": "https://notion.so/linked",
            "last_edited_time": "2023-10-10T03:00:00.000Z",
        }
        self.databases = {
            "database-1": {
                "id": "database-1",
                "title": [{"plain_text": "Root Database"}],
                "url": "https://notion.so/database-1",
                "last_edited_time": "2023-10-11T00:00:00.000Z",
            }
        }
        self.database_rows = {
            "database-1": [
                {"id": "db-row"},
            ]
        }

    def pages_retrieve(self, page_id):
        try:
            return self.pages[page_id]
        except KeyError:
            raise NotionAPIError(404, "object_not_found", f"Page {page_id} not found")

    def blocks_children_list(self, block_id, *, page_size=None, start_cursor=None):
        return self.children.get(block_id, {"results": [], "has_more": False})

    def databases_retrieve(self, database_id):
        if database_id not in self.databases:
            raise NotionAPIError(404, "object_not_found", f"Database {database_id} not found")
        return self.databases[database_id]

    def databases_query(self, database_id, *, page_size=None, start_cursor=None):
        rows = list(self.database_rows.get(database_id, []))
        return {"results": rows, "has_more": False, "next_cursor": None}


class LoopingCursorNotionClient(FakeNotionClient):
    def __init__(self):
        super().__init__()
        self._child_calls = 0

    def blocks_children_list(self, block_id, *, page_size=None, start_cursor=None):
        self._child_calls += 1
        if self._child_calls == 1:
            base = super().blocks_children_list(block_id, page_size=page_size, start_cursor=start_cursor)
            result = dict(base)
            result["has_more"] = True
            result["next_cursor"] = "cursor-token"
            return result
        return {"results": [], "has_more": True, "next_cursor": "cursor-token"}


class LoopingDatabaseCursorClient(FakeNotionClient):
    def __init__(self):
        super().__init__()
        self._database_calls = 0

    def databases_query(self, database_id, *, page_size=None, start_cursor=None):
        self._database_calls += 1
        if self._database_calls == 1:
            rows = list(self.database_rows.get(database_id, []))
            return {"results": rows, "has_more": True, "next_cursor": "repeat-cursor"}
        return {"results": [], "has_more": True, "next_cursor": "repeat-cursor"}


class FakeDriveRequest:
    def __init__(self, payload):
        self._payload = payload

    def execute(self):
        return self._payload


class FakeDriveFiles:
    def __init__(self, metadata_map, list_responses):
        self._metadata_map = metadata_map
        self._list_responses = list_responses
        self._list_index = 0

    def get(self, fileId, **kwargs):  # noqa: N802 - match google client style
        return FakeDriveRequest(self._metadata_map[fileId])

    def list(self, **kwargs):  # noqa: N802 - match google client style
        index = min(self._list_index, len(self._list_responses) - 1)
        self._list_index += 1
        return FakeDriveRequest(self._list_responses[index])


class FakeDriveService:
    def __init__(self, metadata_map, list_responses):
        self._files = FakeDriveFiles(metadata_map, list_responses)

    def files(self):  # noqa: D401 - mimic google client
        return self._files


class FakeDriveModule(GoogleDriveModule):
    def __init__(self, service):
        self._service = service
        super().__init__(DriveModuleConfig(enabled=True))

    def ensure_service(self, *, require_write=False):  # type: ignore[override]
        return self._service, None


def test_collect_notion_pages_with_page_and_links():
    client = FakeNotionClient()
    module = FakeNotionModule(client)
    result = collect_notion_pages(module, ["page-1"], limit=10)
    records = result.records
    errors = result.errors

    titles = [record["title"] for record in records]
    assert "Root Page" in titles
    assert "Child" in titles
    assert "Linked" in titles
    assert errors == []
    assert result.partial is False


def test_collect_notion_pages_with_database_root_includes_rows():
    client = FakeNotionClient()
    module = FakeNotionModule(client)
    result = collect_notion_pages(module, ["database-1"], limit=10)
    records = result.records
    errors = result.errors

    titles = [record["title"] for record in records]
    assert "Root Database" in titles
    assert "Database Row" in titles
    database_entry = next(record for record in records if record["title"] == "Root Database")
    assert database_entry["parent"] == "/"
    row_entry = next(record for record in records if record["title"] == "Database Row")
    assert row_entry["parent"].startswith("/Root Database")


def test_master_index_data_snapshot_counts():
    data = MasterIndexData(
        status="ok",
        dry_run=False,
        generated_at="2024-01-01T00:00:00Z",
        notion_records=[{"title": "Example", "page_id": "1", "url": "", "parent": "/", "last_edited": ""}],
        drive_records=[],
    )

    snapshot = data.snapshot()

    assert snapshot["status"] == "ok"
    assert snapshot["notion"]["count"] == 1
    assert snapshot["drive"]["count"] == 0


def test_database_root_not_found_reports_error():
    client = FakeNotionClient()
    module = FakeNotionModule(client)
    result = collect_notion_pages(module, ["missing"], limit=10)
    records = result.records
    errors = result.errors

    assert records == []
    assert errors == ["Page missing: Page missing not found"]
    assert result.partial is False


def test_collect_notion_pages_detects_repeating_cursor():
    client = LoopingCursorNotionClient()
    module = FakeNotionModule(client)
    result = collect_notion_pages(module, ["page-1"], limit=10)
    records = result.records
    errors = result.errors

    assert any("repeated pagination cursor" in error for error in errors)
    assert any(record["page_id"] == "child-1" for record in records)


def test_collect_notion_database_detects_repeating_cursor():
    client = LoopingDatabaseCursorClient()
    module = FakeNotionModule(client)
    result = collect_notion_pages(module, ["database-1"], limit=10)
    records = result.records
    errors = result.errors

    assert any("repeated pagination cursor" in error for error in errors)
    titles = {record["title"] for record in records}
    assert "Root Database" in titles
    assert "Database Row" in titles


def test_collect_drive_files_detects_repeating_token():
    metadata_map = {
        "root": {
            "id": "root",
            "name": "Root",
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [],
            "trashed": False,
        },
        "child": {
            "id": "child",
            "name": "Child",
            "mimeType": "application/pdf",
            "parents": ["root"],
            "trashed": False,
            "webViewLink": "https://example.com/child",
        },
    }
    list_responses = [
        {"files": [{"id": "child"}], "nextPageToken": "token"},
        {"files": [], "nextPageToken": "token"},
    ]
    service = FakeDriveService(metadata_map, list_responses)
    module = FakeDriveModule(service)

    result = collect_drive_files(module, ["root"], limit=10)
    records = result.records
    errors = result.errors

    assert any("repeated pagination token" in error for error in errors)
    ids = {record["file_id"] for record in records}
    assert ids == {"root", "child"}


def test_collect_notion_pages_respects_max_pages_limit():
    client = FakeNotionClient()
    module = FakeNotionModule(client)
    limits = TraversalLimits(max_pages=1)

    result = collect_notion_pages(module, ["page-1"], limit=10, limits=limits)

    assert result.partial is True
    assert len(result.records) == 1
    assert result.reason and "max pages" in result.reason


def test_collect_drive_files_respects_max_pages_limit():
    metadata_map = {
        "root": {
            "id": "root",
            "name": "Root",
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [],
            "trashed": False,
        },
        "child": {
            "id": "child",
            "name": "Child",
            "mimeType": "application/pdf",
            "parents": ["root"],
            "trashed": False,
            "webViewLink": "https://example.com/child",
        },
    }
    list_responses = [
        {"files": [{"id": "child"}], "nextPageToken": None},
    ]
    service = FakeDriveService(metadata_map, list_responses)
    module = FakeDriveModule(service)
    limits = TraversalLimits(max_pages=1)

    result = collect_drive_files(module, ["root"], limit=10, limits=limits)

    assert result.partial is True
    assert len(result.records) == 1
    assert result.reason and "max pages" in result.reason


def test_write_drive_files_markdown_sorts_and_formats(tmp_path):
    rows = [
        {
            "name": "Older",
            "mimeType": "application/pdf",
            "size": "2048",
            "modifiedTime": "2024-01-01T10:00:00Z",
            "id": "file-1",
            "parents": ["root", "folder"],
            "shortcutDetails": {"targetId": "shortcut-target"},
            "is_shortcut": True,
        },
        {
            "name": "Newer",
            "mimeType": "application/pdf",
            "size": "1024",
            "modifiedTime": "2024-02-01T11:00:00Z",
            "id": "file-2",
            "parents": ["root"],
        },
    ]

    paths = write_drive_files_markdown(tmp_path, rows)

    assert [path.name for path in paths] == ["drive_files.md"]

    content = paths[0].read_text(encoding="utf-8").splitlines()
    assert content[0] == "# Master Index — Drive Files"
    assert any(line.strip() == "Total: 2" for line in content)

    table_lines = [line for line in content if line.startswith("| ")]
    data_lines = table_lines[2:]
    assert data_lines[0].startswith("| Newer")
    assert "shortcut-target" in data_lines[0] or "shortcut-target" in data_lines[1]
    assert data_lines[1].endswith("root, folder |")


def test_write_drive_files_markdown_chunks_large_dataset(tmp_path):
    rows = []
    for index in range(5_001):
        rows.append(
            {
                "name": f"File {index:05d}",
                "mimeType": "text/plain",
                "size": str(index),
                "modifiedTime": f"2024-01-01T00:00:{index % 60:02d}Z",
                "id": f"id-{index}",
                "parents": ["root"],
            }
        )

    paths = write_drive_files_markdown(tmp_path, rows)

    assert [path.name for path in paths] == ["drive_files_1.md", "drive_files_2.md"]

    first_lines = [line for line in paths[0].read_text(encoding="utf-8").splitlines() if line.startswith("| ")][2:]
    second_lines = [line for line in paths[1].read_text(encoding="utf-8").splitlines() if line.startswith("| ")][2:]

    assert len(first_lines) == 5_000
    assert len(second_lines) == 1


def test_master_index_action_writes_sheets_index(monkeypatch, tmp_path):
    output_dir = tmp_path / "docs" / "master_index_reports" / "master_index_test"
    output_dir.mkdir(parents=True)

    class DummyMasterIndexController:
        def __init__(self, controller):
            self.controller = controller

        def run_master_index(self, dry_run, *, limits=None, run_context=None):
            return {
                "status": "ok",
                "dry_run": dry_run,
                "notion_count": 0,
                "drive_count": 0,
                "output_dir": str(output_dir),
                "notion_output": str(output_dir / "notion_pages.md"),
                "drive_output": str(output_dir / "drive_files.md"),
                "drive_outputs": [str(output_dir / "drive_files.md")],
                "notion_errors": [],
                "drive_errors": [],
                "message": None,
            }

    monkeypatch.setattr(
        "tgc.actions.master_index.MasterIndexController",
        DummyMasterIndexController,
    )

    captured_roots: List[str] = []
    sample_rows = [
        {
            "spreadsheetId": "sheet-1",
            "spreadsheetTitle": "Sheet",
            "sheetId": 10,
            "sheetTitle": "Tab",
            "sheetIndex": 0,
            "rows": 1,
            "cols": 1,
            "modifiedTime": "2024-01-01T00:00:00Z",
            "parentPath": "/",
        }
    ]

    def fake_build(limits, drive_root_id, config):
        captured_roots.append(drive_root_id)
        return list(sample_rows)

    monkeypatch.setattr("tgc.actions.master_index.build_sheets_index", fake_build)

    written_payloads: List[List[Dict[str, Any]]] = []

    def fake_write(output_dir_path, rows):
        written_payloads.append(list(rows))
        target = output_dir_path / "sheets_index.md"
        target.write_text("content", encoding="utf-8")
        return [target]

    monkeypatch.setattr(
        "tgc.actions.master_index.write_sheets_index_markdown",
        fake_write,
    )

    class DummyDriveModule:
        def root_ids(self):
            return ["drive-root"]

    config = AppConfig()
    config.drive.fallback_root_id = None
    controller = Controller(
        config=config,
        adapters={},
        organization=OrganizationProfile(),
        reports_root=tmp_path,
    )
    controller.register_module("drive", DummyDriveModule())

    action = MasterIndexAction()
    controller.register_action(action)
    context = RunContext(
        action_id=action.id,
        apply=True,
        reports_root=tmp_path,
        metadata={"action_name": action.name},
        options={},
    )

    result = action.run(controller, context)

    assert any("Sheets index" in change for change in result.changes)
    assert captured_roots == ["drive-root"]
    assert written_payloads == [sample_rows]
