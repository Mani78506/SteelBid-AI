from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.calc.finance import ZERO, cost_estimate_total, q_money
from app.core.deps import TenantContext, require
from app.core.errors import conflict, not_found
from app.core.pagination import Page, PageParams, paginate
from app.models.ops import Approval, CostEstimate, CostLine, Invoice, Payment
from app.models.sales import SalesOrder
from app.models.inventory import StockLot
from app.models.projects import Tender
from app.calc.finance import inventory_valuation
from app.schemas.ops import (CostEstimateIn, CostEstimateOut, CostLineOut, InvoiceIn,
                             InvoiceOut, PaymentIn)
from app.services.audit import record_audit
from app.services.numbering import next_number

router = APIRouter(prefix="/finance", tags=["finance"])


# ---------------- Cost estimates ----------------
def _ce_out(ctx: TenantContext, ce: CostEstimate) -> CostEstimateOut:
    lines = ctx.db.scalars(select(CostLine).where(CostLine.cost_estimate_id == ce.id)).all()
    out = CostEstimateOut.model_validate(ce)
    out.lines = [CostLineOut.model_validate(l) for l in lines]
    return out


@router.get("/cost-estimates", response_model=Page[CostEstimateOut])
def list_estimates(ctx: TenantContext = Depends(require("read")),
                   params: PageParams = Depends(), status: str | None = Query(None)):
    stmt = select(CostEstimate).where(CostEstimate.organization_id == ctx.org_id)
    if status:
        stmt = stmt.where(CostEstimate.status == status)
    stmt = stmt.order_by(CostEstimate.created_at.desc())
    rows, total = paginate(ctx.db, stmt, params)
    return Page(items=[_ce_out(ctx, c) for c in rows], total=total,
                page=params.page, page_size=params.page_size)


@router.post("/cost-estimates", response_model=CostEstimateOut, status_code=201)
def create_estimate(body: CostEstimateIn, ctx: TenantContext = Depends(require("quotations:write"))):
    buckets = {"MATERIAL": ZERO, "FABRICATION": ZERO, "LABOUR": ZERO, "FREIGHT": ZERO,
               "INSTALLATION": ZERO, "SUBCONTRACTING": ZERO}
    if body.tender_id and not ctx.db.scalar(select(Tender.id).where(
        Tender.id == body.tender_id, Tender.organization_id == ctx.org_id)):
        raise not_found("Tender")
    ce = CostEstimate(organization_id=ctx.org_id, tender_id=body.tender_id, context=body.context,
                      overhead_cost=body.overhead_cost, contingency_pct=body.contingency_pct,
                      currency=ctx.organization.currency_code, created_by=ctx.user_id)
    ctx.db.add(ce)
    ctx.db.flush()
    for line in body.lines:
        cat = line.category.upper()
        if cat not in buckets:
            from app.core.errors import bad_request
            raise bad_request("INVALID_CATEGORY",
                              f"category must be one of {sorted(buckets)}")
        amount = line.amount
        if amount is None:
            if line.quantity is None or line.unit_cost is None:
                from app.core.errors import bad_request
                raise bad_request("MISSING_AMOUNT", "Provide amount or quantity+unit_cost")
            amount = q_money(line.quantity * line.unit_cost)
        buckets[cat] += amount
        ctx.db.add(CostLine(organization_id=ctx.org_id, cost_estimate_id=ce.id,
                            category=cat, description=line.description,
                            material_id=line.material_id, quantity=line.quantity,
                            unit=line.unit, unit_cost=line.unit_cost, amount=amount,
                            source=line.source))
    subtotal, total = cost_estimate_total(
        material=buckets["MATERIAL"], fabrication=buckets["FABRICATION"],
        labour=buckets["LABOUR"], freight=buckets["FREIGHT"],
        installation=buckets["INSTALLATION"], subcontracting=buckets["SUBCONTRACTING"],
        overhead=body.overhead_cost, contingency_pct=body.contingency_pct)
    ce.material_cost = q_money(buckets["MATERIAL"])
    ce.fabrication_cost = q_money(buckets["FABRICATION"])
    ce.labour_cost = q_money(buckets["LABOUR"])
    ce.freight_cost = q_money(buckets["FREIGHT"])
    ce.installation_cost = q_money(buckets["INSTALLATION"])
    ce.subcontracting_cost = q_money(buckets["SUBCONTRACTING"])
    ce.contingency_amount = q_money(total - subtotal)
    ce.total_cost = total
    record_audit(ctx, "cost_estimate.create", "cost_estimate", ce.id,
                 {"after": {"total_cost": total}})
    ctx.db.commit()
    return _ce_out(ctx, ce)


@router.get("/cost-estimates/{estimate_id}", response_model=CostEstimateOut)
def get_estimate(estimate_id: UUID, ctx: TenantContext = Depends(require("read"))):
    ce = ctx.db.scalar(select(CostEstimate).where(CostEstimate.id == estimate_id,
                                                  CostEstimate.organization_id == ctx.org_id))
    if ce is None:
        raise not_found("Cost estimate")
    return _ce_out(ctx, ce)


@router.post("/cost-estimates/{estimate_id}/approve", response_model=CostEstimateOut)
def approve_estimate(estimate_id: UUID,
                     ctx: TenantContext = Depends(require("quotations:approve"))):
    ce = ctx.db.scalar(select(CostEstimate).where(CostEstimate.id == estimate_id,
                                                  CostEstimate.organization_id == ctx.org_id))
    if ce is None:
        raise not_found("Cost estimate")
    if ce.status == "APPROVED":
        raise conflict("ALREADY_APPROVED", "Estimate already approved")
    ce.status = "APPROVED"
    record_audit(ctx, "cost_estimate.approve", "cost_estimate", ce.id, {})
    ctx.db.commit()
    return _ce_out(ctx, ce)


# ---------------- Invoices & payments ----------------
def _inv_out(ctx: TenantContext, inv: Invoice) -> InvoiceOut:
    paid = ctx.db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(
        Payment.invoice_id == inv.id)) or Decimal("0")
    out = InvoiceOut.model_validate(inv)
    out.paid_amount = q_money(Decimal(str(paid)))
    return out


@router.get("/invoices", response_model=Page[InvoiceOut])
def list_invoices(ctx: TenantContext = Depends(require("read")),
                  params: PageParams = Depends(), invoice_type: str | None = Query(None),
                  status: str | None = Query(None)):
    stmt = select(Invoice).where(Invoice.organization_id == ctx.org_id)
    if invoice_type:
        stmt = stmt.where(Invoice.invoice_type == invoice_type)
    if status:
        stmt = stmt.where(Invoice.status == status)
    stmt = stmt.order_by(Invoice.issue_date.desc())
    rows, total = paginate(ctx.db, stmt, params)
    return Page(items=[_inv_out(ctx, i) for i in rows], total=total,
                page=params.page, page_size=params.page_size)


@router.post("/invoices", response_model=InvoiceOut, status_code=201)
def create_invoice(body: InvoiceIn, ctx: TenantContext = Depends(require("finance:write"))):
    if body.invoice_type == "SALES" and body.customer_id is None:
        from app.core.errors import bad_request
        raise bad_request("MISSING_COUNTERPARTY", "Sales invoice requires customer_id")
    if body.invoice_type == "PURCHASE" and body.supplier_id is None:
        from app.core.errors import bad_request
        raise bad_request("MISSING_COUNTERPARTY", "Purchase invoice requires supplier_id")
    exists = ctx.db.scalar(select(Invoice.id).where(
        Invoice.organization_id == ctx.org_id, Invoice.invoice_type == body.invoice_type,
        Invoice.number == body.number))
    if exists:
        raise conflict("DUPLICATE_NUMBER", "Invoice number already exists")
    inv = Invoice(organization_id=ctx.org_id, status="ISSUED",
                  total=q_money(body.subtotal + body.tax_amount),
                  **body.model_dump())
    ctx.db.add(inv)
    ctx.db.flush()
    record_audit(ctx, "invoice.create", "invoice", inv.id,
                 {"after": {"number": inv.number, "total": inv.total}})
    ctx.db.commit()
    return _inv_out(ctx, inv)


@router.post("/invoices/{invoice_id}/payments", response_model=InvoiceOut, status_code=201)
def add_payment(invoice_id: UUID, body: PaymentIn,
                ctx: TenantContext = Depends(require("finance:write"))):
    inv = ctx.db.scalar(select(Invoice).where(Invoice.id == invoice_id,
                                              Invoice.organization_id == ctx.org_id))
    if inv is None:
        raise not_found("Invoice")
    ctx.db.add(Payment(organization_id=ctx.org_id, invoice_id=inv.id, **body.model_dump()))
    ctx.db.flush()
    paid = ctx.db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(
        Payment.invoice_id == inv.id)) or Decimal("0")
    paid = Decimal(str(paid))
    inv.status = "PAID" if paid >= inv.total else ("PARTIALLY_PAID" if paid > 0 else inv.status)
    record_audit(ctx, "invoice.add_payment", "invoice", inv.id,
                 {"after": {"amount": body.amount}})
    ctx.db.commit()
    return _inv_out(ctx, inv)


@router.get("/receivables")
def receivables(ctx: TenantContext = Depends(require("read"))):
    stmt = select(Invoice).where(Invoice.organization_id == ctx.org_id,
                                 Invoice.invoice_type == "SALES",
                                 Invoice.status.in_(["ISSUED", "PARTIALLY_PAID", "OVERDUE"]))
    invoices = ctx.db.scalars(stmt).all()
    rows = []
    total = ZERO
    overdue = ZERO
    today = date.today()
    for inv in invoices:
        paid = ctx.db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.invoice_id == inv.id)) or Decimal("0")
        balance = Decimal(str(inv.total)) - Decimal(str(paid))
        if balance <= 0:
            continue
        is_overdue = inv.due_date is not None and inv.due_date < today
        rows.append({"invoice_id": str(inv.id), "number": inv.number,
                     "total": str(inv.total), "paid": str(paid), "balance": str(q_money(balance)),
                     "due_date": str(inv.due_date) if inv.due_date else None,
                     "is_overdue": is_overdue})
        total += balance
        if is_overdue:
            overdue += balance
    return {"items": rows, "total_receivable": str(q_money(total)),
            "overdue_receivable": str(q_money(overdue)),
            "currency": ctx.organization.currency_code}


@router.get("/payables")
def payables(ctx: TenantContext = Depends(require("read"))):
    stmt = select(Invoice).where(Invoice.organization_id == ctx.org_id,
                                 Invoice.invoice_type == "PURCHASE",
                                 Invoice.status.in_(["ISSUED", "PARTIALLY_PAID", "OVERDUE"]))
    invoices = ctx.db.scalars(stmt).all()
    total = ZERO
    for inv in invoices:
        paid = ctx.db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.invoice_id == inv.id)) or Decimal("0")
        total += Decimal(str(inv.total)) - Decimal(str(paid))
    return {"total_payable": str(q_money(total)), "currency": ctx.organization.currency_code}


@router.get("/valuation")
def finance_valuation(ctx: TenantContext = Depends(require("read"))):
    lots = ctx.db.scalars(select(StockLot).where(
        StockLot.organization_id == ctx.org_id, StockLot.unit_cost.isnot(None))).all()
    total = inventory_valuation([(l.on_hand_qty, l.unit_cost) for l in lots])
    return {"inventory_value": str(q_money(total)), "currency": ctx.organization.currency_code}


@router.get("/approvals")
def list_approvals(ctx: TenantContext = Depends(require("read")),
                   status: str = Query("PENDING")):
    rows = ctx.db.scalars(select(Approval).where(
        Approval.organization_id == ctx.org_id, Approval.status == status)
        .order_by(Approval.created_at.desc())).all()
    return [{"id": str(a.id), "entity_type": a.entity_type, "entity_id": str(a.entity_id),
             "approval_type": a.approval_type, "status": a.status,
             "created_at": a.created_at.isoformat()} for a in rows]


@router.get("/project-profitability")
def project_profitability(ctx: TenantContext = Depends(require("read"))):
    """Sales orders vs purchase spend per quotation-linked order (indicative margin)."""
    rows = []
    orders = ctx.db.scalars(select(SalesOrder).where(
        SalesOrder.organization_id == ctx.org_id,
        SalesOrder.status.notin_(["CANCELLED"])).limit(100)).all()
    from app.models.procurement import PurchaseOrder, PurchaseRequest
    for so in orders:
        revenue = so.total_value
        spend = Decimal("0")
        prs = ctx.db.scalars(select(Invoice).where(
            Invoice.organization_id == ctx.org_id, Invoice.invoice_type == "PURCHASE",
            Invoice.status.notin_(["CANCELLED"]))).all()
        for inv in prs:
            if inv.purchase_order_id:
                po = ctx.db.get(PurchaseOrder, inv.purchase_order_id)
                if po and po.purchase_request_id:
                    pr = ctx.db.get(PurchaseRequest, po.purchase_request_id)
                    if pr and pr.context.get("sales_order_id") == str(so.id):
                        spend += inv.total
        margin = q_money(revenue - spend)
        rows.append({"sales_order_id": str(so.id), "number": so.number,
                     "revenue": str(revenue), "linked_purchase_spend": str(q_money(spend)),
                     "indicative_margin": str(margin)})
    return {"items": rows, "currency": ctx.organization.currency_code,
            "note": "Indicative report: purchase invoices linked via shortage PRs to the order."}
