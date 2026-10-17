from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.ai.briefing import generate_daily_briefing
from app.calc.finance import ZERO, gross_margin, q_money
from app.core.deps import TenantContext, require
from app.models.crm import Customer, CustomerInquiry
from app.models.inventory import StockLot, Warehouse
from app.models.market import PriceObservation
from app.models.materials import OrganizationMaterial
from app.models.ops import Approval, AuditEvent, Dispatch, Invoice, Payment
from app.models.procurement import PurchaseOrder, PurchaseRequest, Supplier
from app.models.projects import Tender
from app.models.fabrication import WorkOrder
from app.models.sales import Quotation, QuotationVersion, SalesOrder
from app.schemas.ops import DashboardSummary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def summary(days: int = Query(30, ge=1, le=365), ctx: TenantContext = Depends(require("read"))):
    db, org = ctx.db, ctx.org_id
    now = datetime.now(timezone.utc)

    # ---- KPI cards (all tenant-scoped DB arithmetic) ----
    lots = db.scalars(select(StockLot).where(StockLot.organization_id == org,
                                            StockLot.unit_cost.isnot(None))).all()
    inventory_value = sum((l.on_hand_qty * l.unit_cost for l in lots), ZERO)

    open_so_row = db.execute(select(func.count(), func.coalesce(func.sum(SalesOrder.total_value), 0))
                             .where(SalesOrder.organization_id == org,
                                    SalesOrder.status.in_(["CONFIRMED", "IN_PRODUCTION", "READY"]))).one()
    open_so_count, open_so_value = open_so_row[0], Decimal(str(open_so_row[1]))

    po_row = db.execute(select(func.count(), func.coalesce(func.sum(PurchaseOrder.total_value), 0))
                        .where(PurchaseOrder.organization_id == org,
                               PurchaseOrder.status.in_(["APPROVED", "SENT", "PARTIALLY_RECEIVED"]))).one()
    po_count, po_value = po_row[0], Decimal(str(po_row[1]))

    pending_quotes = db.scalar(select(func.count()).select_from(Quotation).where(
        Quotation.organization_id == org,
        Quotation.status.in_(["DRAFT", "PENDING_APPROVAL", "APPROVED", "SENT"]))) or 0

    margins = db.scalars(select(QuotationVersion.gross_margin_pct).join(Quotation).where(
        Quotation.organization_id == org, QuotationVersion.is_immutable.is_(True),
        Quotation.created_at >= now - timedelta(days=days))).all()
    avg_margin = (sum((Decimal(str(m)) for m in margins), ZERO) / len(margins)
                  if margins else ZERO)

    today = datetime.now(timezone.utc).date()
    overdue_receivable = ZERO
    overdue_invoices = db.scalars(select(Invoice).where(
        Invoice.organization_id == org, Invoice.invoice_type == "SALES",
        Invoice.status.in_(["ISSUED", "PARTIALLY_PAID", "OVERDUE"]),
        Invoice.due_date.isnot(None), Invoice.due_date < today)).all()
    overdue_count = 0
    for inv in overdue_invoices:
        paid = db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.invoice_id == inv.id)) or Decimal("0")
        balance = Decimal(str(inv.total)) - Decimal(str(paid))
        if balance > 0:
            overdue_receivable += balance
            overdue_count += 1

    at_risk_orders = db.scalar(select(func.count()).select_from(SalesOrder).where(
        SalesOrder.organization_id == org, SalesOrder.status.in_(["CONFIRMED", "IN_PRODUCTION", "READY"]),
        SalesOrder.delivery_date.isnot(None),
        SalesOrder.delivery_date < now + timedelta(days=3))) or 0

    pending_approvals = db.scalar(select(func.count()).select_from(Approval).where(
        Approval.organization_id == org, Approval.status == "PENDING")) or 0

    kpis = {
        "inventory_valuation": {"value": str(q_money(inventory_value)), "currency": ctx.organization.currency_code},
        "open_sales_order_value": {"value": str(q_money(open_so_value)), "count": open_so_count,
                                   "currency": ctx.organization.currency_code},
        "purchase_commitments": {"value": str(q_money(po_value)), "count": po_count,
                                 "currency": ctx.organization.currency_code},
        "pending_quotations": {"count": pending_quotes},
        "estimated_gross_margin": {"value": str(avg_margin.quantize(Decimal("0.000001"))),
                                   "basis": f"approved quotations, last {days}d"},
        "overdue_receivables": {"value": str(q_money(overdue_receivable)), "count": overdue_count,
                                "currency": ctx.organization.currency_code},
        "at_risk_orders": {"count": at_risk_orders},
        "pending_approvals": {"count": pending_approvals},
        "material_count": db.scalar(select(func.count()).select_from(OrganizationMaterial).where(
            OrganizationMaterial.organization_id == org, OrganizationMaterial.is_active.is_(True))) or 0,
        "warehouse_count": db.scalar(select(func.count()).select_from(Warehouse).where(
            Warehouse.organization_id == org, Warehouse.is_active.is_(True))) or 0,
        "supplier_count": db.scalar(select(func.count()).select_from(Supplier).where(
            Supplier.organization_id == org, Supplier.is_active.is_(True))) or 0,
        "customer_count": db.scalar(select(func.count()).select_from(Customer).where(
            Customer.organization_id == org, Customer.is_active.is_(True))) or 0,
        "quotation_status_distribution": {
            s: c for s, c in db.execute(select(Quotation.status, func.count()).where(
                Quotation.organization_id == org).group_by(Quotation.status)).all()},
    }

    # ---- Today's priorities (derived, severity-ordered) ----
    priorities = []
    for so_number, so_id, due, cust in db.execute(
            select(SalesOrder.number, SalesOrder.id, SalesOrder.delivery_date, Customer.name)
            .join(Customer, Customer.id == SalesOrder.customer_id)
            .where(SalesOrder.organization_id == org,
                   SalesOrder.status.in_(["CONFIRMED", "IN_PRODUCTION", "READY"]),
                   SalesOrder.delivery_date.isnot(None),
                   SalesOrder.delivery_date < now + timedelta(days=3))
            .order_by(SalesOrder.delivery_date).limit(5)).all():
        priorities.append({"severity": "high", "kind": "order_deadline",
                           "text": f"{so_number} for {cust} due {due.date()}",
                           "link": f"/sales-orders/{so_id}"})
    low = db.execute(
        select(OrganizationMaterial.sku, OrganizationMaterial.name,
               OrganizationMaterial.low_stock_threshold,
               func.coalesce(func.sum(StockLot.on_hand_qty - StockLot.reserved_qty), 0))
        .join(StockLot, (StockLot.material_id == OrganizationMaterial.id)
              & (StockLot.quality_status == "OK"), isouter=True)
        .where(OrganizationMaterial.organization_id == org,
               OrganizationMaterial.low_stock_threshold.isnot(None),
               OrganizationMaterial.is_active.is_(True))
        .group_by(OrganizationMaterial.id)).all()
    for sku, name, threshold, avail in low:
        if Decimal(str(avail)) < threshold:
            priorities.append({"severity": "medium", "kind": "low_stock",
                               "text": f"{sku} ({name}) below threshold: {avail} available",
                               "link": "/inventory"})
    for pr_number, pr_id, status in db.execute(
            select(PurchaseRequest.number, PurchaseRequest.id, PurchaseRequest.status).where(
            PurchaseRequest.organization_id == org,
            PurchaseRequest.status.in_(["DRAFT", "RFQ_ISSUED"])).limit(3)).all():
        priorities.append({"severity": "medium", "kind": "open_pr",
                           "text": f"{pr_number} awaiting procurement action ({status.replace('_', ' ').lower()})",
                           "link": "/procurement"})
    priorities = priorities[:8]

    recent_inquiries = [
        {"id": str(i.id), "reference": i.reference, "customer": c, "status": i.status,
         "received_at": i.received_at.isoformat()}
        for i, c in db.execute(
            select(CustomerInquiry, Customer.name)
            .join(Customer, Customer.id == CustomerInquiry.customer_id)
            .where(CustomerInquiry.organization_id == org)
            .order_by(CustomerInquiry.received_at.desc()).limit(5)).all()]

    # procurement shortages: active PR items vs current availability
    shortages = []
    from app.models.procurement import PurchaseRequestItem
    for pr, item, mat_name in db.execute(
            select(PurchaseRequest, PurchaseRequestItem, OrganizationMaterial.name)
            .join(PurchaseRequestItem,
                  PurchaseRequestItem.purchase_request_id == PurchaseRequest.id)
            .join(OrganizationMaterial,
                  OrganizationMaterial.id == PurchaseRequestItem.material_id)
            .where(PurchaseRequest.organization_id == org,
                   PurchaseRequest.status.in_(["DRAFT", "RFQ_ISSUED", "ORDERED"])).limit(8)).all():
        shortages.append({"pr_id": str(pr.id), "pr_number": pr.number, "material": mat_name,
                          "quantity": str(item.quantity), "status": pr.status,
                          "needed_by": str(pr.needed_by) if pr.needed_by else None})

    latest_prices = [
        {"form": p.material_form, "grade": p.grade, "region": p.region,
         "price": str(p.price_per_unit), "unit": p.unit, "observed_on": str(p.observed_on),
         "is_synthetic": p.is_synthetic}
        for p in db.scalars(select(PriceObservation).where(
            (PriceObservation.organization_id == org) | (PriceObservation.organization_id.is_(None)))
            .order_by(PriceObservation.observed_on.desc()).limit(6)).all()]

    upcoming_dispatches = [
        {"id": str(d.id), "number": d.number, "status": d.status,
         "dispatch_date": str(d.dispatch_date) if d.dispatch_date else None,
         "transporter": d.transporter}
        for d in db.scalars(select(Dispatch).where(
            Dispatch.organization_id == org,
            Dispatch.status.in_(["PLANNED", "PICKING", "READY", "DISPATCHED"]))
            .order_by(Dispatch.created_at.desc()).limit(5)).all()]

    production = [
        {"id": str(w.id), "number": w.number, "status": w.status,
         "planned_qty": str(w.planned_qty), "produced_qty": str(w.produced_qty)}
        for w in db.scalars(select(WorkOrder).where(
            WorkOrder.organization_id == org,
            WorkOrder.status.notin_(["COMPLETED", "CANCELLED"]))
            .order_by(WorkOrder.created_at.desc()).limit(5)).all()]

    tender_deadlines = [
        {"id": str(t.id), "number": t.number, "title": t.title,
         "deadline": t.submission_deadline.isoformat(), "status": t.status}
        for t in db.scalars(select(Tender).where(
            Tender.organization_id == org, Tender.submission_deadline.isnot(None),
            Tender.status.in_(["DRAFT", "IN_REVIEW", "ESTIMATING", "BID_SUBMITTED"]))
            .order_by(Tender.submission_deadline).limit(5)).all()]

    recent_activity = [
        {"id": str(a.id), "action": a.action, "entity_type": a.entity_type,
         "created_at": a.created_at.isoformat(), "user_id": str(a.user_id) if a.user_id else None}
        for a in db.scalars(select(AuditEvent).where(AuditEvent.organization_id == org)
                            .order_by(AuditEvent.created_at.desc()).limit(10)).all()]

    return DashboardSummary(
        organization={"id": str(ctx.organization.id), "name": ctx.organization.name,
                      "profiles": ctx.organization.business_profiles,
                      "currency": ctx.organization.currency_code},
        kpis=kpis, priorities=priorities, recent_inquiries=recent_inquiries,
        procurement_shortages=shortages, price_observations=latest_prices,
        upcoming_dispatches=upcoming_dispatches, production_status=production,
        tender_deadlines=tender_deadlines, recent_activity=recent_activity)


@router.get("/briefing")
def briefing(ctx: TenantContext = Depends(require("read"))):
    return generate_daily_briefing(ctx.db, ctx.org_id, ctx.organization.currency_code)
