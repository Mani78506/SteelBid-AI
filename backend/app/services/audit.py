"""Audit logging — every meaningful mutation records an append-only event."""
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.models.ops import AuditEvent


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date, UUID)):
        return value.isoformat() if not isinstance(value, UUID) else str(value)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def record_audit(ctx, action: str, entity_type: str, entity_id, diff: dict | None = None) -> AuditEvent:
    event = AuditEvent(
        organization_id=ctx.org_id,
        user_id=ctx.user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        diff=_jsonable(diff or {}),
        request_id=ctx.request_id,
    )
    ctx.db.add(event)
    return event
