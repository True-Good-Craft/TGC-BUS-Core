# SPDX-License-Identifier: AGPL-3.0-or-later
"""Audit event helper for future claimed-mode auth actions."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from core.appdb.models import AuthAuditEvent


def create_audit_event(
    db: Session,
    *,
    action: str,
    actor_user_id: int | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    request_id: str | None = None,
    detail: Mapping[str, Any] | None = None,
) -> AuthAuditEvent:
    if not action:
        raise ValueError("audit_action_required")
    detail_json = None
    if detail is not None:
        detail_json = json.dumps(dict(detail), sort_keys=True, separators=(",", ":"))
    event = AuthAuditEvent(
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        request_id=request_id,
        detail_json=detail_json,
    )
    db.add(event)
    return event


__all__ = ["create_audit_event"]
