from __future__ import annotations

from pathlib import Path

import pytest

from core.plans.model import Plan


def _configure_organizer(monkeypatch: pytest.MonkeyPatch, root: Path) -> list[Plan]:
    import core.organizer.api as organizer_api

    saved: list[Plan] = []
    monkeypatch.setattr(organizer_api, "get_allowed_local_roots", lambda: [str(root)])
    monkeypatch.setattr(organizer_api, "save_plan", lambda plan: saved.append(plan))
    return saved


def _assert_under(path_value: str, root: Path) -> None:
    Path(path_value).resolve(strict=False).relative_to(root.resolve(strict=False))


def test_valid_in_root_duplicate_scan_succeeds(bus_client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    client = bus_client["client"]
    root = tmp_path / "allowed"
    start = root / "scan"
    start.mkdir(parents=True)
    (start / "keeper.txt").write_text("same", encoding="utf-8")
    (start / "duplicate.txt").write_text("same", encoding="utf-8")
    quarantine = root / "quarantine"
    saved = _configure_organizer(monkeypatch, root)

    response = client.post(
        "/organizer/duplicates/plan",
        json={"start_path": str(start), "quarantine_dir": str(quarantine)},
    )

    assert response.status_code == 200
    assert response.json()["actions"] == 1
    assert len(saved) == 1
    action = saved[0].actions[0]
    _assert_under(action.meta["src_path"], start)
    _assert_under(action.meta["dst_path"], root)
    assert Path(action.meta["dst_parent_path"]).resolve(strict=False) == quarantine.resolve(strict=False)


def test_valid_in_root_rename_plan_succeeds(bus_client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    client = bus_client["client"]
    root = tmp_path / "allowed"
    start = root / "scan"
    start.mkdir(parents=True)
    source = start / "messy__name.txt"
    source.write_text("content", encoding="utf-8")
    saved = _configure_organizer(monkeypatch, root)

    response = client.post("/organizer/rename/plan", json={"start_path": str(start)})

    assert response.status_code == 200
    assert response.json()["actions"] == 1
    action = saved[0].actions[0]
    assert action.dst_name == "messy name.txt"
    assert Path(action.meta["dst_path"]).name == "messy name.txt"
    _assert_under(action.meta["src_path"], start)
    _assert_under(action.meta["dst_path"], start)


@pytest.mark.parametrize(
    "bad_start",
    [
        "../escape",
        "..\\escape",
        r"C:\Windows\System32",
        r"C:Windows\System32",
        r"\\server\share",
        r"\\?\C:\Windows\file",
        "bad\x00name",
    ],
)
@pytest.mark.parametrize("endpoint", ["/organizer/duplicates/plan", "/organizer/rename/plan"])
def test_traversal_and_platform_start_paths_rejected(
    bus_client,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    endpoint: str,
    bad_start: str,
):
    client = bus_client["client"]
    root = tmp_path / "allowed"
    root.mkdir()
    _configure_organizer(monkeypatch, root)

    response = client.post(endpoint, json={"start_path": bad_start})


    assert response.status_code in {400, 403}
    assert "Windows" not in response.text
    assert "server" not in response.text


@pytest.mark.parametrize("endpoint", ["/organizer/duplicates/plan", "/organizer/rename/plan"])
def test_absolute_path_outside_configured_root_rejected(
    bus_client,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    endpoint: str,
):
    client = bus_client["client"]
    root = tmp_path / "allowed"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    _configure_organizer(monkeypatch, root)

    response = client.post(endpoint, json={"start_path": str(outside)})

    assert response.status_code == 403
    assert str(outside) not in response.text


@pytest.mark.parametrize(
    "bad_name",
    [
        "../escape.txt",
        "..\\escape.txt",
        "nested/escape.txt",
        r"C:\Windows\System32\escape.txt",
        r"C:Windows\System32\escape.txt",
        r"\\server\share\escape.txt",
        r"\\?\C:\Windows\escape.txt",
        "bad\x00name.txt",
        "",
    ],
)
def test_malicious_normalized_name_cannot_escape_approved_root(
    bus_client,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    bad_name: str,
):
    import core.organizer.api as organizer_api

    client = bus_client["client"]
    root = tmp_path / "allowed"
    start = root / "scan"
    start.mkdir(parents=True)
    (start / "source.txt").write_text("content", encoding="utf-8")
    _configure_organizer(monkeypatch, root)
    monkeypatch.setattr(organizer_api, "normalize_filename", lambda _name: bad_name)

    response = client.post("/organizer/rename/plan", json={"start_path": str(start)})

    assert response.status_code in {400, 403}
    assert "Windows" not in response.text
    assert "server" not in response.text


def test_duplicate_quarantine_outside_approved_root_rejected(
    bus_client,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    client = bus_client["client"]
    root = tmp_path / "allowed"
    start = root / "scan"
    outside = tmp_path / "outside"
    start.mkdir(parents=True)
    outside.mkdir()
    (start / "a.txt").write_text("same", encoding="utf-8")
    (start / "b.txt").write_text("same", encoding="utf-8")
    _configure_organizer(monkeypatch, root)

    response = client.post(
        "/organizer/duplicates/plan",
        json={"start_path": str(start), "quarantine_dir": str(outside)},
    )

    assert response.status_code == 403
    assert str(outside) not in response.text


def test_organizer_path_sinks_route_through_pathsafe_helper() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    api_source = (repo_root / "core/organizer/api.py").read_text(encoding="utf-8")
    duplicates_source = (repo_root / "core/organizer/duplicates.py").read_text(encoding="utf-8")

    assert "resolve_path_under_roots" in api_source
    for forbidden in (
        "os.walk(",
        "os.stat(",
        "os.path.exists(",
        "os.path.isdir(",
        "os.path.isfile(",
        "os.path.join(",
        "os.path.commonpath(",
        "os.path.abspath(",
    ):
        assert forbidden not in api_source
        assert forbidden not in duplicates_source