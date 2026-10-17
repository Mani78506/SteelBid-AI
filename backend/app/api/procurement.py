from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import or_, select

from app.calc.finance import q_money
from app.calc.suppliers import Offer, rank_offers
from app.core.deps import TenantContext, require
from app.core.errors import conflict, not_found
from app.core.pagination import Page, PageParams, apply_sort, paginate
from app.models.inventory import Warehouse
from app.models.materials import OrganizationMaterial
from app.models.procurement import (GoodsReceipt, PurchaseOrder, PurchaseOrderItem,
                                    PurchaseRequest, PurchaseRequestItem, RFQ, Supplier,
                                    SupplierQuote)
from app.schemas.procurement import (GoodsReceiptIn, GoodsReceiptOut, PRItemOut,
                                     PurchaseOrderIn, PurchaseOrderOut, PurchaseRequestIn,
                                     PurchaseRequestOut, POItemOut, ShortageRequestIn,
                                     SupplierIn, SupplierOut, SupplierQuoteIn,
                                     SupplierQuoteOut, SupplierUpdate)
from app.services import inventory as inv_service
from app.services.audit import record_audit
from app.services.inventory import material_availability
from app.services.numbering import next_number

router = APIRouter(tags=["procurement"])


# ---------------- Suppliers ----------------
def _supplier_out(s: Supplier) -> SupplierOut:
    return SupplierOut.model_validate(s)


@router.get("/suppliers", response_model=Page[SupplierOut])
def list_suppliers(ctx: TenantContext = Depends(require("read")),
                   params: PageParams = Depends(), search: str | None = Query(None),
                   capability: str | None = Query(None), is_active: bool | None = Query(None)):
    stmt = select(Supplier).where(Supplier.organization_id == ctx.org_id)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(Supplier.name.ilike(like), Supplier.code.ilike(like),
                              Supplier.city.ilike(like)))
    if capability:
        stmt = stmt.where(Supplier.material_capabilities.any(capability))
    if is_active is not None:
        stmt = stmt.where(Supplier.is_active.is_(is_active))
    stmt = apply_sort(stmt, params.sort, {"name": Supplier.name, "code": Supplier.code},
                      Supplier.name)
    rows, total = paginate(ctx.db, stmt, params)
    return Page(items=[_supplier_out(s) for s in rows], total=total,
                page=params.page, page_size=params.page_size)


@router.post("/suppliers", response_model=SupplierOut, status_code=201)
def create_supplier(body: SupplierIn, ctx: TenantContext = Depends(require("suppliers:write"))):
    exists = ctx.db.scalar(select(Supplier.id).where(Supplier.organization_id == ctx.org_id,
                                                     Supplier.code == body.code))
    if exists:
        raise conflict("DUPLICATE_CODE", f"Supplier code '{body.code}' already exists")
    s = Supplier(organization_id=ctx.org_id, **body.model_dump())
    ctx.db.add(s)
    ctx.db.flush()
    record_audit(ctx, "supplier.create", "supplier", s.id, {"after": body.model_dump()})
    ctx.db.commit()
    return _supplier_out(s)


def _get_supplier(ctx: TenantContext, supplier_id: UUID) -> Supplier:
    s = ctx.db.scalar(select(Supplier).where(Supplier.id == supplier_id,
                                             Supplier.organization_id == ctx.org_id))
    if s is None:
        raise not_found("Supplier")
    return s


@router.get("/suppliers/{supplier_id}", response_model=SupplierOut)
def get_supplier(supplier_id: UUID, ctx: TenantContext = Depends(require("read"))):
    return _supplier_out(_get_supplier(ctx, supplier_id))


@router.patch("/suppliers/{supplier_id}", response_model=SupplierOut)
def update_supplier(supplier_id: UUID, body: SupplierUpdate,
                    ctx: TenantContext = Depends(require("suppliers:write"))):
    s = _get_supplier(ctx, supplier_id)
    changes = body.model_dump(exclude_unset=True)
    before = {k: getattr(s, k) for k in changes}
    for k, v in changes.items():
        setattr(s, k, v)
    record_audit(ctx, "supplier.update", "supplier", s.id,
                 {"before": before, "after": changes})
    ctx.db.commit()
    return _supplier_out(s)


# ---------------- Purchase requests ----------------
def _pr_out(ctx: TenantContext, pr: PurchaseRequest) -> PurchaseRequestOut:
    items = ctx.db.scalars(select(PurchaseRequestItem).where(
        PurchaseRequestItem.purchase_request_id == pr.id)).all()
    out = PurchaseRequestOut.model_validate(pr)
    item_outs = []
    for it in items:
        io = PRItemOut.model_validate(it)
        m = ctx.db.get(OrganizationMaterial, it.material_id)
        io.material_name = m.name if m else None
        item_outs.append(io)
    out.items = item_outs
    return out


@router.get("/procurement/purchase-requests", response_model=Page[PurchaseRequestOut])
def list_prs(ctx: TenantContext = Depends(require("read")),
             params: PageParams = Depends(), status: str | None = Query(None),
             search: str | None = Query(None)):
    stmt = select(PurchaseRequest).where(PurchaseRequest.organization_id == ctx.org_id)
    if status:
        stmt = stmt.where(PurchaseRequest.status == status)
    if search:
        stmt = stmt.where(PurchaseRequest.number.ilike(f"%{search}%"))
    stmt = stmt.order_by(PurchaseRequest.created_at.desc())
    rows, total = paginate(ctx.db, stmt, params)
    return Page(items=[_pr_out(ctx, pr) for pr in rows], total=total,
                page=params.page, page_size=params.page_size)


@router.post("/procurement/purchase-requests", response_model=PurchaseRequestOut, status_code=201)
def create_pr(body: PurchaseRequestIn,
              idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
              ctx: TenantContext = Depends(require("procurement:write"))):
    if idempotency_key:
        existing = ctx.db.scalar(select(PurchaseRequest).where(
            PurchaseRequest.organization_id == ctx.org_id,
            PurchaseRequest.idempotency_key == idempotency_key))
        if existing:
            return _pr_out(ctx, existing)
    pr = PurchaseRequest(
        organization_id=ctx.org_id,
        number=next_number(ctx.db, PurchaseRequest, ctx.org_id, prefix="PR"),
        status="DRAFT", source_type=body.source_type, context=body.context,
        needed_by=body.needed_by, notes=body.notes, idempotency_key=idempotency_key,
        created_by=ctx.user_id)
    ctx.db.add(pr)
    ctx.db.flush()
    for item in body.items:
        mat = ctx.db.get(OrganizationMaterial, item.material_id)
        if mat is None or mat.organization_id != ctx.org_id:
            raise not_found("Material")
        ctx.db.add(PurchaseRequestItem(organization_id=ctx.org_id,
                                       purchase_request_id=pr.id, **item.model_dump()))
    record_audit(ctx, "purchase_request.create", "purchase_request", pr.id,
                 {"after": {"number": pr.number, "items": len(body.items)}})
    ctx.db.commit()
    return _pr_out(ctx, pr)


@router.get("/procurement/purchase-requests/{pr_id}", response_model=PurchaseRequestOut)
def get_pr(pr_id: UUID, ctx: TenantContext = Depends(require("read"))):
    pr = ctx.db.scalar(select(PurchaseRequest).where(
        PurchaseRequest.id == pr_id, PurchaseRequest.organization_id == ctx.org_id))
    if pr is None:
        raise not_found("Purchase request")
    return _pr_out(ctx, pr)


@router.post("/procurement/shortage-request", response_model=PurchaseRequestOut, status_code=201)
def shortage_request(body: ShortageRequestIn,
                     idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                     ctx: TenantContext = Depends(require("procurement:write"))):
    """Compute live shortage for a material and raise a PR for the shortfall."""
    mat = ctx.db.get(OrganizationMaterial, body.material_id)
    if mat is None or mat.organization_id != ctx.org_id:
        raise not_found("Material")
    av = material_availability(None, ctx.db, ctx.org_id, body.material_id)
    from app.calc.finance import shortage_qty
    shortage = shortage_qty(body.quantity, av["available"])
    if shortage <= 0:
        raise conflict("NO_SHORTAGE", "Eligible stock already covers the requirement",
                       {"available": str(av["available"]), "required": str(body.quantity)})
    pr_in = PurchaseRequestIn(
        source_type="SHORTAGE",
        context={**body.context, "gross_requirement": str(body.quantity),
                 "eligible_available": str(av["available"]), "shortage": str(shortage)},
        needed_by=body.needed_by,
        items=[{"material_id": str(body.material_id), "quantity": str(shortage), "unit": "MT"}])
    return create_pr(pr_in, idempotency_key, ctx)


# ---------------- RFQs & supplier quotes ----------------
@router.post("/procurement/rfqs", status_code=201)
def create_rfq(pr_id: UUID, valid_until: date | None = None,
               ctx: TenantContext = Depends(require("procurement:write"))):
    pr = ctx.db.scalar(select(PurchaseRequest).where(
        PurchaseRequest.id == pr_id, PurchaseRequest.organization_id == ctx.org_id))
    if pr is None:
        raise not_found("Purchase request")
    rfq = RFQ(organization_id=ctx.org_id, purchase_request_id=pr.id,
              number=next_number(ctx.db, RFQ, ctx.org_id, prefix="RFQ"),
              status="ISSUED", valid_until=valid_until)
    ctx.db.add(rfq)
    pr.status = "RFQ_ISSUED"
    ctx.db.flush()
    record_audit(ctx, "rfq.create", "rfq", rfq.id, {"after": {"number": rfq.number}})
    ctx.db.commit()
    return {"id": str(rfq.id), "number": rfq.number, "status": rfq.status}


def _quote_out(ctx: TenantContext, q: SupplierQuote) -> SupplierQuoteOut:
    from app.calc.finance import landed_unit_cost
    s = ctx.db.get(Supplier, q.supplier_id)
    out = SupplierQuoteOut.model_validate(q)
    out.supplier_name = s.name if s else None
    out.landed_cost = landed_unit_cost(q.unit_price, q.fx_rate_to_org_ccy, q.freight_per_unit,
                                       q.duty_pct, q.tax_pct, q.tax_recoverable)
    return out


@router.get("/procurement/supplier-quotes", response_model=list[SupplierQuoteOut])
def list_quotes(ctx: TenantContext = Depends(require("read")),
                material_id: UUID | None = Query(None), rfq_id: UUID | None = Query(None)):
    stmt = select(SupplierQuote).where(SupplierQuote.organization_id == ctx.org_id)
    if material_id:
        stmt = stmt.where(SupplierQuote.material_id == material_id)
    if rfq_id:
        stmt = stmt.where(SupplierQuote.rfq_id == rfq_id)
    rows = ctx.db.scalars(stmt.order_by(SupplierQuote.created_at.desc())).all()
    return [_quote_out(ctx, q) for q in rows]


@router.post("/procurement/supplier-quotes", response_model=SupplierQuoteOut, status_code=201)
def add_quote(body: SupplierQuoteIn, ctx: TenantContext = Depends(require("procurement:write"))):
    _get_supplier(ctx, body.supplier_id)
    mat = ctx.db.get(OrganizationMaterial, body.material_id)
    if mat is None or mat.organization_id != ctx.org_id:
        raise not_found("Material")
    q = SupplierQuote(organization_id=ctx.org_id, **body.model_dump())
    ctx.db.add(q)
    ctx.db.flush()
    record_audit(ctx, "supplier_quote.create", "supplier_quote", q.id,
                 {"after": {"supplier_id": str(body.supplier_id),
                            "unit_price": str(body.unit_price)}})
    ctx.db.commit()
    return _quote_out(ctx, q)


@router.get("/procurement/compare")
def compare_quotes(material_id: UUID, max_lead_time_days: int | None = None,
                   ctx: TenantContext = Depends(require("read"))):
    """Landed-cost comparison of OPEN supplier quotes for a compatible material spec.
    Offers from expired validity are excluded; unit/currency normalized at entry."""
    quotes = ctx.db.scalars(select(SupplierQuote).where(
        SupplierQuote.organization_id == ctx.org_id, SupplierQuote.material_id == material_id,
        SupplierQuote.status == "OPEN")).all()
    offers = []
    for q in quotes:
        if q.valid_until and q.valid_until < date.today():
            continue  # expired offer not comparable
        s = ctx.db.get(Supplier, q.supplier_id)
        offers.append(Offer(
            supplier_id=str(q.supplier_id), supplier_name=s.name if s else "?",
            unit_price=q.unit_price, fx_rate=q.fx_rate_to_org_ccy,
            freight_per_unit=q.freight_per_unit, duty_pct=q.duty_pct, tax_pct=q.tax_pct,
            tax_recoverable=q.tax_recoverable, lead_time_days=q.lead_time_days,
            payment_terms_days=q.payment_terms_days, valid=True))
    ranked = rank_offers(offers, max_lead_time_days)
    for r in ranked:
        r["landed_cost"] = str(r["landed_cost"])
        r["unit_price"] = str(r["unit_price"])
        r["premium_vs_best"] = str(r["premium_vs_best"])
    return {"material_id": str(material_id), "currency": ctx.organization.currency_code,
            "items": ranked}


# ---------------- Purchase orders ----------------
def _po_out(ctx: TenantContext, po: PurchaseOrder) -> PurchaseOrderOut:
    s = ctx.db.get(Supplier, po.supplier_id)
    items = ctx.db.scalars(select(PurchaseOrderItem).where(
        PurchaseOrderItem.purchase_order_id == po.id)).all()
    out = PurchaseOrderOut.model_validate(po)
    out.supplier_name = s.name if s else None
    item_outs = []
    for it in items:
        io = POItemOut.model_validate(it)
        m = ctx.db.get(OrganizationMaterial, it.material_id)
        io.material_name = m.name if m else None
        item_outs.append(io)
    out.items = item_outs
    return out


@router.get("/procurement/purchase-orders", response_model=Page[PurchaseOrderOut])
def list_pos(ctx: TenantContext = Depends(require("read")),
             params: PageParams = Depends(), status: str | None = Query(None),
             search: str | None = Query(None)):
    stmt = select(PurchaseOrder).where(PurchaseOrder.organization_id == ctx.org_id)
    if status:
        stmt = stmt.where(PurchaseOrder.status == status)
    if search:
        stmt = stmt.where(PurchaseOrder.number.ilike(f"%{search}%"))
    stmt = apply_sort(stmt, params.sort, {"created_at": PurchaseOrder.created_at,
                                          "number": PurchaseOrder.number},
                      PurchaseOrder.created_at.desc())
    rows, total = paginate(ctx.db, stmt, params)
    return Page(items=[_po_out(ctx, po) for po in rows], total=total,
                page=params.page, page_size=params.page_size)


@router.post("/procurement/purchase-orders", response_model=PurchaseOrderOut, status_code=201)
def create_po(body: PurchaseOrderIn,
              idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
              ctx: TenantContext = Depends(require("procurement:write"))):
    if idempotency_key:
        existing = ctx.db.scalar(select(PurchaseOrder).where(
            PurchaseOrder.organization_id == ctx.org_id,
            PurchaseOrder.idempotency_key == idempotency_key))
        if existing:
            return _po_out(ctx, existing)
    _get_supplier(ctx, body.supplier_id)
    total = Decimal("0")
    for it in body.items:
        mat = ctx.db.get(OrganizationMaterial, it.material_id)
        if mat is None or mat.organization_id != ctx.org_id:
            raise not_found("Material")
        total += it.quantity * it.unit_price
    po = PurchaseOrder(
        organization_id=ctx.org_id, supplier_id=body.supplier_id,
        purchase_request_id=body.purchase_request_id,
        number=next_number(ctx.db, PurchaseOrder, ctx.org_id, prefix="PO"),
        status="DRAFT", total_value=q_money(total), expected_delivery=body.expected_delivery,
        idempotency_key=idempotency_key, created_by=ctx.user_id)
    ctx.db.add(po)
    ctx.db.flush()
    for it in body.items:
        ctx.db.add(PurchaseOrderItem(organization_id=ctx.org_id, purchase_order_id=po.id,
                                     **it.model_dump()))
    if body.purchase_request_id:
        pr = ctx.db.get(PurchaseRequest, body.purchase_request_id)
        if pr and pr.organization_id == ctx.org_id and pr.status in ("DRAFT", "RFQ_ISSUED"):
            pr.status = "ORDERED"
    record_audit(ctx, "purchase_order.create", "purchase_order", po.id,
                 {"after": {"number": po.number, "total_value": po.total_value}})
    ctx.db.commit()
    return _po_out(ctx, po)


@router.post("/procurement/purchase-orders/{po_id}/approve", response_model=PurchaseOrderOut)
def approve_po(po_id: UUID, ctx: TenantContext = Depends(require("procurement:approve"))):
    po = ctx.db.scalar(select(PurchaseOrder).where(PurchaseOrder.id == po_id,
                                                   PurchaseOrder.organization_id == ctx.org_id))
    if po is None:
        raise not_found("Purchase order")
    if po.status != "DRAFT":
        raise conflict("INVALID_TRANSITION", f"PO is {po.status}, cannot approve")
    po.status = "APPROVED"
    po.approved_by = ctx.user_id
    po.approved_at = datetime.now(timezone.utc)
    record_audit(ctx, "purchase_order.approve", "purchase_order", po.id, {})
    ctx.db.commit()
    return _po_out(ctx, po)


@router.get("/procurement/purchase-orders/{po_id}", response_model=PurchaseOrderOut)
def get_po(po_id: UUID, ctx: TenantContext = Depends(require("read"))):
    po = ctx.db.scalar(select(PurchaseOrder).where(PurchaseOrder.id == po_id,
                                                   PurchaseOrder.organization_id == ctx.org_id))
    if po is None:
        raise not_found("Purchase order")
    return _po_out(ctx, po)


# ---------------- Goods receipts ----------------
@router.post("/procurement/goods-receipts", response_model=GoodsReceiptOut, status_code=201)
def create_grn(body: GoodsReceiptIn,
               idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
               ctx: TenantContext = Depends(require("inventory:transact"))):
    if idempotency_key:
        existing = ctx.db.scalar(select(GoodsReceipt).where(
            GoodsReceipt.organization_id == ctx.org_id,
            GoodsReceipt.idempotency_key == idempotency_key))
        if existing:
            return GoodsReceiptOut.model_validate(existing)
    po = ctx.db.scalar(select(PurchaseOrder).where(
        PurchaseOrder.id == body.purchase_order_id,
        PurchaseOrder.organization_id == ctx.org_id))
    if po is None:
        raise not_found("Purchase order")
    if po.status not in ("APPROVED", "SENT", "PARTIALLY_RECEIVED"):
        raise conflict("INVALID_TRANSITION", f"PO is {po.status}; approve before receiving")
    wh = ctx.db.get(Warehouse, body.warehouse_id)
    if wh is None or wh.organization_id != ctx.org_id:
        raise not_found("Warehouse")
    grn = GoodsReceipt(
        organization_id=ctx.org_id, purchase_order_id=po.id, warehouse_id=body.warehouse_id,
        number=next_number(ctx.db, GoodsReceipt, ctx.org_id, prefix="GRN"),
        idempotency_key=idempotency_key, created_by=ctx.user_id)
    ctx.db.add(grn)
    ctx.db.flush()
    prefix = body.lot_number_prefix or grn.number
    items = ctx.db.scalars(select(PurchaseOrderItem).where(
        PurchaseOrderItem.purchase_order_id == po.id)).all()
    all_received = True
    for idx, item in enumerate(items, start=1):
        remaining = item.quantity - item.received_qty
        if remaining <= 0:
            continue
        inv_service.receive_stock(
            ctx, material_id=item.material_id, warehouse_id=body.warehouse_id,
            lot_number=f"{prefix}-L{idx}", quantity=remaining, unit=item.unit,
            unit_cost=item.unit_price,
            reference={"goods_receipt_id": str(grn.id), "po_id": str(po.id)})
        item.received_qty = item.quantity
        if item.received_qty < item.quantity:
            all_received = False
    po.status = "RECEIVED" if all_received else "PARTIALLY_RECEIVED"
    if po.purchase_request_id:
        pr = ctx.db.get(PurchaseRequest, po.purchase_request_id)
        if pr and pr.organization_id == ctx.org_id:
            pr.status = "FULFILLED"
    record_audit(ctx, "goods_receipt.post", "goods_receipt", grn.id,
                 {"after": {"number": grn.number, "po": po.number}})
    ctx.db.commit()
    return GoodsReceiptOut.model_validate(grn)
