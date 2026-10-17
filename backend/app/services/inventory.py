"""Inventory ledger service — atomic, concurrency-safe stock mutations.

Every mutation: locks the stock lot row (SELECT ... FOR UPDATE), applies the delta,
writes a movement row with the resulting balance, all in ONE transaction.
DB CHECK constraints are the final backstop: on_hand >= 0, 0 <= reserved <= on_hand.
"""
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.calc.finance import ZERO, q_qty
from app.core.errors import bad_request, conflict, not_found
from app.models.inventory import InventoryMovement, Reservation, StockLot
from app.models.market import PriceObservation


def get_lot_for_update(db: Session, org_id: UUID, lot_id: UUID) -> StockLot:
    lot = db.scalar(
        select(StockLot).where(StockLot.id == lot_id, StockLot.organization_id == org_id)
        .with_for_update())
    if lot is None:
        raise not_found("Stock lot")
    return lot


def _write_movement(ctx, lot: StockLot, movement_type: str, quantity: Decimal,
                    reference: dict, idempotency_key: str | None) -> InventoryMovement:
    mv = InventoryMovement(
        organization_id=ctx.org_id, material_id=lot.material_id, warehouse_id=lot.warehouse_id,
        stock_lot_id=lot.id, movement_type=movement_type, quantity=q_qty(quantity), unit=lot.unit,
        balance_after_on_hand=lot.on_hand_qty, reference=reference,
        idempotency_key=idempotency_key, created_by=ctx.user_id)
    ctx.db.add(mv)
    return mv


def _check_idempotency(ctx, model, idempotency_key: str | None):
    if not idempotency_key:
        return None
    existing = ctx.db.scalar(
        select(model).where(model.organization_id == ctx.org_id,
                            model.idempotency_key == idempotency_key))
    return existing


def receive_stock(ctx, *, material_id: UUID, warehouse_id: UUID, lot_number: str,
                  quantity: Decimal, unit: str = "MT", heat_number: str | None = None,
                  unit_cost: Decimal | None = None, quality_status: str = "OK",
                  reference: dict | None = None, idempotency_key: str | None = None,
                  received_on: date | None = None) -> StockLot:
    """Stock receipt — creates or tops up a lot. Idempotent via idempotency_key."""
    if quantity <= 0:
        raise bad_request("INVALID_QUANTITY", "Receipt quantity must be positive")
    if quality_status not in ("OK", "QUARANTINED", "REJECTED"):
        raise bad_request("INVALID_QUALITY", "Quality status must be OK, QUARANTINED or REJECTED")
    if idempotency_key:
        existing_mv = _check_idempotency(ctx, InventoryMovement, idempotency_key)
        if existing_mv:
            return ctx.db.get(StockLot, existing_mv.stock_lot_id)
    lot = ctx.db.scalar(
        select(StockLot).where(
            StockLot.organization_id == ctx.org_id, StockLot.material_id == material_id,
            StockLot.warehouse_id == warehouse_id, StockLot.lot_number == lot_number)
        .with_for_update())
    if lot is None:
        lot = StockLot(
            organization_id=ctx.org_id, material_id=material_id, warehouse_id=warehouse_id,
            lot_number=lot_number, heat_number=heat_number, quality_status=quality_status,
            on_hand_qty=ZERO, reserved_qty=ZERO, unit=unit, unit_cost=unit_cost,
            source=reference or {})
        ctx.db.add(lot)
        ctx.db.flush()
    else:
        if heat_number:
            lot.heat_number = heat_number
        if unit_cost is not None:
            lot.unit_cost = unit_cost
        lot.quality_status = quality_status
    lot.on_hand_qty = q_qty(lot.on_hand_qty + quantity)
    ref = dict(reference or {})
    if received_on:
        ref["received_on"] = str(received_on)
    _write_movement(ctx, lot, "RECEIPT", quantity, ref, idempotency_key)
    return lot


def issue_stock(ctx, *, lot_id: UUID, quantity: Decimal, movement_type: str = "ISSUE",
                reference: dict | None = None, idempotency_key: str | None = None) -> StockLot:
    """Issue material from a lot (sales dispatch, consumption, scrap). Consumes reservations first."""
    if quantity <= 0:
        raise bad_request("INVALID_QUANTITY", "Issue quantity must be positive")
    if movement_type not in ("ISSUE", "CONSUME", "SCRAP"):
        raise bad_request("INVALID_MOVEMENT", "Invalid issue movement type")
    if idempotency_key:
        existing_mv = _check_idempotency(ctx, InventoryMovement, idempotency_key)
        if existing_mv:
            return ctx.db.get(StockLot, existing_mv.stock_lot_id)
    lot = get_lot_for_update(ctx.db, ctx.org_id, lot_id)
    issue_from_unreserved = max(ZERO, quantity - lot.reserved_qty)
    if lot.on_hand_qty - lot.reserved_qty < issue_from_unreserved:
        raise conflict("INSUFFICIENT_STOCK", "Insufficient available stock for issue",
                       {"on_hand": str(lot.on_hand_qty), "reserved": str(lot.reserved_qty),
                        "requested": str(quantity)})
    consumed_reserved = min(lot.reserved_qty, quantity)
    lot.reserved_qty = q_qty(lot.reserved_qty - consumed_reserved)
    lot.on_hand_qty = q_qty(lot.on_hand_qty - quantity)
    _write_movement(ctx, lot, movement_type, -quantity, reference or {}, idempotency_key)
    return lot


def adjust_stock(ctx, *, lot_id: UUID, new_on_hand: Decimal, reason: str,
                 reference: dict | None = None, idempotency_key: str | None = None) -> StockLot:
    """Authorized adjustment — sets physical count; delta recorded in ledger."""
    if new_on_hand < 0:
        raise bad_request("INVALID_QUANTITY", "On-hand cannot be negative")
    if idempotency_key:
        existing_mv = _check_idempotency(ctx, InventoryMovement, idempotency_key)
        if existing_mv:
            return ctx.db.get(StockLot, existing_mv.stock_lot_id)
    lot = get_lot_for_update(ctx.db, ctx.org_id, lot_id)
    if new_on_hand < lot.reserved_qty:
        raise conflict("ADJUSTMENT_BELOW_RESERVED",
                       "Adjustment cannot set on-hand below reserved quantity",
                       {"reserved": str(lot.reserved_qty)})
    delta = q_qty(new_on_hand - lot.on_hand_qty)
    if delta == 0:
        return lot
    lot.on_hand_qty = q_qty(new_on_hand)
    ref = dict(reference or {})
    ref["reason"] = reason
    _write_movement(ctx, lot, "ADJUSTMENT", delta, ref, idempotency_key)
    return lot


def reserve_stock(ctx, *, lot_id: UUID, quantity: Decimal, context: dict,
                  idempotency_key: str | None = None) -> Reservation:
    """Reserve available stock against a sales order / work order. Quality OK lots only."""
    if quantity <= 0:
        raise bad_request("INVALID_QUANTITY", "Reservation quantity must be positive")
    if idempotency_key:
        existing = _check_idempotency(ctx, Reservation, idempotency_key)
        if existing:
            return existing
    lot = get_lot_for_update(ctx.db, ctx.org_id, lot_id)
    if lot.quality_status != "OK":
        raise conflict("LOT_NOT_ELIGIBLE", "Only quality-OK lots can be reserved",
                       {"quality_status": lot.quality_status})
    if lot.on_hand_qty - lot.reserved_qty < quantity:
        raise conflict("INSUFFICIENT_STOCK", "Insufficient available stock to reserve",
                       {"available": str(lot.on_hand_qty - lot.reserved_qty),
                        "requested": str(quantity)})
    lot.reserved_qty = q_qty(lot.reserved_qty + quantity)
    reservation = Reservation(
        organization_id=ctx.org_id, stock_lot_id=lot.id, material_id=lot.material_id,
        warehouse_id=lot.warehouse_id, quantity=q_qty(quantity), status="ACTIVE",
        context=context, idempotency_key=idempotency_key, created_by=ctx.user_id)
    ctx.db.add(reservation)
    ctx.db.flush()
    _write_movement(ctx, lot, "RESERVE", quantity, {"reservation_id": str(reservation.id), **context}, None)
    return reservation


def unreserve_stock(ctx, *, reservation_id: UUID, idempotency_key: str | None = None) -> Reservation:
    reservation = ctx.db.scalar(
        select(Reservation).where(Reservation.id == reservation_id,
                                  Reservation.organization_id == ctx.org_id))
    if reservation is None:
        raise not_found("Reservation")
    if reservation.status != "ACTIVE":
        raise conflict("RESERVATION_NOT_ACTIVE", f"Reservation is {reservation.status}")
    lot = get_lot_for_update(ctx.db, ctx.org_id, reservation.stock_lot_id)
    lot.reserved_qty = q_qty(lot.reserved_qty - reservation.quantity)
    reservation.status = "CANCELLED"
    _write_movement(ctx, lot, "UNRESERVE", -reservation.quantity,
                    {"reservation_id": str(reservation.id)}, idempotency_key)
    return reservation


def material_availability(ctx_id: UUID, db: Session, org_id: UUID, material_id: UUID,
                          warehouse_id: UUID | None = None) -> dict:
    """On-hand / reserved / available per material. Quarantined/rejected excluded from available."""
    q = select(
        func.coalesce(func.sum(StockLot.on_hand_qty), 0),
        func.coalesce(func.sum(StockLot.reserved_qty), 0),
    ).where(StockLot.organization_id == org_id, StockLot.material_id == material_id)
    if warehouse_id:
        q = q.where(StockLot.warehouse_id == warehouse_id)
    on_hand, reserved = db.execute(q).one()
    eligible = db.execute(
        select(func.coalesce(func.sum(StockLot.on_hand_qty - StockLot.reserved_qty), 0)).where(
            StockLot.organization_id == org_id, StockLot.material_id == material_id,
            StockLot.quality_status == "OK",
            *((StockLot.warehouse_id == warehouse_id,) if warehouse_id else ()))
    ).scalar()
    held = db.execute(
        select(func.coalesce(func.sum(StockLot.on_hand_qty - StockLot.reserved_qty), 0)).where(
            StockLot.organization_id == org_id, StockLot.material_id == material_id,
            StockLot.quality_status.in_(["QUARANTINED", "REJECTED"]),
            *((StockLot.warehouse_id == warehouse_id,) if warehouse_id else ()))
    ).scalar()
    return {
        "on_hand": q_qty(Decimal(on_hand)), "reserved": q_qty(Decimal(reserved)),
        "available": max(ZERO, q_qty(Decimal(eligible))), "quality_held": q_qty(Decimal(held)),
    }


def active_reservations_for_lot(ctx, lot_id: UUID) -> list[Reservation]:
    return list(ctx.db.scalars(
        select(Reservation).where(Reservation.stock_lot_id == lot_id,
                                  Reservation.organization_id == ctx.org_id,
                                  Reservation.status == "ACTIVE")))


def latest_price_observation(db: Session, org_id: UUID, form: str, grade: str, region: str | None = None):
    q = select(PriceObservation).where(
        PriceObservation.material_form == form, PriceObservation.grade == grade,
        (PriceObservation.organization_id == org_id) | (PriceObservation.organization_id.is_(None))
    ).order_by(PriceObservation.is_synthetic, PriceObservation.observed_on.desc())
    if region:
        q = q.where(PriceObservation.region == region)
    return db.scalars(q).first()


def handle_integrity_error(exc: IntegrityError):
    detail = str(exc.orig)
    if "ck_lot_on_hand_nonneg" in detail or "ck_lot_reserved" in detail:
        raise conflict("NEGATIVE_STOCK_PREVENTED", "Operation would make stock negative")
    if "uq_" in detail:
        raise conflict("DUPLICATE", "A record with these unique fields already exists")
    raise conflict("CONSTRAINT_VIOLATION", "Database constraint violation")
