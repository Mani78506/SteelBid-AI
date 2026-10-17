from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import select

from app.calc.finance import inventory_valuation, q_money
from app.core.deps import TenantContext, require
from app.core.errors import bad_request, not_found
from app.core.pagination import Page, PageParams, apply_sort, paginate
from app.models.inventory import (InventoryMovement, Reservation, StockLot, StorageLocation,
                                  Warehouse)
from app.models.materials import OrganizationMaterial
from app.schemas.inventory import (AdjustmentIn, IssueIn, LocationIn, LocationOut,
                                   MovementOut, ReceiptIn, ReservationOut, ReserveIn,
                                   StockLotOut, TransferIn, WarehouseIn, WarehouseOut)
from app.services import inventory as inv
from app.services.audit import record_audit
from app.services.inventory import handle_integrity_error

router = APIRouter(prefix="/inventory", tags=["inventory"])


# ---------- Warehouses & locations ----------
@router.get("/warehouses", response_model=list[WarehouseOut])
def list_warehouses(ctx: TenantContext = Depends(require("read"))):
    rows = ctx.db.scalars(select(Warehouse).where(
        Warehouse.organization_id == ctx.org_id, Warehouse.is_active.is_(True))
        .order_by(Warehouse.code)).all()
    return [WarehouseOut.model_validate(r) for r in rows]


@router.post("/warehouses", response_model=WarehouseOut, status_code=201)
def create_warehouse(body: WarehouseIn, ctx: TenantContext = Depends(require("warehouses:write"))):
    w = Warehouse(organization_id=ctx.org_id, **body.model_dump())
    ctx.db.add(w)
    ctx.db.flush()
    record_audit(ctx, "warehouse.create", "warehouse", w.id, {"after": body.model_dump()})
    ctx.db.commit()
    return WarehouseOut.model_validate(w)


@router.get("/storage-locations", response_model=list[LocationOut])
def list_locations(ctx: TenantContext = Depends(require("read")),
                   warehouse_id: UUID | None = Query(None)):
    stmt = select(StorageLocation).where(StorageLocation.organization_id == ctx.org_id)
    if warehouse_id:
        stmt = stmt.where(StorageLocation.warehouse_id == warehouse_id)
    rows = ctx.db.scalars(stmt.order_by(StorageLocation.code)).all()
    return [LocationOut.model_validate(r) for r in rows]


@router.post("/storage-locations", response_model=LocationOut, status_code=201)
def create_location(body: LocationIn, ctx: TenantContext = Depends(require("warehouses:write"))):
    w = ctx.db.get(Warehouse, body.warehouse_id)
    if w is None or w.organization_id != ctx.org_id:
        raise not_found("Warehouse")
    loc = StorageLocation(organization_id=ctx.org_id, **body.model_dump())
    ctx.db.add(loc)
    ctx.db.commit()
    return LocationOut.model_validate(loc)


# ---------- Stock lots ----------
def _lot_out(ctx: TenantContext, lot: StockLot) -> StockLotOut:
    mat = ctx.db.get(OrganizationMaterial, lot.material_id)
    wh = ctx.db.get(Warehouse, lot.warehouse_id)
    out = StockLotOut.model_validate(lot)
    out.material_sku = mat.sku if mat else None
    out.material_name = mat.name if mat else None
    out.warehouse_name = wh.name if wh else None
    out.available_qty = max(Decimal("0"), lot.on_hand_qty - lot.reserved_qty)
    return out


@router.get("/stock-lots", response_model=Page[StockLotOut])
def list_lots(ctx: TenantContext = Depends(require("read")),
              params: PageParams = Depends(), warehouse_id: UUID | None = Query(None),
              material_id: UUID | None = Query(None), quality_status: str | None = Query(None),
              search: str | None = Query(None)):
    stmt = select(StockLot).where(StockLot.organization_id == ctx.org_id)
    if warehouse_id:
        stmt = stmt.where(StockLot.warehouse_id == warehouse_id)
    if material_id:
        stmt = stmt.where(StockLot.material_id == material_id)
    if quality_status:
        stmt = stmt.where(StockLot.quality_status == quality_status)
    if search:
        stmt = stmt.where((StockLot.lot_number.ilike(f"%{search}%"))
                          | (StockLot.heat_number.ilike(f"%{search}%")))
    stmt = apply_sort(stmt, params.sort, {"created_at": StockLot.created_at,
                                          "lot_number": StockLot.lot_number},
                      StockLot.created_at.desc())
    rows, total = paginate(ctx.db, stmt, params)
    return Page(items=[_lot_out(ctx, lot) for lot in rows], total=total,
                page=params.page, page_size=params.page_size)


@router.get("/stock-lots/{lot_id}", response_model=StockLotOut)
def get_lot(lot_id: UUID, ctx: TenantContext = Depends(require("read"))):
    lot = ctx.db.scalar(select(StockLot).where(StockLot.id == lot_id,
                                               StockLot.organization_id == ctx.org_id))
    if lot is None:
        raise not_found("Stock lot")
    return _lot_out(ctx, lot)


# ---------- Transactions ----------
@router.post("/receipts", response_model=StockLotOut, status_code=201)
def receipt(body: ReceiptIn, idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
            ctx: TenantContext = Depends(require("inventory:transact"))):
    _validate_refs(ctx, body.material_id, body.warehouse_id)
    try:
        lot = inv.receive_stock(
            ctx, material_id=body.material_id, warehouse_id=body.warehouse_id,
            lot_number=body.lot_number, quantity=body.quantity, unit=body.unit,
            heat_number=body.heat_number, unit_cost=body.unit_cost,
            quality_status=body.quality_status, received_on=body.received_on,
            idempotency_key=idempotency_key)
    except Exception as exc:
        ctx.db.rollback()
        from sqlalchemy.exc import IntegrityError
        if isinstance(exc, IntegrityError):
            raise handle_integrity_error(exc)
        raise
    record_audit(ctx, "inventory.receipt", "stock_lot", lot.id,
                 {"after": {"qty": body.quantity, "lot": body.lot_number}})
    ctx.db.commit()
    return _lot_out(ctx, lot)


@router.post("/issues", response_model=StockLotOut, status_code=201)
def issue(body: IssueIn, idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
          ctx: TenantContext = Depends(require("inventory:transact"))):
    lot = inv.issue_stock(ctx, lot_id=body.lot_id, quantity=body.quantity,
                          movement_type=body.movement_type,
                          reference={"reason": body.reason} if body.reason else {},
                          idempotency_key=idempotency_key)
    record_audit(ctx, "inventory.issue", "stock_lot", lot.id,
                 {"after": {"qty": body.quantity, "type": body.movement_type}})
    ctx.db.commit()
    return _lot_out(ctx, lot)


@router.post("/adjustments", response_model=StockLotOut, status_code=201)
def adjustment(body: AdjustmentIn, idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
               ctx: TenantContext = Depends(require("inventory:adjust"))):
    lot = inv.adjust_stock(ctx, lot_id=body.lot_id, new_on_hand=body.new_on_hand,
                           reason=body.reason, idempotency_key=idempotency_key)
    record_audit(ctx, "inventory.adjust", "stock_lot", lot.id,
                 {"after": {"new_on_hand": body.new_on_hand, "reason": body.reason}})
    ctx.db.commit()
    return _lot_out(ctx, lot)


@router.post("/reservations", response_model=ReservationOut, status_code=201)
def make_reservation(body: ReserveIn, idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                     ctx: TenantContext = Depends(require("inventory:transact"))):
    reservation = inv.reserve_stock(ctx, lot_id=body.lot_id, quantity=body.quantity,
                                    context=body.context, idempotency_key=idempotency_key)
    record_audit(ctx, "inventory.reserve", "reservation", reservation.id,
                 {"after": {"qty": body.quantity}})
    ctx.db.commit()
    return ReservationOut.model_validate(reservation)


@router.get("/reservations", response_model=list[ReservationOut])
def list_reservations(ctx: TenantContext = Depends(require("read")),
                      status: str = Query("ACTIVE")):
    rows = ctx.db.scalars(select(Reservation).where(
        Reservation.organization_id == ctx.org_id, Reservation.status == status)
        .order_by(Reservation.created_at.desc())).all()
    return [ReservationOut.model_validate(r) for r in rows]


@router.post("/reservations/{reservation_id}/release", response_model=ReservationOut)
def release_reservation(reservation_id: UUID,
                        ctx: TenantContext = Depends(require("inventory:transact"))):
    r = inv.unreserve_stock(ctx, reservation_id=reservation_id)
    record_audit(ctx, "inventory.release", "reservation", r.id, {})
    ctx.db.commit()
    return ReservationOut.model_validate(r)


@router.post("/transfers", response_model=StockLotOut, status_code=201)
def transfer(body: TransferIn, ctx: TenantContext = Depends(require("inventory:transact"))):
    target = ctx.db.get(Warehouse, body.to_warehouse_id)
    if target is None or target.organization_id != ctx.org_id:
        raise not_found("Target warehouse")
    from app.models.inventory import StockTransfer
    from app.services.inventory import get_lot_for_update
    from app.calc.finance import q_qty
    if body.quantity <= 0:
        raise bad_request("INVALID_QUANTITY", "Transfer quantity must be positive")
    lot = get_lot_for_update(ctx.db, ctx.org_id, body.lot_id)
    if lot.warehouse_id == body.to_warehouse_id:
        raise bad_request("SAME_WAREHOUSE", "Lot already in target warehouse")
    available = lot.on_hand_qty - lot.reserved_qty
    if available < body.quantity:
        from app.core.errors import conflict
        raise conflict("INSUFFICIENT_STOCK", "Insufficient unreserved stock to transfer")
    lot.on_hand_qty = q_qty(lot.on_hand_qty - body.quantity)
    inv._write_movement(ctx, lot, "TRANSFER_OUT", -body.quantity,
                        {"to_warehouse_id": str(body.to_warehouse_id)}, None)
    new_lot = inv.receive_stock(
        ctx, material_id=lot.material_id, warehouse_id=body.to_warehouse_id,
        lot_number=lot.lot_number, quantity=body.quantity, unit=lot.unit,
        heat_number=lot.heat_number, unit_cost=lot.unit_cost, quality_status=lot.quality_status,
        reference={"transfer_from_warehouse_id": str(lot.warehouse_id)})
    ctx.db.add(StockTransfer(
        organization_id=ctx.org_id, stock_lot_id=lot.id, from_warehouse_id=lot.warehouse_id,
        to_warehouse_id=body.to_warehouse_id, quantity=body.quantity, created_by=ctx.user_id))
    record_audit(ctx, "inventory.transfer", "stock_lot", lot.id,
                 {"after": {"qty": body.quantity, "to": str(body.to_warehouse_id)}})
    ctx.db.commit()
    return _lot_out(ctx, new_lot)


# ---------- Ledger & valuation ----------
@router.get("/movements", response_model=Page[MovementOut])
def movements(ctx: TenantContext = Depends(require("read")),
              params: PageParams = Depends(), material_id: UUID | None = Query(None),
              warehouse_id: UUID | None = Query(None),
              movement_type: str | None = Query(None)):
    stmt = select(InventoryMovement).where(InventoryMovement.organization_id == ctx.org_id)
    if material_id:
        stmt = stmt.where(InventoryMovement.material_id == material_id)
    if warehouse_id:
        stmt = stmt.where(InventoryMovement.warehouse_id == warehouse_id)
    if movement_type:
        stmt = stmt.where(InventoryMovement.movement_type == movement_type)
    stmt = stmt.order_by(InventoryMovement.created_at.desc())
    rows, total = paginate(ctx.db, stmt, params)
    return Page(items=[MovementOut.model_validate(r) for r in rows], total=total,
                page=params.page, page_size=params.page_size)


@router.get("/valuation")
def valuation(ctx: TenantContext = Depends(require("read")),
              warehouse_id: UUID | None = Query(None)):
    stmt = select(StockLot).where(StockLot.organization_id == ctx.org_id,
                                  StockLot.unit_cost.isnot(None))
    if warehouse_id:
        stmt = stmt.where(StockLot.warehouse_id == warehouse_id)
    lots = ctx.db.scalars(stmt).all()
    total = inventory_valuation([(l.on_hand_qty, l.unit_cost) for l in lots])
    by_warehouse: dict[str, dict] = {}
    for lot in lots:
        wh = by_warehouse.setdefault(str(lot.warehouse_id), {"value": Decimal("0"), "qty": Decimal("0")})
        wh["value"] += lot.on_hand_qty * lot.unit_cost
        wh["qty"] += lot.on_hand_qty
    return {
        "total_value": str(q_money(total)),
        "currency": ctx.organization.currency_code,
        "by_warehouse": {k: {"value": str(q_money(v["value"])), "qty": str(v["qty"])}
                         for k, v in by_warehouse.items()},
    }


def _validate_refs(ctx: TenantContext, material_id: UUID, warehouse_id: UUID):
    mat = ctx.db.get(OrganizationMaterial, material_id)
    if mat is None or mat.organization_id != ctx.org_id:
        raise not_found("Material")
    wh = ctx.db.get(Warehouse, warehouse_id)
    if wh is None or wh.organization_id != ctx.org_id:
        raise not_found("Warehouse")
