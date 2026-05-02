from __future__ import annotations

import ntpath
from pathlib import Path, PurePosixPath, PureWindowsPath
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
    if raw.startswith(("~", "~/", "~\\")):
        raise PathSafetyError("path_out_of_roots")
    if raw.startswith(("\\\\?\\", "\\\\.\\", "\\\\", "//")):
        raise PathSafetyError("path_out_of_roots")
    drive, tail = ntpath.splitdrive(raw)
    if drive and not tail.startswith(("\\", "/")):
        raise PathSafetyError("path_out_of_roots")
    split_parts = [part for part in raw.replace("\\", "/").split("/") if part not in ("", ".")]
    if any(part == ".." for part in split_parts):
        raise PathSafetyError("path_out_of_roots")
    return raw


def _is_windows_like_path(raw: str) -> bool:
    drive, _tail = ntpath.splitdrive(raw)
    return bool(drive) or "\\" in raw


def _pure_path(raw: str) -> PureWindowsPath | PurePosixPath:
    if _is_windows_like_path(raw):
        return PureWindowsPath(raw)
    return PurePosixPath(raw)


def _user_relative_parts(raw: str) -> tuple[object, ...]:
    pure_path = _pure_path(raw)
    return tuple(part for part in pure_path.parts if part not in (pure_path.anchor, ""))


def resolve_path_under_roots(path_value: str | Path, allowed_roots: Iterable[Path]) -> Path:
    raw = _clean_path_value(path_value)
    pure_input = _pure_path(raw)
    candidate_parts = _user_relative_parts(raw)

    for root in allowed_roots:
        resolved_root = Path(root).resolve(strict=False)
        pure_root = _pure_path(str(resolved_root))
        if pure_input.is_absolute():
            try:
                relative_parts = pure_input.relative_to(pure_root).parts
            except ValueError:
                continue
            candidate = resolved_root.joinpath(*relative_parts)
        else:
            candidate = resolved_root.joinpath(*candidate_parts)
        resolved_candidate = candidate.resolve(strict=False)
        try:
            resolved_candidate.relative_to(resolved_root)
        except ValueError:
            continue
        return resolved_candidate

    raise PathSafetyError("path_out_of_roots")