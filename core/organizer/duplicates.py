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

"""Helpers for discovering duplicate files within allowed roots."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List


@dataclass
class FileInfo:
    """Snapshot of a file encountered during a walk."""

    path: Path
    size: int
    mtime: float


def iter_files(root: Path) -> Iterator[FileInfo]:
    """Yield files under ``root`` along with metadata."""

    safe_root = root.resolve(strict=False)
    for candidate in safe_root.rglob("*"):
        try:
            resolved = candidate.resolve(strict=False)
            resolved.relative_to(safe_root)
            if not resolved.is_file():
                continue
            stat = resolved.stat()
        except (OSError, ValueError):
            continue
        yield FileInfo(resolved, stat.st_size, stat.st_mtime)


def sha256_of(path: Path, bufsize: int = 1024 * 1024) -> str:
    """Return SHA-256 digest for ``path`` using buffered reads."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(bufsize)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def find_duplicates(start_root: Path) -> Dict[str, List[Path]]:
    """Return mapping of sha256 digest -> duplicate file paths."""

    safe_root = start_root.resolve(strict=False)
    size_buckets: Dict[int, List[Path]] = {}
    for info in iter_files(safe_root):
        size_buckets.setdefault(info.size, []).append(info.path)

    duplicates: Dict[str, List[Path]] = {}
    for paths in size_buckets.values():
        if len(paths) < 2:
            continue
        digest_groups: Dict[str, List[Path]] = {}
        for path in paths:
            try:
                path.resolve(strict=False).relative_to(safe_root)
                digest = sha256_of(path)
            except (OSError, IOError, ValueError):
                continue
            digest_groups.setdefault(digest, []).append(path)
        for digest, group in digest_groups.items():
            if len(group) > 1:
                duplicates[digest] = group
    return duplicates


def pick_keeper(paths: List[Path]) -> Path:
    """Pick the file to keep among duplicates.

    The oldest modification time wins; ties fall back to shortest path length.
    Missing files are treated as newest so healthy files win.
    """

    ranked: List[tuple[float, int, Path]] = []
    for path in paths:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = float("inf")
        ranked.append((mtime, len(str(path)), path))
    ranked.sort()
    return ranked[0][2] if ranked else Path()
