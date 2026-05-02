from pathlib import Path

import pytest

from core.plans.model import Action, ActionKind, Plan, PlanStatus


def test_plan_commit_summary_response_removes_raw_exception_text(bus_client, monkeypatch):
    client = bus_client["client"]
    api_http = bus_client["api_http"]
    plan = Plan(
        id="leaky-plan",
        source="test",
        title="leaky plan",
        actions=[Action(id="a1", kind=ActionKind.COPY, meta={})],
        status=PlanStatus.PREVIEWED,
    )
    saved: dict[str, Plan] = {}

    monkeypatch.setattr(api_http, "get_plan", lambda plan_id: plan if plan_id == "leaky-plan" else None)
    monkeypatch.setattr(api_http, "require_owner_commit", lambda request: None)
    monkeypatch.setattr(
        api_http,
        "commit_local",
        lambda _plan: {
            "ok": False,
            "results": [
                {
                    "action_id": "a1",
                    "status": "error",
                    "error": r"PermissionError: C:\Users\operator\secret.txt",
                }
            ],
        },
    )
    monkeypatch.setattr(api_http, "save_plan", lambda updated: saved.setdefault("plan", updated))

    response = client.post("/plans/leaky-plan/commit")

    assert response.status_code == 200
    assert response.json() == {"ok": False, "results": [{"action_id": "a1", "status": "error", "error": "action_failed"}]}
    assert "secret.txt" not in response.text
    assert saved["plan"].stats["last_commit"] == response.json()


def test_plan_export_sanitizes_stored_last_commit_error(bus_client, monkeypatch):
    client = bus_client["client"]
    api_http = bus_client["api_http"]
    plan = Plan(
        id="stored-leak",
        source="test",
        title="stored leak",
        actions=[Action(id="a1", kind=ActionKind.DELETE, meta={})],
        stats={
            "last_commit": {
                "ok": False,
                "results": [{"action_id": "a1", "status": "error", "error": r"Traceback at D:\private\db.sqlite"}],
            }
        },
    )

    monkeypatch.setattr(api_http, "get_plan", lambda plan_id: plan if plan_id == "stored-leak" else None)

    response = client.post("/plans/stored-leak/export")

    body = response.json()

    assert response.status_code == 200
    assert body["stats"]["last_commit"] == {
        "ok": False,
        "results": [{"action_id": "a1", "status": "error", "error": "action_failed"}],
    }
    assert "Traceback" not in response.text
    assert "private" not in response.text


def test_restore_commit_response_suppresses_dev_debug_info(bus_client, monkeypatch):
    client = bus_client["client"]
    api_http = bus_client["api_http"]

    monkeypatch.setattr(api_http, "_import_commit", lambda *args, **kwargs: {"ok": False, "error": "commit_failed", "info": r"RuntimeError:C:\secret\app.db"})
    monkeypatch.setattr(api_http, "stop_indexer", lambda timeout=10.0: None)
    monkeypatch.setattr(api_http, "start_indexer", lambda: None)

    response = client.post("/app/db/import/commit", json={"path": "backup.db.gcm", "password": "pw"})

    assert response.status_code == 400
    assert response.json() == {"detail": {"error": "commit_failed"}}
    assert "secret" not in response.text
    assert "RuntimeError" not in response.text


@pytest.mark.parametrize("bus_client", ["0"], indirect=True)
def test_dev_journal_info_hidden_when_dev_mode_off(bus_client):
    response = bus_client["client"].get("/dev/journal/info")

    assert response.status_code == 404


@pytest.mark.parametrize("bus_client", ["1"], indirect=True)
def test_dev_journal_info_returns_controlled_read_error_in_dev_mode(bus_client, monkeypatch, tmp_path: Path):
    client = bus_client["client"]
    api_http = bus_client["api_http"]
    journal_dir = tmp_path / "journals"
    journal_dir.mkdir()
    (journal_dir / "inventory.jsonl").mkdir()

    monkeypatch.setattr(api_http, "JOURNALS_DIR", journal_dir)

    response = client.get("/dev/journal/info")
    body = response.json()

    assert response.status_code == 200
    assert body["tail"] == ["__read_error__"]
    assert "PermissionError" not in response.text
    assert str(journal_dir) in body["JOURNAL_DIR"]