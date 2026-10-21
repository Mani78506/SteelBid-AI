from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy import select
from app.core.deps import TenantContext, require
from app.core.errors import not_found
from app.models.ops import Notification

router = APIRouter(prefix="/notifications", tags=["notifications"])

def _out(n: Notification):
    return {"id": str(n.id), "kind": n.kind, "title": n.title, "body": n.body, "link": n.link,
            "is_read": n.is_read, "created_at": n.created_at.isoformat()}

@router.get("")
def list_notifications(ctx: TenantContext = Depends(require("read"))):
    rows = ctx.db.scalars(select(Notification).where(Notification.organization_id == ctx.org_id,
        (Notification.user_id == ctx.user_id) | (Notification.user_id.is_(None))).order_by(Notification.created_at.desc()).limit(50)).all()
    return {"items": [_out(row) for row in rows], "unread_count": sum(not row.is_read for row in rows)}

@router.post("/{notification_id}/read")
def mark_read(notification_id: UUID, ctx: TenantContext = Depends(require("read"))):
    row = ctx.db.scalar(select(Notification).where(Notification.id == notification_id, Notification.organization_id == ctx.org_id,
        (Notification.user_id == ctx.user_id) | (Notification.user_id.is_(None))))
    if row is None: raise not_found("Notification")
    row.is_read = True; ctx.db.commit(); return _out(row)
