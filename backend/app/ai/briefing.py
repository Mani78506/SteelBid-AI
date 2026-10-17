"""AI services grounded in database records.

The AI Daily Briefing, shortage explanations, supplier comparison narratives and the
project copilot ALL derive strictly from tenant-scoped DB rows — every statement links
back to its source record (grounded_in). AI never writes financial facts and never
invents prices, stock, supplier offers or specifications.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.calc.finance import q_money, q_ratio
from app.models.crm import CustomerInquiry
from app.models.inventory import StockLot
from app.models.materials import OrganizationMaterial
from app.models.market import PriceObservation
from app.models.ops import Approval, AuditEvent
from app.models.procurement import PurchaseOrder, PurchaseRequest, SupplierQuote
from app.models.projects import Tender
from app.models.sales import Quotation, SalesOrder


def _fmt(v) -> str:
    return f"{Decimal(str(v)):,.2f}"


def generate_daily_briefing(db: Session, org_id, currency: str = "INR") -> dict:
    items: list[dict] = []
    grounded: list[dict] = []

    overdue_dispatches = db.scalars(select(SalesOrder).where(
        SalesOrder.organization_id == org_id, SalesOrder.status.in_(["CONFIRMED", "READY"]),
        SalesOrder.delivery_date.isnot(None),
        SalesOrder.delivery_date < datetime.now(timezone.utc))).all()
    for so in overdue_dispatches[:5]:
        items.append({"kind": "overdue_order", "severity": "high",
                      "text": f"Sales order {so.number} (value {currency} {_fmt(so.total_value)}) "
                              f"was due {so.delivery_date.date()} and is not dispatched.",
                      "link": f"/sales-orders/{so.id}"})
        grounded.append({"entity": "sales_order", "id": str(so.id)})

    expiring_quotes = db.scalars(select(Quotation).where(
        Quotation.organization_id == org_id, Quotation.status == "SENT",
        Quotation.valid_until.isnot(None),
        Quotation.valid_until < datetime.now(timezone.utc))).all()
    for q in expiring_quotes[:5]:
        items.append({"kind": "expired_quotation", "severity": "medium",
                      "text": f"Quotation {q.number} passed its validity date; refresh pricing before follow-up.",
                      "link": f"/quotations/{q.id}"})
        grounded.append({"entity": "quotation", "id": str(q.id)})

    low_stock = db.execute(
        select(OrganizationMaterial, func.coalesce(func.sum(
            StockLot.on_hand_qty - StockLot.reserved_qty), 0))
        .join(StockLot, (StockLot.material_id == OrganizationMaterial.id)
              & (StockLot.quality_status == "OK"), isouter=True)
        .where(OrganizationMaterial.organization_id == org_id,
               OrganizationMaterial.is_active.is_(True),
               OrganizationMaterial.low_stock_threshold.isnot(None))
        .group_by(OrganizationMaterial.id)).all()
    for mat, avail in low_stock:
        if Decimal(str(avail)) < mat.low_stock_threshold:
            items.append({"kind": "low_stock", "severity": "high",
                          "text": f"{mat.sku} ({mat.name}) available {avail} {mat.base_unit} is below "
                                  f"threshold {mat.low_stock_threshold}.",
                          "link": "/inventory"})
            grounded.append({"entity": "organization_material", "id": str(mat.id)})

    open_prs = db.scalars(select(PurchaseRequest).where(
        PurchaseRequest.organization_id == org_id,
        PurchaseRequest.status.in_(["DRAFT", "RFQ_ISSUED"])).limit(5)).all()
    for pr in open_prs:
        items.append({"kind": "open_purchase_request", "severity": "medium",
                      "text": f"Purchase request {pr.number} is {pr.status.replace('_', ' ').lower()}"
                              + (f"; needed by {pr.needed_by}." if pr.needed_by else "."),
                      "link": "/procurement"})
        grounded.append({"entity": "purchase_request", "id": str(pr.id)})

    pending_approvals = db.scalar(select(func.count()).select_from(Approval).where(
        Approval.organization_id == org_id, Approval.status == "PENDING")) or 0
    if pending_approvals:
        items.append({"kind": "pending_approvals", "severity": "medium",
                      "text": f"{pending_approvals} approval(s) are waiting for a decision.",
                      "link": "/finance/approvals"})

    upcoming_tenders = db.scalars(select(Tender).where(
        Tender.organization_id == org_id,
        Tender.status.in_(["DRAFT", "IN_REVIEW", "ESTIMATING"]),
        Tender.submission_deadline.isnot(None),
        Tender.submission_deadline < datetime.now(timezone.utc) + timedelta(days=7))).all()
    for t in upcoming_tenders[:5]:
        items.append({"kind": "tender_deadline", "severity": "high",
                      "text": f"Tender {t.number} \"{t.title[:60]}\" is due "
                              f"{t.submission_deadline.date()}.",
                      "link": f"/tenders/{t.id}"})
        grounded.append({"entity": "tender", "id": str(t.id)})

    if not items:
        items.append({"kind": "all_clear", "severity": "info",
                      "text": "No urgent alerts: no overdue orders, stale quotations, low-stock "
                              "breaches, open shortages or tender deadlines within 7 days.",
                      "link": None})

    summary = (f"{len(overdue_dispatches)} overdue order(s), "
               f"{len(expiring_quotes)} expired quotation(s), "
               f"{sum(1 for i in items if i['kind'] == 'low_stock')} low-stock material(s), "
               f"{len(open_prs)} open purchase request(s), "
               f"{len(upcoming_tenders)} tender deadline(s) within 7 days.")
    return {"generated_at": datetime.now(timezone.utc),
            "items": items, "summary": summary, "grounded_in": grounded,
            "note": "Briefing is generated from live database records; no external data."}


def explain_shortage(db: Session, org_id, material_id, required_qty: Decimal) -> dict:
    from app.services.inventory import material_availability
    mat = db.get(OrganizationMaterial, material_id)
    if mat is None or mat.organization_id != org_id:
        from app.core.errors import not_found
        raise not_found("Material")
    av = material_availability(None, db, org_id, material_id)
    shortage = max(Decimal("0"), required_qty - av["available"])
    lots = db.scalars(select(StockLot).where(
        StockLot.organization_id == org_id, StockLot.material_id == material_id,
        StockLot.on_hand_qty > 0).order_by(StockLot.on_hand_qty.desc()).limit(10)).all()
    incoming = db.scalars(select(SupplierQuote).where(
        SupplierQuote.organization_id == org_id, SupplierQuote.material_id == material_id,
        SupplierQuote.status == "OPEN")).all()
    explanation = (
        f"Requirement for {mat.sku} is {required_qty} {mat.base_unit}. Eligible availability "
        f"(on-hand minus reserved, quality-OK lots) is {av['available']} {mat.base_unit} across "
        f"{len(lots)} lot(s); {av['quality_held']} is quality-held and excluded. "
        f"Shortfall: {shortage} {mat.base_unit}. "
        f"{len(incoming)} open supplier offer(s) exist for this material.")
    return {
        "explanation": explanation,
        "figures": {"required": str(required_qty), "available": str(av["available"]),
                    "reserved": str(av["reserved"]), "quality_held": str(av["quality_held"]),
                    "shortage": str(shortage)},
        "grounded_in": [{"entity": "organization_material", "id": str(mat.id)}]
        + [{"entity": "stock_lot", "id": str(l.id)} for l in lots]
        + [{"entity": "supplier_quote", "id": str(q.id)} for q in incoming],
    }


def answer_copilot(db: Session, org_id, question: str, project_id=None) -> dict:
    """Record-grounded copilot: answers only what the tenant database supports."""
    ql = question.lower()
    grounded: list[dict] = []
    if any(w in ql for w in ("stock", "inventory", "available", "availability")):
        lots_count = db.scalar(select(func.count()).select_from(StockLot).where(
            StockLot.organization_id == org_id, StockLot.on_hand_qty > 0)) or 0
        total_qty = db.scalar(select(func.coalesce(func.sum(
            StockLot.on_hand_qty - StockLot.reserved_qty), 0)).where(
            StockLot.organization_id == org_id, StockLot.quality_status == "OK")) or 0
        return {"answer": f"As of now the organization holds {total_qty} MT of eligible "
                          f"(unreserved, quality-OK) stock across {lots_count} lot(s). "
                          "Open the Inventory page for lot-level detail.",
                "grounded_in": [{"entity": "stock_lot", "aggregate": True}]}
    if any(w in ql for w in ("order", "sales", "revenue")):
        row = db.execute(select(func.count(), func.coalesce(func.sum(SalesOrder.total_value), 0))
                         .where(SalesOrder.organization_id == org_id,
                                SalesOrder.status.notin_(["CANCELLED"]))).one()
        return {"answer": f"There are {row[0]} active sales order(s) worth "
                          f"{q_money(Decimal(str(row[1])))} in total.",
                "grounded_in": [{"entity": "sales_order", "aggregate": True}]}
    if any(w in ql for w in ("price", "market", "rate")):
        latest = db.scalars(select(PriceObservation).where(
            (PriceObservation.organization_id == org_id)
            | (PriceObservation.organization_id.is_(None)))
            .order_by(PriceObservation.observed_on.desc()).limit(1)).first()
        if latest:
            synth = " (labeled synthetic demo data)" if latest.is_synthetic else ""
            return {"answer": f"Latest recorded observation: {latest.material_form} "
                              f"{latest.grade} at {latest.price_per_unit} {latest.currency}/"
                              f"{latest.unit} in {latest.region} on {latest.observed_on}{synth}.",
                    "grounded_in": [{"entity": "price_observation", "id": str(latest.id)}]}
    if any(w in ql for w in ("urgent", "today", "priority", "briefing", "alert")):
        b = generate_daily_briefing(db, org_id)
        top = [i["text"] for i in b["items"][:3]]
        return {"answer": "Top priorities: " + " ".join(top),
                "grounded_in": b["grounded_in"]}
    return {"answer": "I can answer questions grounded in your records — try asking about "
                      "stock availability, active sales orders, latest price observations "
                      "or today's priorities.",
            "grounded_in": grounded}
