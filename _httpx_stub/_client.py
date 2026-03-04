# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations


class UseClientDefault:
    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return "USE_CLIENT_DEFAULT"


USE_CLIENT_DEFAULT = UseClientDefault()

__all__ = ["USE_CLIENT_DEFAULT", "UseClientDefault"]
