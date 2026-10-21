from datetime import datetime, timedelta, timezone, date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, and_, or_

from app.ai.briefing import generate_daily_briefing
from app.calc.finance import ZERO, gross_margin, q_money
from app.core.deps import TenantContext, require
from app.models.crm import Customer, CustomerInquiry
from app.models.inventory import StockLot, Warehouse, Reservation
from app.models.market import PriceObservation, PriceScenario, PriceSource
from app.models.materials import OrganizationMaterial
from app.models.ops import Approval, AuditEvent, Dispatch, Invoice, Payment
from app.models.procurement import PurchaseOrder, PurchaseRequest, Supplier, SupplierQuote, RFQ
from app.models.projects import Tender
from app.models.fabrication import WorkOrder, BOMItem
from app.models.sales import Quotation, QuotationVersion, SalesOrder
from app.schemas.ops import DashboardSummary, EnhancedDashboardSummary

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


@router.get("/enhanced", response_model=EnhancedDashboardSummary)
def enhanced_summary(days: int = Query(30, ge=1, le=365), ctx: TenantContext = Depends(require("read"))):
    """Enhanced dashboard with market intelligence, tender intelligence, BOQ/BOM status,
    inventory breakdown, tender costing, procurement intelligence, and approvals queue."""
    db, org = ctx.db, ctx.org_id
    now = datetime.now(timezone.utc)
    today = now.date()

    # First, get the base summary data (reuse existing logic)
    base = summary(days, ctx=ctx)
    base_dict = base.model_dump()

    # ---- Market Intelligence enhancements ----
    # Derive actual comparable series; never hard-code product coverage.
    series_rows = db.scalars(select(PriceObservation).where(
        (PriceObservation.organization_id == org) | (PriceObservation.organization_id.is_(None)))
        .order_by(PriceObservation.observed_on.desc(), PriceObservation.created_at.desc()).limit(100)).all()
    key_products = []
    seen_series = set()
    for observation in series_rows:
        key = (observation.material_form, observation.grade, observation.region, observation.price_basis, observation.unit, observation.currency)
        if key not in seen_series:
            seen_series.add(key); key_products.append(key)
        if len(key_products) == 6: break
    market_trends = []
    for form, grade, region, basis, unit, currency in key_products:
        latest = db.scalar(select(PriceObservation).where(
            PriceObservation.material_form == form,
            PriceObservation.grade == grade,
            PriceObservation.region == region, PriceObservation.price_basis == basis,
            PriceObservation.unit == unit, PriceObservation.currency == currency,
            (PriceObservation.organization_id == org) | (PriceObservation.organization_id.is_(None)))
            .order_by(PriceObservation.observed_on.desc()).limit(1))
        if latest:
            # Calculate 30d change
            cutoff = today - timedelta(days=30)
            older = db.scalar(select(PriceObservation).where(
                PriceObservation.material_form == form,
                PriceObservation.grade == grade,
                PriceObservation.region == region, PriceObservation.price_basis == basis,
                PriceObservation.unit == unit, PriceObservation.currency == currency,
                PriceObservation.observed_on <= cutoff,
                (PriceObservation.organization_id == org) | (PriceObservation.organization_id.is_(None)))
                .order_by(PriceObservation.observed_on.desc()).limit(1))
            change_30d = None
            if older and older.price_per_unit > 0:
                change_30d = str(q_money((latest.price_per_unit - older.price_per_unit) / older.price_per_unit))
            market_trends.append({
                "form": form, "grade": grade, "region": region, "price_basis": basis, "latest_price": str(latest.price_per_unit),
                "currency": latest.currency, "unit": latest.unit,
                "observed_on": str(latest.observed_on), "change_30d_pct": change_30d,
                "is_synthetic": latest.is_synthetic, "freshness_days": (today - latest.observed_on).days,
                "source": (db.get(PriceSource, latest.source_id).name if latest.source_id else "Unattributed observation")
            })

    # 30d vs 90d price comparisons for key products
    market_comparisons = []
    for form, grade, region, basis, unit, currency in key_products:
        cutoff_30 = today - timedelta(days=30)
        cutoff_90 = today - timedelta(days=90)
        price_30d = db.scalar(select(PriceObservation.price_per_unit).where(
            PriceObservation.material_form == form,
            PriceObservation.grade == grade,
            PriceObservation.region == region, PriceObservation.price_basis == basis,
            PriceObservation.unit == unit, PriceObservation.currency == currency,
            PriceObservation.observed_on <= cutoff_30,
            (PriceObservation.organization_id == org) | (PriceObservation.organization_id.is_(None)))
            .order_by(PriceObservation.observed_on.desc()).limit(1))
        price_90d = db.scalar(select(PriceObservation.price_per_unit).where(
            PriceObservation.material_form == form,
            PriceObservation.grade == grade,
            PriceObservation.region == region, PriceObservation.price_basis == basis,
            PriceObservation.unit == unit, PriceObservation.currency == currency,
            PriceObservation.observed_on <= cutoff_90,
            (PriceObservation.organization_id == org) | (PriceObservation.organization_id.is_(None)))
            .order_by(PriceObservation.observed_on.desc()).limit(1))
        if price_30d and price_90d and price_90d > 0:
            market_comparisons.append({
                "form": form, "grade": grade,
                "price_30d": str(price_30d), "price_90d": str(price_90d),
                "change_pct": str(q_money((price_30d - price_90d) / price_90d))
            })

    # Scenario summary
    scenario_count = db.scalar(select(func.count()).select_from(PriceScenario).where(
        PriceScenario.organization_id == org,
        PriceScenario.created_at >= now - timedelta(days=days))) or 0
    scenario_summary = {"total_scenarios": scenario_count, "period_days": days}

    # ---- Tender Intelligence enhancements ----
    # New tenders within 30 days
    new_tenders = []
    for t in db.scalars(select(Tender).where(
        Tender.organization_id == org,
        Tender.submission_deadline.isnot(None),
        Tender.submission_deadline >= today,
        Tender.submission_deadline <= today + timedelta(days=30),
        Tender.status.in_(["DRAFT", "IN_REVIEW", "ESTIMATING"]))
        .order_by(Tender.submission_deadline).limit(5)).all():
        # Submission deadlines are timestamps while dashboard comparisons are date based.
        # Normalise first so a persisted tender cannot blank the Command Center.
        deadline_date = t.submission_deadline.date() if isinstance(t.submission_deadline, datetime) else t.submission_deadline
        days_until = (deadline_date - today).days
        new_tenders.append({
            "id": str(t.id), "number": t.number, "title": t.title,
            "deadline": str(t.submission_deadline), "days_until": days_until,
            "status": t.status
        })

    # Tender pipeline counts
    pipeline_statuses = ["DRAFT", "IN_REVIEW", "ESTIMATING", "BID_SUBMITTED", "WON", "LOST"]
    tender_pipeline = {}
    for status in pipeline_statuses:
        count = db.scalar(select(func.count()).select_from(Tender).where(
            Tender.organization_id == org, Tender.status == status)) or 0
        tender_pipeline[status] = count
    active_statuses = ["DRAFT", "IN_REVIEW", "ESTIMATING", "BID_SUBMITTED"]
    pipeline_value, missing_value_count = db.execute(
        select(func.coalesce(func.sum(Tender.estimated_value), 0), func.count())
        .where(Tender.organization_id == org, Tender.status.in_(active_statuses),
               Tender.estimated_value.is_(None))).one()
    tender_pipeline["active_estimated_value"] = str(q_money(Decimal(str(pipeline_value)))) if pipeline_value else None
    tender_pipeline["active_value_unavailable_count"] = missing_value_count

    # Tender amendments (updated in last 7 days)
    tender_amendments = []
    for t in db.scalars(select(Tender).where(
        Tender.organization_id == org,
        Tender.updated_at >= now - timedelta(days=7))
        .order_by(Tender.updated_at.desc()).limit(5)).all():
        tender_amendments.append({
            "id": str(t.id), "number": t.number, "title": t.title,
            "status": t.status, "updated_at": t.updated_at.isoformat()
        })

    # ---- BOQ/BOM Intelligence ----
    # BOQ review status: tenders with BOQ items but not marked as reviewed
    from app.models.projects import BOQItem
    boq_pending = db.scalar(select(func.count()).select_from(Tender).join(
        BOQItem, BOQItem.tender_id == Tender.id).where(
        Tender.organization_id == org,
        BOQItem.review_status == "PENDING",
        Tender.status.in_(["DRAFT", "IN_REVIEW", "ESTIMATING"]))) or 0
    boq_review_status = {"pending_review": boq_pending}

    # BOM readiness: material availability for active work orders
    bom_readiness = []
    for wo in db.scalars(select(WorkOrder).where(
        WorkOrder.organization_id == org,
        WorkOrder.status.in_(["CONFIRMED", "IN_PROGRESS"])).limit(5)).all():
        # Get BOM items for this work order
        if not wo.bom_version_id:
            bom_readiness.append({
                "id": str(wo.id), "number": wo.number, "status": wo.status,
                "material_readiness": None,
            })
            continue
        bom_items = db.scalars(select(BOMItem).where(
            BOMItem.bom_version_id == wo.bom_version_id)).all()
        ready_count = 0
        total_count = len(bom_items)
        for bi in bom_items:
            # Check inventory availability
            from app.services.inventory import material_availability
            avail = material_availability(None, db, org, bi.material_id)
            if avail["available"] >= bi.quantity:
                ready_count += 1
        bom_readiness.append({
            "id": str(wo.id), "number": wo.number, "status": wo.status,
            "material_readiness": f"{ready_count}/{total_count} items ready"
        })

    # Tender-specific shortages (linking tender BOQ to inventory)
    tender_shortages = []
    for tender_id in db.scalars(select(Tender.id).where(
        Tender.organization_id == org,
        Tender.status.in_(["DRAFT", "IN_REVIEW", "ESTIMATING"])).limit(3)).all():
        for bi in db.scalars(select(BOQItem).where(BOQItem.tender_id == tender_id)).all():
            from app.services.inventory import material_availability
            avail = material_availability(None, db, org, bi.material_id)
            if avail["available"] < bi.quantity:
                shortage = bi.quantity - avail["available"]
                tender_shortages.append({
                    "tender_id": str(tender_id),
                    "material_id": str(bi.material_id),
                    "required_qty": str(bi.quantity),
                    "available_qty": str(avail["available"]),
                    "shortage_qty": str(shortage)
                })

    # ---- Inventory Intelligence (enhanced) ----
    lots = db.scalars(select(StockLot).where(StockLot.organization_id == org)).all()
    on_hand = sum(l.on_hand_qty for l in lots)
    available = sum(l.on_hand_qty - l.reserved_qty for l in lots)
    reserved = sum(l.reserved_qty for l in lots)
    quality_held = sum(l.on_hand_qty for l in lots if l.quality_status == "QUARANTINED")
    inventory_breakdown = {
        "on_hand": str(on_hand), "available": str(available),
        "reserved": str(reserved), "quality_held": str(quality_held),
        "unit": "MT"
    }

    # ATP for top 5 materials
    atp_by_material = []
    top_materials = db.execute(
        select(OrganizationMaterial.id, OrganizationMaterial.name,
               func.coalesce(func.sum(StockLot.on_hand_qty - StockLot.reserved_qty), 0))
        .join(StockLot, (StockLot.material_id == OrganizationMaterial.id)
              & (StockLot.quality_status == "OK"), isouter=True)
        .where(OrganizationMaterial.organization_id == org, OrganizationMaterial.is_active.is_(True))
        .group_by(OrganizationMaterial.id)
        .order_by(func.coalesce(func.sum(StockLot.on_hand_qty - StockLot.reserved_qty), 0).desc())
        .limit(5)).all()
    for mat_id, mat_name, avail in top_materials:
        atp_by_material.append({"material_id": str(mat_id), "name": mat_name, "available_atp": str(avail or 0)})

    # ---- Tender Costing Intelligence ----
    # Active costing quotes (pending approval, can be from tenders or regular inquiries)
    active_costing_quotes = []
    for q in db.scalars(select(Quotation).where(
        Quotation.organization_id == org,
        Quotation.status == "PENDING_APPROVAL").limit(5)).all():
        qv = db.scalar(select(QuotationVersion).where(
            QuotationVersion.quotation_id == q.id,
            QuotationVersion.is_immutable.is_(True)).order_by(QuotationVersion.version_no.desc()).limit(1))
        total_selling = str(qv.total_selling_price) if qv else "0"
        estimated_cost = str(qv.total_estimated_cost) if qv else "0"
        gross_margin = str(qv.gross_margin_pct) if qv else "0"
        active_costing_quotes.append({
            "id": str(q.id), "number": q.number, "customer_id": str(q.customer_id),
            "total_selling": total_selling,
            "estimated_cost": estimated_cost,
            "gross_margin_pct": gross_margin
        })

    # Margin exposure: sum of margin at risk (pending quotes with price sensitivity)
    margin_exposure = {"total_pending_value": "0", "at_risk_margin": "0"}
    pending_value = db.scalar(select(func.coalesce(func.sum(QuotationVersion.total_selling_price), 0)).join(
        Quotation, Quotation.id == QuotationVersion.quotation_id).where(
        Quotation.organization_id == org,
        Quotation.status == "PENDING_APPROVAL")) or Decimal("0")
    margin_exposure["total_pending_value"] = str(pending_value)
    # Calculate weighted average margin of pending quotes
    pending_margins = db.scalars(select(QuotationVersion.gross_margin_pct).join(
        Quotation, Quotation.id == QuotationVersion.quotation_id).where(
        Quotation.organization_id == org,
        Quotation.status == "PENDING_APPROVAL")).all()
    if pending_margins:
        avg_pending_margin = sum(pending_margins, ZERO) / len(pending_margins)
        margin_exposure["at_risk_margin"] = str(avg_pending_margin.quantize(Decimal("0.000001")))

    # Pricing scenarios related to tenders
    # Scenarios are stored as JSON parameters; no forecast is inferred from them.
    pricing_scenarios = {"total_scenarios": scenario_count, "tender_related": None,
                         "label": "validated saved scenarios only"}

    # ---- Procurement Intelligence (enhanced) ----
    # Open RFQs
    open_rfqs = db.scalar(select(func.count()).select_from(RFQ).where(
        RFQ.organization_id == org,
        RFQ.status == "ISSUED",
        RFQ.valid_until >= today)) or 0

    # Pending supplier quotes
    pending_quotes = db.scalar(select(func.count()).select_from(SupplierQuote).where(
        SupplierQuote.organization_id == org,
        SupplierQuote.status == "OPEN")) or 0

    # Delivery risks: POs with delivery within 3 days but no GRN
    delivery_risks = []
    for po in db.scalars(select(PurchaseOrder).where(
        PurchaseOrder.organization_id == org,
        PurchaseOrder.status.in_(["APPROVED", "SENT"]),
        PurchaseOrder.expected_delivery.isnot(None),
        PurchaseOrder.expected_delivery <= today + timedelta(days=3)).order_by(PurchaseOrder.expected_delivery).limit(5)).all():
        # Check if GRN exists
        from app.models.procurement import GoodsReceipt
        grn_count = db.scalar(select(func.count()).select_from(GoodsReceipt).where(
            GoodsReceipt.purchase_order_id == po.id)) or 0
        if grn_count == 0:
            days_late = (today - po.expected_delivery).days if po.expected_delivery < today else 0
            delivery_risks.append({
                "id": str(po.id), "number": po.number, "expected_delivery": str(po.expected_delivery),
                "days_late": days_late, "supplier_id": str(po.supplier_id)
            })

    # ---- Approvals Queue ----
    approval_queue = []
    # Pending quotations
    for q in db.scalars(select(Quotation).where(
        Quotation.organization_id == org,
        Quotation.status == "PENDING_APPROVAL").limit(5)).all():
        approval_queue.append({
            "type": "quotation", "id": str(q.id), "number": q.number,
            "value": str(qv) if (qv := db.scalar(select(QuotationVersion.total_selling_price).where(
                QuotationVersion.quotation_id == q.id, QuotationVersion.is_immutable.is_(True)))) is not None else None,
            "created_at": q.created_at.isoformat()
        })
    # Pending POs
    for po in db.scalars(select(PurchaseOrder).where(
        PurchaseOrder.organization_id == org,
        PurchaseOrder.status == "DRAFT").limit(5)).all():
        approval_queue.append({
            "type": "purchase_order", "id": str(po.id), "number": po.number,
            "value": str(po.total_value), "created_at": po.created_at.isoformat()
        })

    # Price alerts: stale observations (>14 days old)
    stale_cutoff = today - timedelta(days=14)
    stale_count = db.scalar(select(func.count()).select_from(PriceObservation).where(
        (PriceObservation.organization_id == org) | (PriceObservation.organization_id.is_(None)),
        PriceObservation.observed_on < stale_cutoff)) or 0
    price_alerts = {"stale_observations": stale_count, "stale_threshold_days": 14}

    # Build enhanced response
    return EnhancedDashboardSummary(
        organization=base_dict["organization"],
        kpis=base_dict["kpis"],
        priorities=base_dict["priorities"],
        recent_inquiries=base_dict["recent_inquiries"],
        procurement_shortages=base_dict["procurement_shortages"],
        price_observations=base_dict["price_observations"],
        upcoming_dispatches=base_dict["upcoming_dispatches"],
        production_status=base_dict["production_status"],
        tender_deadlines=base_dict["tender_deadlines"],
        recent_activity=base_dict["recent_activity"],
        market_trends=market_trends,
        market_comparisons=market_comparisons,
        scenario_summary=scenario_summary,
        new_tenders=new_tenders,
        tender_pipeline=tender_pipeline,
        tender_amendments=tender_amendments,
        boq_review_status=boq_review_status,
        bom_readiness=bom_readiness,
        tender_shortages=tender_shortages,
        inventory_breakdown=inventory_breakdown,
        atp_by_material=atp_by_material,
        active_costing_quotes=active_costing_quotes,
        margin_exposure=margin_exposure,
        pricing_scenarios=pricing_scenarios,
        open_rfqs={"count": open_rfqs},
        pending_quotes={"count": pending_quotes},
        delivery_risks=delivery_risks,
        approval_queue=approval_queue,
        price_alerts=price_alerts
    )
