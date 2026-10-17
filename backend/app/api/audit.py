from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.core.deps import TenantContext, require
from app.core.pagination import Page, PageParams, paginate
from app.models.ops import AuditEvent
from app.schemas.common import AuditEventOut

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/events", response_model=Page[AuditEventOut])
def list_events(ctx: TenantContext = Depends(require("audit:read")),
                params: PageParams = Depends(),
                entity_type: str | None = Query(None),
                action: str | None = Query(None),
                entity_id: UUID | None = Query(None)):
    stmt = select(AuditEvent).where(AuditEvent.organization_id == ctx.org_id)
    if entity_type:
        stmt = stmt.where(AuditEvent.entity_type == entity_type)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    if entity_id:
        stmt = stmt.where(AuditEvent.entity_id == entity_id)
    stmt = stmt.order_by(AuditEvent.created_at.desc())
    rows, total = paginate(ctx.db, stmt, params)
    return Page(items=[AuditEventOut.model_validate(r) for r in rows], total=total,
                page=params.page, page_size=params.page_size)
