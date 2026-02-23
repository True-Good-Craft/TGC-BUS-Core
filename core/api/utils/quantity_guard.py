# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from fastapi import HTTPException

LEGACY_QTY_KEYS = {"qty", "qty_base", "quantity_int", "quantity", "output_qty", "qty_required", "raw_qty"}


def find_legacy_qty_keys(obj) -> set[str]:
    found: set[str] = set()

    def walk(value):
        if isinstance(value, dict):
            for key, nested in value.items():
                if key in LEGACY_QTY_KEYS:
                    found.add(key)
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    walk(obj)
    return found


def reject_legacy_qty_keys(obj) -> None:
    matches = find_legacy_qty_keys(obj)
    if matches:
        raise HTTPException(
            status_code=400,
            detail={"error": "legacy_quantity_keys_forbidden", "keys": sorted(list(matches))},
        )
