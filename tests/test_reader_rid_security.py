# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import os

import pytest

from core.plans.commit import commit_local
from core.plans.model import Action, ActionKind, Plan
from core.reader import api as reader_api
from core.reader.ids import _b64e, _legacy_root_signature, rid_to_path, to_rid


def _legacy_rid(root: str, rel_path: str) -> str:
    return f"local:{_legacy_root_signature(root)}:{_b64e(rel_path)}"


def test_legacy_rid_resolves(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    p = root / "dir" / "a.txt"
    p.parent.mkdir(parents=True)
    p.write_text("x", encoding="utf-8")

    rid = _legacy_rid(str(root), os.path.join("dir", "a.txt"))

    assert rid_to_path(rid, [str(root)]) == os.path.normpath(str(p))


def test_v2_rid_resolves_and_is_emitted(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    p = root / "a.txt"
    p.write_text("x", encoding="utf-8")

    rid = to_rid(str(p), [str(root)])

    assert rid.startswith("local:v2:")
    assert rid_to_path(rid, [str(root)]) == os.path.normpath(str(p))


@pytest.mark.parametrize(
    "rid",
    [
        "",
        "local",
        "local:",
        "local:abc:def",
        "local:v2:abc:def",
        "local:v3:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:Zg",
        "remote:v2:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:Zg",
        "local:zzzzzzzzzz:Zg",
        "local:v2:zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz:Zg",
    ],
)
def test_malformed_rids_fail_closed(tmp_path, rid):
    root = tmp_path / "root"
    root.mkdir()

    with pytest.raises(ValueError):
        rid_to_path(rid, [str(root)])


def test_invalid_base64_payload_rejected(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    rid = "local:v2:" + ("a" * 32) + ":***"

    with pytest.raises(ValueError):
        rid_to_path(rid, [str(root)])


def test_root_signature_mismatch_rejected(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    rid = "local:v2:" + ("0" * 32) + ":" + _b64e("a.txt")

    with pytest.raises(ValueError, match="rid_root_not_found"):
        rid_to_path(rid, [str(root)])


def test_traversal_payload_rejected(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    rid = "local:v2:" + ("0" * 32) + ":" + _b64e("..\\escape.txt")

    with pytest.raises(ValueError):
        rid_to_path(rid, [str(root)])


def test_reader_resolve_paths_mixed_old_new_and_bad(tmp_path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "root"
    root.mkdir()
    p = root / "dir" / "x.txt"
    p.parent.mkdir(parents=True)
    p.write_text("x", encoding="utf-8")

    rid_v2 = to_rid(str(p), [str(root)])
    rid_legacy = _legacy_rid(str(root), os.path.join("dir", "x.txt"))
    rid_bad = "local:v2:" + ("f" * 32) + ":***"

    monkeypatch.setattr(reader_api, "get_allowed_local_roots", lambda: [str(root)])
    out = reader_api.resolve_paths(reader_api.IdsBody(ids=[rid_v2, rid_legacy, rid_bad]))

    assert out[rid_v2] == os.path.normpath(str(p))
    assert out[rid_legacy] == os.path.normpath(str(p))
    assert out[rid_bad] is None


def test_commit_mixed_legacy_src_and_v2_parent_succeeds(tmp_path, monkeypatch: pytest.MonkeyPatch):
    src_root = tmp_path / "src-root"
    dst_root = tmp_path / "dst-root"
    src_root.mkdir()
    dst_root.mkdir()

    src = src_root / "old.txt"
    src.write_text("hello", encoding="utf-8")

    src_id = _legacy_rid(str(src_root), "old.txt")
    dst_parent_id = to_rid(str(dst_root), [str(dst_root)])

    plan = Plan(
        id="p1",
        source="test",
        title="mixed",
        actions=[
            Action(
                id="a1",
                kind=ActionKind.MOVE,
                src_id=src_id,
                dst_parent_id=dst_parent_id,
                dst_name="new.txt",
                meta={
                    "src_path": str(src),
                    "dst_parent_path": str(dst_root),
                },
            )
        ],
    )

    monkeypatch.setattr("core.plans.commit.get_allowed_local_roots", lambda: [str(src_root), str(dst_root)])

    result = commit_local(plan)

    assert result["ok"] is True
    assert (dst_root / "new.txt").exists()
    assert not src.exists()


def test_commit_fails_closed_when_rid_present_but_invalid(tmp_path, monkeypatch: pytest.MonkeyPatch):
    src_root = tmp_path / "src-root"
    dst_root = tmp_path / "dst-root"
    src_root.mkdir()
    dst_root.mkdir()

    src = src_root / "old.txt"
    src.write_text("hello", encoding="utf-8")

    bad_src_id = "local:v2:" + ("0" * 32) + ":" + _b64e("old.txt")
    dst_parent_id = to_rid(str(dst_root), [str(dst_root)])

    plan = Plan(
        id="p2",
        source="test",
        title="invalid rid",
        actions=[
            Action(
                id="a1",
                kind=ActionKind.MOVE,
                src_id=bad_src_id,
                dst_parent_id=dst_parent_id,
                dst_name="new.txt",
                meta={
                    "src_path": str(src),
                    "dst_parent_path": str(dst_root),
                },
            )
        ],
    )

    monkeypatch.setattr("core.plans.commit.get_allowed_local_roots", lambda: [str(src_root), str(dst_root)])

    result = commit_local(plan)

    assert result["ok"] is False
    assert result["results"][0]["status"] == "error"
    assert src.exists()
    assert not (dst_root / "new.txt").exists()
