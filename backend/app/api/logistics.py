from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.core.deps import TenantContext, require
from app.core.errors import conflict, not_found
from app.core.pagination import Page, PageParams, paginate
from app.models.inventory import Warehouse
from app.models.ops import Dispatch, DispatchItem, Shipment
from app.models.sales import SalesOrder
from app.schemas.ops import DispatchIn, DispatchItemIn, DispatchOut
from app.services import inventory as inv_service
from app.services.audit import record_audit
from app.services.numbering import next_number

router = APIRouter(prefix="/logistics", tags=["logistics"])


def _d_out(ctx: TenantContext, d: Dispatch) -> DispatchOut:
    items = ctx.db.scalars(select(DispatchItem).where(DispatchItem.dispatch_id == d.id)).all()
    out = DispatchOut.model_validate(d)
    out.items = [{"id": str(i.id), "material_id": str(i.material_id), "quantity": str(i.quantity),
                  "unit": i.unit, "stock_lot_id": str(i.stock_lot_id) if i.stock_lot_id else None}
                 for i in items]
    return out


@router.get("/dispatches", response_model=Page[DispatchOut])
def list_dispatches(ctx: TenantContext = Depends(require("read")),
                    params: PageParams = Depends(), status: str | None = Query(None)):
    stmt = select(Dispatch).where(Dispatch.organization_id == ctx.org_id)
    if status:
        stmt = stmt.where(Dispatch.status == status)
    stmt = stmt.order_by(Dispatch.created_at.desc())
    rows, total = paginate(ctx.db, stmt, params)
    return Page(items=[_d_out(ctx, d) for d in rows], total=total,
                page=params.page, page_size=params.page_size)


@router.post("/dispatches", response_model=DispatchOut, status_code=201)
def create_dispatch(body: DispatchIn,
                    ctx: TenantContext = Depends(require("logistics:write"))):
    wh = ctx.db.get(Warehouse, body.warehouse_id)
    if wh is None or wh.organization_id != ctx.org_id:
        raise not_found("Warehouse")
    if body.sales_order_id:
        so = ctx.db.get(SalesOrder, body.sales_order_id)
        if so is None or so.organization_id != ctx.org_id:
            raise not_found("Sales order")
    d = Dispatch(organization_id=ctx.org_id,
                 number=next_number(ctx.db, Dispatch, ctx.org_id, prefix="DSP"),
                 status="PLANNED", **body.model_dump(exclude={"items"}))
    ctx.db.add(d)
    ctx.db.flush()
    for item_in in body.items:
        ctx.db.add(DispatchItem(organization_id=ctx.org_id, dispatch_id=d.id,
                                **item_in.model_dump()))
    record_audit(ctx, "dispatch.create", "dispatch", d.id,
                 {"after": {"number": d.number, "items": len(body.items)}})
    ctx.db.commit()
    return _d_out(ctx, d)


@router.get("/dispatches/{dispatch_id}", response_model=DispatchOut)
def get_dispatch(dispatch_id: UUID, ctx: TenantContext = Depends(require("read"))):
    d = ctx.db.scalar(select(Dispatch).where(Dispatch.id == dispatch_id,
                                             Dispatch.organization_id == ctx.org_id))
    if d is None:
        raise not_found("Dispatch")
    return _d_out(ctx, d)


@router.post("/dispatches/{dispatch_id}/ship", response_model=DispatchOut)
def ship_dispatch(dispatch_id: UUID, ctx: TenantContext = Depends(require("logistics:write"))):
    """Mark dispatched: issues the reserved stock (consumes reservations) in one transaction."""
    d = ctx.db.scalar(select(Dispatch).where(Dispatch.id == dispatch_id,
                                             Dispatch.organization_id == ctx.org_id))
    if d is None:
        raise not_found("Dispatch")
    if d.status not in ("PLANNED", "READY", "PICKING"):
        raise conflict("INVALID_TRANSITION", f"Dispatch is {d.status}")
    items = ctx.db.scalars(select(DispatchItem).where(DispatchItem.dispatch_id == d.id)).all()
    for item in items:
        if item.stock_lot_id:
            inv_service.issue_stock(ctx, lot_id=item.stock_lot_id, quantity=item.quantity,
                                    movement_type="ISSUE",
                                    reference={"dispatch_id": str(d.id)})
    d.status = "DISPATCHED"
    if d.sales_order_id:
        so = ctx.db.get(SalesOrder, d.sales_order_id)
        if so and so.status == "READY":
            so.status = "DISPATCHED"
    ctx.db.add(Shipment(organization_id=ctx.org_id, dispatch_id=d.id, status="IN_TRANSIT",
                        tracking_ref=f"TRK-{d.number}"))
    record_audit(ctx, "dispatch.ship", "dispatch", d.id, {"after": {"status": "DISPATCHED"}})
    ctx.db.commit()
    return _d_out(ctx, d)
