from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.calc.finance import ZERO, q_money, q_qty, weighted_average_cost
from app.core.deps import TenantContext, require
from app.core.errors import conflict, not_found
from app.core.pagination import Page, PageParams, paginate
from app.models.fabrication import (BOMItem, BOMVersion, MaterialAllocation,
                                    ProductionOperation, QualityInspection, Routing,
                                    ScrapRecord, WorkOrder)
from app.models.inventory import StockLot
from app.models.materials import OrganizationMaterial
from app.schemas.fabrication import (AllocateIn, AllocateOut, BOMCreateIn, BOMItemOut,
                                     BOMOut, InspectionIn, InspectionOut, OperationOut,
                                     OperationUpdateIn, RoutingOut, ScrapIn, WorkOrderIn,
                                     WorkOrderOut)
from app.services import inventory as inv_service
from app.services.audit import record_audit
from app.services.numbering import next_number

router = APIRouter(prefix="/fabrication", tags=["fabrication"])

WO_FLOW = {
    "PLANNED": {"MATERIAL_ALLOCATED", "CANCELLED"},
    "MATERIAL_ALLOCATED": {"IN_PROGRESS", "CANCELLED"},
    "IN_PROGRESS": {"QC"},
    "QC": {"COMPLETED", "IN_PROGRESS"},
    "COMPLETED": set(), "CANCELLED": set(),
}


def _bom_out(ctx: TenantContext, bom: BOMVersion) -> BOMOut:
    items = ctx.db.scalars(select(BOMItem).where(BOMItem.bom_version_id == bom.id)).all()
    routings = ctx.db.scalars(select(Routing).where(Routing.bom_version_id == bom.id)
                              .order_by(Routing.sequence)).all()
    item_outs = []
    for it in items:
        io = BOMItemOut.model_validate(it)
        m = ctx.db.get(OrganizationMaterial, it.material_id)
        io.material_name = m.name if m else None
        io.estimated_cost = None
        item_outs.append(io)
    out = BOMOut.model_validate(bom)
    out.items = item_outs
    out.routings = [RoutingOut.model_validate(r) for r in routings]
    return out


def _wac(ctx: TenantContext, material_id) -> Decimal:
    rows = ctx.db.execute(
        select(StockLot.on_hand_qty, StockLot.unit_cost).where(
            StockLot.organization_id == ctx.org_id, StockLot.material_id == material_id,
            StockLot.on_hand_qty > 0, StockLot.unit_cost.isnot(None))).all()
    return weighted_average_cost([(Decimal(str(q)), Decimal(str(c))) for q, c in rows])


@router.get("/boms", response_model=Page[BOMOut])
def list_boms(ctx: TenantContext = Depends(require("read")),
              params: PageParams = Depends(), status: str | None = Query(None),
              search: str | None = Query(None)):
    stmt = select(BOMVersion).where(BOMVersion.organization_id == ctx.org_id)
    if status:
        stmt = stmt.where(BOMVersion.status == status)
    if search:
        like = f"%{search}%"
        stmt = stmt.where((BOMVersion.bom_code.ilike(like)) | (BOMVersion.product_name.ilike(like)))
    stmt = stmt.order_by(BOMVersion.created_at.desc())
    rows, total = paginate(ctx.db, stmt, params)
    return Page(items=[_bom_out(ctx, b) for b in rows], total=total,
                page=params.page, page_size=params.page_size)


@router.post("/boms", response_model=BOMOut, status_code=201)
def create_bom(body: BOMCreateIn, ctx: TenantContext = Depends(require("fabrication:write"))):
    version_no = (ctx.db.scalar(
        select(BOMVersion.version_no).where(BOMVersion.organization_id == ctx.org_id,
                                            BOMVersion.bom_code == body.bom_code)
        .order_by(BOMVersion.version_no.desc()).limit(1)) or 0) + 1
    bom = BOMVersion(organization_id=ctx.org_id, bom_code=body.bom_code,
                     product_name=body.product_name, version_no=version_no, status="DRAFT")
    ctx.db.add(bom)
    ctx.db.flush()
    material_cost = ZERO
    for item in body.items:
        mat = ctx.db.get(OrganizationMaterial, item.material_id)
        if mat is None or mat.organization_id != ctx.org_id:
            raise not_found("Material")
        wac = _wac(ctx, item.material_id)
        gross_qty = q_qty(item.quantity * (Decimal("1") + item.theoretical_waste_pct))
        material_cost += gross_qty * wac
        ctx.db.add(BOMItem(organization_id=ctx.org_id, bom_version_id=bom.id,
                           **item.model_dump()))
    routing_cost = ZERO
    for rt in body.routings:
        if rt.operation_type not in ("CUTTING", "WELDING", "DRILLING", "MACHINING",
                                     "PAINTING", "COATING", "ASSEMBLY", "INSPECTION"):
            from app.core.errors import bad_request
            raise bad_request("INVALID_OPERATION", f"Unknown operation type {rt.operation_type}")
        routing_cost += rt.est_hours * rt.rate_per_hour
        ctx.db.add(Routing(organization_id=ctx.org_id, bom_version_id=bom.id, **rt.model_dump()))
    bom.estimated_material_cost = q_money(material_cost)
    bom.estimated_total_cost = q_money(material_cost + routing_cost)
    record_audit(ctx, "bom.create", "bom_version", bom.id,
                 {"after": {"bom_code": bom.bom_code, "version_no": version_no,
                            "estimated_total_cost": bom.estimated_total_cost}})
    ctx.db.commit()
    return _bom_out(ctx, bom)


@router.get("/boms/{bom_id}", response_model=BOMOut)
def get_bom(bom_id: UUID, ctx: TenantContext = Depends(require("read"))):
    bom = ctx.db.scalar(select(BOMVersion).where(BOMVersion.id == bom_id,
                                                 BOMVersion.organization_id == ctx.org_id))
    if bom is None:
        raise not_found("BOM")
    return _bom_out(ctx, bom)


@router.post("/boms/{bom_id}/approve", response_model=BOMOut)
def approve_bom(bom_id: UUID, ctx: TenantContext = Depends(require("fabrication:write"))):
    bom = ctx.db.scalar(select(BOMVersion).where(BOMVersion.id == bom_id,
                                                 BOMVersion.organization_id == ctx.org_id))
    if bom is None:
        raise not_found("BOM")
    if bom.status != "DRAFT":
        raise conflict("INVALID_TRANSITION", f"BOM is {bom.status}")
    bom.status = "APPROVED"
    bom.approved_by = ctx.user_id
    bom.approved_at = datetime.now(timezone.utc)
    record_audit(ctx, "bom.approve", "bom_version", bom.id, {})
    ctx.db.commit()
    return _bom_out(ctx, bom)


# ---------------- Work orders ----------------
def _wo_out(ctx: TenantContext, wo: WorkOrder) -> WorkOrderOut:
    ops = ctx.db.scalars(select(ProductionOperation).where(
        ProductionOperation.work_order_id == wo.id).order_by(ProductionOperation.sequence)).all()
    out = WorkOrderOut.model_validate(wo)
    out.operations = [OperationOut.model_validate(o) for o in ops]
    return out


def _get_wo(ctx: TenantContext, wo_id: UUID) -> WorkOrder:
    wo = ctx.db.scalar(select(WorkOrder).where(WorkOrder.id == wo_id,
                                               WorkOrder.organization_id == ctx.org_id))
    if wo is None:
        raise not_found("Work order")
    return wo


@router.get("/work-orders", response_model=Page[WorkOrderOut])
def list_work_orders(ctx: TenantContext = Depends(require("read")),
                     params: PageParams = Depends(), status: str | None = Query(None)):
    stmt = select(WorkOrder).where(WorkOrder.organization_id == ctx.org_id)
    if status:
        stmt = stmt.where(WorkOrder.status == status)
    stmt = stmt.order_by(WorkOrder.created_at.desc())
    rows, total = paginate(ctx.db, stmt, params)
    return Page(items=[_wo_out(ctx, w) for w in rows], total=total,
                page=params.page, page_size=params.page_size)


@router.post("/work-orders", response_model=WorkOrderOut, status_code=201)
def create_work_order(body: WorkOrderIn,
                      ctx: TenantContext = Depends(require("fabrication:write"))):
    routings = []
    if body.bom_version_id:
        bom = ctx.db.get(BOMVersion, body.bom_version_id)
        if bom is None or bom.organization_id != ctx.org_id:
            raise not_found("BOM")
        if bom.status != "APPROVED":
            raise conflict("BOM_NOT_APPROVED", "Only APPROVED BOM revisions can drive work orders")
        routings = ctx.db.scalars(select(Routing).where(Routing.bom_version_id == bom.id)
                                  .order_by(Routing.sequence)).all()
    wo = WorkOrder(
        organization_id=ctx.org_id, bom_version_id=body.bom_version_id,
        sales_order_id=body.sales_order_id,
        number=next_number(ctx.db, WorkOrder, ctx.org_id, prefix="WO"),
        status="PLANNED", planned_qty=body.planned_qty, due_date=body.due_date,
        start_date=date.today())
    ctx.db.add(wo)
    ctx.db.flush()
    for rt in routings:
        ctx.db.add(ProductionOperation(
            organization_id=ctx.org_id, work_order_id=wo.id, routing_id=rt.id,
            sequence=rt.sequence, operation_type=rt.operation_type, status="PENDING"))
    record_audit(ctx, "work_order.create", "work_order", wo.id,
                 {"after": {"number": wo.number, "planned_qty": body.planned_qty}})
    ctx.db.commit()
    return _wo_out(ctx, wo)


@router.get("/work-orders/{wo_id}", response_model=WorkOrderOut)
def get_work_order(wo_id: UUID, ctx: TenantContext = Depends(require("read"))):
    return _wo_out(ctx, _get_wo(ctx, wo_id))


@router.post("/work-orders/{wo_id}/allocate", response_model=AllocateOut, status_code=201)
def allocate_material(wo_id: UUID, body: AllocateIn,
                      ctx: TenantContext = Depends(require("fabrication:write"))):
    """Allocate stock to a work order — reserves inventory against the WO context."""
    wo = _get_wo(ctx, wo_id)
    if wo.status in ("CANCELLED", "COMPLETED"):
        raise conflict("ORDER_CLOSED", f"Cannot allocate to a {wo.status} work order")
    mat = ctx.db.get(OrganizationMaterial, body.material_id)
    if mat is None or mat.organization_id != ctx.org_id:
        raise not_found("Material")
    reservation = inv_service.reserve_stock(
        ctx, lot_id=body.lot_id, quantity=body.quantity,
        context={"work_order_id": str(wo.id)})
    alloc = MaterialAllocation(
        organization_id=ctx.org_id, work_order_id=wo.id, stock_lot_id=body.lot_id,
        material_id=body.material_id, allocated_qty=body.quantity, status="ALLOCATED")
    ctx.db.add(alloc)
    if wo.status == "PLANNED":
        wo.status = "MATERIAL_ALLOCATED"
    ctx.db.flush()
    record_audit(ctx, "work_order.allocate", "material_allocation", alloc.id,
                 {"after": {"wo": wo.number, "qty": body.quantity,
                            "reservation_id": str(reservation.id)}})
    ctx.db.commit()
    return AllocateOut.model_validate(alloc)


@router.post("/work-orders/{wo_id}/consume/{allocation_id}", response_model=AllocateOut)
def consume_material(wo_id: UUID, allocation_id: UUID,
                     ctx: TenantContext = Depends(require("fabrication:write"))):
    """Consume allocated material — issues from the lot and tracks actual cost."""
    wo = _get_wo(ctx, wo_id)
    alloc = ctx.db.scalar(select(MaterialAllocation).where(
        MaterialAllocation.id == allocation_id, MaterialAllocation.work_order_id == wo.id,
        MaterialAllocation.organization_id == ctx.org_id))
    if alloc is None:
        raise not_found("Allocation")
    if alloc.status != "ALLOCATED":
        raise conflict("ALREADY_CONSUMED", f"Allocation is {alloc.status}")
    lot = inv_service.issue_stock(ctx, lot_id=alloc.stock_lot_id, quantity=alloc.allocated_qty,
                                  movement_type="CONSUME",
                                  reference={"work_order_id": str(wo.id)})
    alloc.consumed_qty = alloc.allocated_qty
    alloc.status = "CONSUMED"
    if lot.unit_cost is not None:
        wo.actual_material_cost = q_money(
            wo.actual_material_cost + alloc.allocated_qty * lot.unit_cost)
    if wo.status == "MATERIAL_ALLOCATED":
        wo.status = "IN_PROGRESS"
    record_audit(ctx, "work_order.consume", "material_allocation", alloc.id,
                 {"after": {"qty": alloc.allocated_qty}})
    ctx.db.commit()
    return AllocateOut.model_validate(alloc)


@router.patch("/work-orders/{wo_id}/operations/{op_id}", response_model=OperationOut)
def update_operation(wo_id: UUID, op_id: UUID, body: OperationUpdateIn,
                     ctx: TenantContext = Depends(require("fabrication:write"))):
    wo = _get_wo(ctx, wo_id)
    op = ctx.db.scalar(select(ProductionOperation).where(
        ProductionOperation.id == op_id, ProductionOperation.work_order_id == wo.id))
    if op is None:
        raise not_found("Operation")
    op.status = body.status
    if body.status == "IN_PROGRESS" and op.started_at is None:
        op.started_at = datetime.now(timezone.utc)
    if body.status == "COMPLETED":
        op.completed_at = datetime.now(timezone.utc)
    if body.actual_hours is not None:
        op.actual_hours = body.actual_hours
        if op.routing_id:
            rt = ctx.db.get(Routing, op.routing_id)
            if rt:
                wo.actual_labour_cost = q_money(
                    wo.actual_labour_cost + body.actual_hours * rt.rate_per_hour)
    if body.operator is not None:
        op.operator = body.operator
    record_audit(ctx, "work_order.operation", "production_operation", op.id,
                 {"after": body.model_dump(exclude_unset=True)})
    ctx.db.commit()
    return OperationOut.model_validate(op)


@router.post("/work-orders/{wo_id}/transition", response_model=WorkOrderOut)
def transition_wo(wo_id: UUID, target: str,
                  ctx: TenantContext = Depends(require("fabrication:write"))):
    wo = _get_wo(ctx, wo_id)
    allowed = WO_FLOW.get(wo.status, set())
    if target not in allowed:
        raise conflict("INVALID_TRANSITION",
                       f"Cannot move work order from {wo.status} to {target}",
                       {"allowed": sorted(allowed)})
    before = wo.status
    wo.status = target
    if target == "COMPLETED":
        wo.produced_qty = wo.planned_qty
    record_audit(ctx, "work_order.transition", "work_order", wo.id,
                 {"before": {"status": before}, "after": {"status": target}})
    ctx.db.commit()
    return _wo_out(ctx, wo)


@router.post("/work-orders/{wo_id}/inspections", response_model=InspectionOut, status_code=201)
def add_inspection(wo_id: UUID, body: InspectionIn,
                   ctx: TenantContext = Depends(require("fabrication:write"))):
    wo = _get_wo(ctx, wo_id)
    insp = QualityInspection(organization_id=ctx.org_id, work_order_id=wo.id,
                             **body.model_dump())
    ctx.db.add(insp)
    ctx.db.flush()
    record_audit(ctx, "work_order.inspect", "quality_inspection", insp.id,
                 {"after": {"result": body.result, "type": body.inspection_type}})
    ctx.db.commit()
    return InspectionOut.model_validate(insp)


@router.get("/work-orders/{wo_id}/inspections", response_model=list[InspectionOut])
def list_inspections(wo_id: UUID, ctx: TenantContext = Depends(require("read"))):
    wo = _get_wo(ctx, wo_id)
    rows = ctx.db.scalars(select(QualityInspection).where(
        QualityInspection.work_order_id == wo.id)
        .order_by(QualityInspection.inspected_at.desc())).all()
    return [InspectionOut.model_validate(r) for r in rows]


@router.post("/work-orders/{wo_id}/scrap", status_code=201)
def add_scrap(wo_id: UUID, body: ScrapIn,
              ctx: TenantContext = Depends(require("fabrication:write"))):
    wo = _get_wo(ctx, wo_id)
    if body.material_id:
        mat = ctx.db.get(OrganizationMaterial, body.material_id)
        if mat is None or mat.organization_id != ctx.org_id:
            raise not_found("Material")
    rec = ScrapRecord(organization_id=ctx.org_id, work_order_id=wo.id,
                      recorded_by=ctx.user_id, **body.model_dump())
    ctx.db.add(rec)
    ctx.db.flush()
    record_audit(ctx, "work_order.scrap", "scrap_record", rec.id,
                 {"after": {"qty": body.quantity, "unit": body.unit}})
    ctx.db.commit()
    return {"id": str(rec.id), "quantity": str(rec.quantity), "unit": rec.unit}
