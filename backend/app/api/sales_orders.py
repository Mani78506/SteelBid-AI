from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import or_, select

from app.core.deps import TenantContext, require
from app.core.errors import conflict, not_found
from app.core.pagination import Page, PageParams, apply_sort, paginate
from app.models.crm import Customer
from app.models.sales import SalesOrder, SalesOrderItem
from app.schemas.inventory import ReservationOut
from app.schemas.sales import (ReserveRequestIn, SalesOrderItemOut, SalesOrderOut,
                               SalesOrderStatusIn)
from app.services.audit import record_audit
from app.services.inventory import reserve_stock

router = APIRouter(prefix="/sales-orders", tags=["sales-orders"])

SO_FLOW = {
    "CONFIRMED": {"IN_PRODUCTION", "READY", "CANCELLED"},
    "IN_PRODUCTION": {"READY", "CANCELLED"},
    "READY": {"DISPATCHED", "CANCELLED"},
    "DISPATCHED": {"CLOSED"},
    "CLOSED": set(), "CANCELLED": set(),
}


def sales_order_out(ctx: TenantContext, so: SalesOrder) -> SalesOrderOut:
    customer = ctx.db.get(Customer, so.customer_id)
    items = ctx.db.scalars(select(SalesOrderItem).where(
        SalesOrderItem.sales_order_id == so.id)).all()
    out = SalesOrderOut.model_validate(so)
    out.customer_name = customer.name if customer else None
    out.items = [SalesOrderItemOut.model_validate(i) for i in items]
    return out


def get_so_scoped(ctx: TenantContext, so_id: UUID) -> SalesOrder:
    so = ctx.db.scalar(select(SalesOrder).where(SalesOrder.id == so_id,
                                                SalesOrder.organization_id == ctx.org_id))
    if so is None:
        raise not_found("Sales order")
    return so


@router.get("", response_model=Page[SalesOrderOut])
def list_sales_orders(ctx: TenantContext = Depends(require("read")),
                      params: PageParams = Depends(), search: str | None = Query(None),
                      status: str | None = Query(None)):
    stmt = select(SalesOrder).where(SalesOrder.organization_id == ctx.org_id)
    if search:
        stmt = stmt.where(or_(SalesOrder.number.ilike(f"%{search}%")))
    if status:
        stmt = stmt.where(SalesOrder.status == status)
    stmt = apply_sort(stmt, params.sort, {"created_at": SalesOrder.created_at,
                                          "number": SalesOrder.number},
                      SalesOrder.created_at.desc())
    rows, total = paginate(ctx.db, stmt, params)
    return Page(items=[sales_order_out(ctx, so) for so in rows], total=total,
                page=params.page, page_size=params.page_size)


@router.get("/{so_id}", response_model=SalesOrderOut)
def get_one(so_id: UUID, ctx: TenantContext = Depends(require("read"))):
    return sales_order_out(ctx, get_so_scoped(ctx, so_id))


@router.patch("/{so_id}/status", response_model=SalesOrderOut)
def set_status(so_id: UUID, body: SalesOrderStatusIn,
               ctx: TenantContext = Depends(require("sales_orders:write"))):
    so = get_so_scoped(ctx, so_id)
    allowed = SO_FLOW.get(so.status, set())
    if body.status not in allowed:
        raise conflict("INVALID_TRANSITION",
                       f"Cannot move sales order from {so.status} to {body.status}",
                       {"allowed": sorted(allowed)})
    before = so.status
    so.status = body.status
    record_audit(ctx, "sales_order.status", "sales_order", so.id,
                 {"before": {"status": before}, "after": {"status": body.status}})
    ctx.db.commit()
    return sales_order_out(ctx, so)


@router.post("/{so_id}/reserve", response_model=ReservationOut, status_code=201)
def reserve(so_id: UUID, body: ReserveRequestIn,
            idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
            ctx: TenantContext = Depends(require("inventory:transact"))):
    so = get_so_scoped(ctx, so_id)
    if so.status in ("CANCELLED", "CLOSED"):
        raise conflict("ORDER_CLOSED", f"Cannot reserve against a {so.status} order")
    item = ctx.db.scalar(select(SalesOrderItem).where(
        SalesOrderItem.id == body.sales_order_item_id,
        SalesOrderItem.sales_order_id == so.id, SalesOrderItem.organization_id == ctx.org_id))
    if item is None:
        raise not_found("Sales order item")
    reservation = reserve_stock(
        ctx, lot_id=body.lot_id, quantity=body.quantity,
        context={"sales_order_id": str(so.id), "sales_order_item_id": str(item.id)},
        idempotency_key=idempotency_key)
    item.reserved_qty = item.reserved_qty + body.quantity
    record_audit(ctx, "sales_order.reserve", "reservation", reservation.id,
                 {"after": {"so": so.number, "qty": body.quantity}})
    ctx.db.commit()
    return ReservationOut.model_validate(reservation)
