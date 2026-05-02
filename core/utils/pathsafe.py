from __future__ import annotations

import ntpath
from pathlib import Path
from typing import Iterable


class PathSafetyError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _clean_path_value(path_value: str | Path) -> str:
    raw = str(path_value or "").strip()
    if not raw:
        raise PathSafetyError("path_empty")
    if "\x00" in raw:
        raise PathSafetyError("path_invalid")
    if raw.startswith(("\\\\?\\", "\\\\.\\", "\\\\", "//")):
        raise PathSafetyError("path_out_of_roots")
    drive, tail = ntpath.splitdrive(raw)
    if drive and not tail.startswith(("\\", "/")):
        raise PathSafetyError("path_out_of_roots")
    return raw


def resolve_path_under_roots(path_value: str | Path, allowed_roots: Iterable[Path]) -> Path:
    raw = _clean_path_value(path_value)
    candidate_input = Path(raw).expanduser()

    for root in allowed_roots:
        resolved_root = Path(root).expanduser().resolve(strict=False)
        candidate = candidate_input if candidate_input.is_absolute() else (resolved_root / candidate_input)
        resolved_candidate = candidate.expanduser().resolve(strict=False)
        try:
            resolved_candidate.relative_to(resolved_root)
        except ValueError:
            continue
        return resolved_candidate

    raise PathSafetyError("path_out_of_roots")