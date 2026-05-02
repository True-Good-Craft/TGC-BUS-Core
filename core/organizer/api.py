# SPDX-License-Identifier: AGPL-3.0-or-later
# TGC BUS Core (Business Utility System Core)
# Copyright (C) 2025 True Good Craft
#
# This file is part of TGC BUS Core.
#
# TGC BUS Core is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# TGC BUS Core is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with TGC BUS Core.  If not, see <https://www.gnu.org/licenses/>.

"""Organizer API endpoints for generating file operation plans."""

from __future__ import annotations

import ntpath
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.organizer.duplicates import find_duplicates, pick_keeper
from core.organizer.rename import normalize_filename
from core.plans.model import Action, ActionKind, Plan
from core.plans.store import save_plan
from core.reader.ids import to_rid
from core.settings.reader_state import get_allowed_local_roots
from core.utils.pathsafe import PathSafetyError, resolve_path_under_roots

router = APIRouter(prefix="/organizer", tags=["organizer"])


class DupBody(BaseModel):
    start_path: str
    quarantine_dir: Optional[str] = None


class RenameBody(BaseModel):
    start_path: str


def _path_error(exc: PathSafetyError) -> HTTPException:
    status_code = 400 if exc.code in {"path_empty", "path_invalid"} else 403
    return HTTPException(status_code=status_code, detail=exc.code)


def _allowed_roots() -> List[Path]:
    return [Path(root) for root in get_allowed_local_roots() if isinstance(root, str) and root.strip()]


def _resolve_organizer_path(path_value: str, roots: List[Path]) -> tuple[Path, Path]:
    try:
        resolved = resolve_path_under_roots(path_value, roots)
    except PathSafetyError as exc:
        raise _path_error(exc) from exc
    for root in roots:
        resolved_root = root.resolve(strict=False)
        try:
            resolved.relative_to(resolved_root)
        except ValueError:
            continue
        return resolved, resolved_root
    raise HTTPException(status_code=403, detail="path_out_of_roots")


def _require_directory(path_value: str, roots: List[Path]) -> tuple[Path, Path]:
    resolved, approved_root = _resolve_organizer_path(path_value, roots)
    if not resolved.exists():
        raise HTTPException(status_code=404, detail="start_path_not_found")
    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail="start_path_not_directory")
    return resolved, approved_root


def _resolve_generated_path(path: Path, approved_root: Path) -> Path:
    try:
        return resolve_path_under_roots(path, [approved_root])
    except PathSafetyError as exc:
        raise _path_error(exc) from exc


def _resolve_child_filename(parent: Path, filename: str) -> Path:
    raw = str(filename or "")
    if not raw or "\x00" in raw or "/" in raw or "\\" in raw or ":" in raw or raw in {".", ".."}:
        raise HTTPException(status_code=400, detail="filename_invalid")
    drive, _tail = ntpath.splitdrive(raw)
    if drive:
        raise HTTPException(status_code=400, detail="filename_invalid")
    try:
        resolved = resolve_path_under_roots(raw, [parent])
    except PathSafetyError as exc:
        raise _path_error(exc) from exc
    if resolved.parent != parent.resolve(strict=False):
        raise HTTPException(status_code=403, detail="path_out_of_roots")
    return resolved


def _maybe_to_rid(path: Path, roots: List[str]) -> Optional[str]:
    try:
        return to_rid(str(path), roots)
    except Exception:
        return None


@router.post("/duplicates/plan")
def duplicates_plan(body: DupBody):
    roots = _allowed_roots()
    start, approved_root = _require_directory(body.start_path, roots)
    root_strings = [str(root) for root in roots]
    if body.quarantine_dir:
        quarantine_dir = _resolve_organizer_path(body.quarantine_dir, [approved_root])[0]
    else:
        quarantine_dir = _resolve_generated_path(start / "Quarantine" / "Duplicates", approved_root)
    quarantine_dir.mkdir(parents=True, exist_ok=True)

    duplicates = find_duplicates(start)
    actions: List[Action] = []
    for digest, group in duplicates.items():
        keeper = pick_keeper(group)
        counter = 1
        for path in group:
            if path == keeper:
                continue
            name = path.name
            destination = _resolve_child_filename(quarantine_dir, name)
            base = Path(name).stem
            ext = Path(name).suffix
            suffix = 1
            while destination.exists():
                destination = _resolve_child_filename(quarantine_dir, f"{base}-dup{suffix}{ext}")
                suffix += 1
            action = Action(
                id=f"dup-{digest[:8]}-{counter}",
                kind=ActionKind.MOVE,
                src_id=_maybe_to_rid(path, root_strings),
                dst_parent_id=_maybe_to_rid(destination.parent, root_strings),
                dst_name=destination.name,
                meta={
                    "src_path": str(path),
                    "dst_path": str(destination),
                    "dst_parent_path": str(destination.parent),
                    "dst_name": destination.name,
                },
            )
            actions.append(action)
            counter += 1

    plan = Plan(
        id=f"org-dup-{int(datetime.utcnow().timestamp())}",
        source="organizer",
        title=f"Organizer: Duplicates from {start.name}",
        note="Move duplicates to the approved quarantine folder",
        actions=actions,
    )
    save_plan(plan)
    return {"plan_id": plan.id, "actions": len(actions)}


@router.post("/rename/plan")
def rename_plan(body: RenameBody):
    roots = _allowed_roots()
    start, approved_root = _require_directory(body.start_path, roots)
    root_strings = [str(root) for root in roots]
    actions: List[Action] = []
    counter = 1
    for current_path in start.rglob("*"):
        current_path = _resolve_generated_path(current_path, approved_root)
        try:
            current_path.relative_to(start)
        except ValueError:
            continue
        if not current_path.is_file():
            continue
        filename = current_path.name
        normalized_name = normalize_filename(filename)
        if normalized_name == filename:
            continue
        destination_path = _resolve_child_filename(current_path.parent, normalized_name)
        try:
            destination_path.relative_to(start)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail="path_out_of_roots") from exc
        # Skip if another file already occupies the destination name.
        if destination_path.exists() and destination_path != current_path:
            continue
        action = Action(
            id=f"rn-{counter}",
            kind=ActionKind.RENAME,
            src_id=_maybe_to_rid(current_path, root_strings),
            dst_parent_id=_maybe_to_rid(current_path.parent, root_strings),
            dst_name=normalized_name,
            meta={
                "src_path": str(current_path),
                "dst_path": str(destination_path),
                "dst_parent_path": str(current_path.parent),
                "dst_name": normalized_name,
            },
        )
        actions.append(action)
        counter += 1

    plan = Plan(
        id=f"org-rn-{int(datetime.utcnow().timestamp())}",
        source="organizer",
        title=f"Organizer: Rename normalize under {start.name}",
        note="Conservative normalization of filenames",
        actions=actions,
    )
    save_plan(plan)
    return {"plan_id": plan.id, "actions": len(actions)}
