"""Quotation domain service: cost build-up, margin pricing, versioning, conversion."""
from decimal import Decimal

from sqlalchemy import select

from app.calc.finance import (ZERO, cost_estimate_total, gross_margin, q_money, q_ratio, q_qty,
                              selling_from_margin, weighted_average_cost)
from app.core.errors import bad_request, conflict, not_found
from app.models.crm import Customer, CustomerInquiry
from app.models.inventory import StockLot
from app.models.materials import OrganizationMaterial
from app.models.ops import Approval, CostEstimate, CostLine
from app.models.sales import (Quotation, QuotationItem, QuotationVersion, SalesOrder,
                              SalesOrderItem)
from app.services.inventory import material_availability
from app.services.numbering import next_number

QUOTATION_FLOW = {
    "DRAFT": {"PENDING_APPROVAL", "REJECTED"},
    "PENDING_APPROVAL": {"APPROVED", "REJECTED"},
    "APPROVED": {"SENT", "EXPIRED", "CONVERTED"},
    "SENT": {"ACCEPTED", "REJECTED", "EXPIRED"},
    "ACCEPTED": {"CONVERTED"},
    "REJECTED": set(), "EXPIRED": set(), "CONVERTED": set(),
}


def _wac_for_material(ctx, material_id) -> Decimal:
    rows = ctx.db.execute(
        select(StockLot.on_hand_qty, StockLot.unit_cost).where(
            StockLot.organization_id == ctx.org_id, StockLot.material_id == material_id,
            StockLot.on_hand_qty > 0, StockLot.unit_cost.isnot(None))).all()
    return weighted_average_cost([(Decimal(str(q)), Decimal(str(c))) for q, c in rows])


def _resolve_unit_cost(ctx, material_id, provided: Decimal) -> Decimal:
    if provided and provided > 0:
        return provided
    if material_id:
        wac = _wac_for_material(ctx, material_id)
        if wac > 0:
            return wac
    return ZERO


def get_quotation_scoped(ctx, quotation_id) -> Quotation:
    q = ctx.db.scalar(select(Quotation).where(Quotation.id == quotation_id,
                                              Quotation.organization_id == ctx.org_id))
    if q is None:
        raise not_found("Quotation")
    return q


def build_quotation_pdf_html(ctx, quotation: Quotation, version: QuotationVersion,
                             items: list[QuotationItem]) -> str:
    """Customer-facing quotation: prices only — internal costs/suppliers are NEVER included."""
    customer = ctx.db.get(Customer, quotation.customer_id)
    rows = "".join(
        f"<tr><td>{it.description}</td><td>{it.form or ''}</td><td>{it.grade or ''}</td>"
        f"<td style='text-align:right'>{it.quantity}</td><td>{it.unit}</td>"
        f"<td style='text-align:right'>{it.unit_price}</td>"
        f"<td style='text-align:right'>{it.line_selling_price}</td></tr>"
        for it in items)
    return f"""<!doctype html><html><head><meta charset='utf-8'><style>
body{{font-family:Arial,sans-serif;color:#1e293b;margin:40px;font-size:13px}}
h1{{color:#1d4ed8;font-size:20px}} table{{border-collapse:collapse;width:100%;margin-top:16px}}
th,td{{border:1px solid #cbd5e1;padding:6px 8px}} th{{background:#f1f5f9;text-align:left}}
.meta td{{border:none;padding:2px 8px 2px 0}}</style></head><body>
<h1>Quotation {quotation.number}</h1>
<table class='meta'>
<tr><td><b>From:</b> {ctx.organization.name}</td></tr>
<tr><td><b>To:</b> {customer.name if customer else ''}</td></tr>
<tr><td><b>Version:</b> {version.version_no} &nbsp; <b>Currency:</b> {quotation.currency}
&nbsp; <b>Valid until:</b> {quotation.valid_until.date() if quotation.valid_until else '—'}</td></tr>
</table>
<table><thead><tr><th>Description</th><th>Form</th><th>Grade</th><th>Qty</th><th>Unit</th>
<th>Unit price</th><th>Amount</th></tr></thead><tbody>{rows}</tbody>
<tfoot><tr><td colspan='6' style='text-align:right'><b>Total</b></td>
<td style='text-align:right'><b>{version.total_selling_price}</b></td></tr></tfoot></table>
<p style='margin-top:24px;color:#64748b'>Prices are exclusive of taxes unless stated otherwise.
This is a system-generated document.</p></body></html>"""


def create_quotation(ctx, body) -> Quotation:
    customer = ctx.db.scalar(select(Customer).where(Customer.id == body.customer_id,
                                                    Customer.organization_id == ctx.org_id))
    if customer is None:
        raise not_found("Customer")
    inquiry = None
    if body.inquiry_id:
        inquiry = ctx.db.scalar(select(CustomerInquiry).where(
            CustomerInquiry.id == body.inquiry_id, CustomerInquiry.organization_id == ctx.org_id))
        if inquiry is None:
            raise not_found("Inquiry")
    quotation = Quotation(
        organization_id=ctx.org_id, inquiry_id=body.inquiry_id, customer_id=body.customer_id,
        number=next_number(ctx.db, Quotation, ctx.org_id, prefix="QTN"),
        status="DRAFT", currency=customer.currency, target_margin=q_ratio(body.target_margin),
        valid_until=body.valid_until, created_by=ctx.user_id)
    ctx.db.add(quotation)
    ctx.db.flush()
    _build_version(ctx, quotation, version_no=1, items_in=body.items, target_margin=body.target_margin)
    if inquiry and inquiry.status == "NEW":
        inquiry.status = "QUOTED"
    return quotation


def _build_version(ctx, quotation: Quotation, version_no: int, items_in, target_margin: Decimal):
    """Compute per-line cost/availability, totals, selling price from margin; persist estimate+items."""
    material_total = ZERO
    prepared = []
    for item in items_in:
        material = None
        if item.material_id:
            material = ctx.db.get(OrganizationMaterial, item.material_id)
            if material is None or material.organization_id != ctx.org_id:
                raise not_found("Material")
        unit_cost = _resolve_unit_cost(ctx, item.material_id, item.unit_cost)
        line_cost = q_money(unit_cost * item.quantity)
        availability = (material_availability(None, ctx.db, ctx.org_id, item.material_id)
                        if item.material_id else
                        {"available": ZERO, "on_hand": ZERO, "reserved": ZERO, "quality_held": ZERO})
        available = availability["available"]
        shortage = max(ZERO, q_qty(item.quantity - available))
        material_total += line_cost
        prepared.append((item, material, unit_cost, line_cost, available, shortage))

    subtotal, total_cost = cost_estimate_total(material=material_total)
    total_selling = selling_from_margin(total_cost, target_margin)
    if total_selling <= 0:
        raise bad_request("ZERO_SELLING_PRICE", "Selling price resolves to zero; enter item costs")

    estimate = CostEstimate(
        organization_id=ctx.org_id, context={"quotation_id": str(quotation.id)},
        status="DRAFT", material_cost=q_money(material_total), total_cost=total_cost,
        currency=quotation.currency, created_by=ctx.user_id)
    ctx.db.add(estimate)
    ctx.db.flush()

    version = QuotationVersion(
        organization_id=ctx.org_id, quotation_id=quotation.id, version_no=version_no,
        status="DRAFT", subtotal=subtotal, total_estimated_cost=total_cost,
        total_selling_price=total_selling,
        gross_margin_pct=gross_margin(total_selling, total_cost), cost_estimate_id=estimate.id)
    ctx.db.add(version)
    ctx.db.flush()

    for item, material, unit_cost, line_cost, available, shortage in prepared:
        line_selling = q_money(total_selling * (line_cost / total_cost)) if total_cost > 0 else ZERO
        unit_price = q_money(line_selling / item.quantity) if item.quantity > 0 else ZERO
        ctx.db.add(QuotationItem(
            organization_id=ctx.org_id, quotation_version_id=version.id,
            material_id=item.material_id, description=item.description, form=item.form,
            grade=item.grade, quantity=item.quantity, unit=item.unit, unit_cost=unit_cost,
            unit_price=unit_price, line_estimated_cost=line_cost, line_selling_price=line_selling,
            available_qty=available, shortage_qty=shortage))
        ctx.db.add(CostLine(
            organization_id=ctx.org_id, cost_estimate_id=estimate.id, category="MATERIAL",
            description=item.description, material_id=item.material_id, quantity=item.quantity,
            unit=item.unit, unit_cost=unit_cost, amount=line_cost,
            source={"basis": "wac_or_input"}))
    return version


def transition_quotation(ctx, quotation: Quotation, target: str, actor_role: str):
    allowed = QUOTATION_FLOW.get(quotation.status, set())
    if target not in allowed:
        raise conflict("INVALID_TRANSITION",
                       f"Cannot move quotation from {quotation.status} to {target}",
                       {"allowed": sorted(allowed)})
    quotation.status = target


def submit_for_approval(ctx, quotation: Quotation):
    transition_quotation(ctx, quotation, "PENDING_APPROVAL", ctx.role)
    version = _current_version(ctx, quotation)
    ctx.db.add(Approval(
        organization_id=ctx.org_id, entity_type="quotation", entity_id=quotation.id,
        approval_type="QUOTATION", requested_by=ctx.user_id, status="PENDING"))
    return version


def approve_quotation(ctx, quotation: Quotation, comment: str | None):
    transition_quotation(ctx, quotation, "APPROVED", ctx.role)
    version = _current_version(ctx, quotation)
    from datetime import datetime, timezone
    version.status = "APPROVED"
    version.approved_by = ctx.user_id
    version.approved_at = datetime.now(timezone.utc)
    version.is_immutable = True
    approval = ctx.db.scalar(select(Approval).where(
        Approval.entity_type == "quotation", Approval.entity_id == quotation.id,
        Approval.status == "PENDING").order_by(Approval.created_at.desc()))
    if approval:
        approval.status = "APPROVED"
        approval.decided_by = ctx.user_id
        approval.decided_at = datetime.now(timezone.utc)
        approval.comment = comment
    return version


def _current_version(ctx, quotation: Quotation) -> QuotationVersion:
    return ctx.db.scalar(select(QuotationVersion).where(
        QuotationVersion.quotation_id == quotation.id)
        .order_by(QuotationVersion.version_no.desc()).limit(1))


def convert_to_sales_order(ctx, quotation: Quotation) -> SalesOrder:
    existing = ctx.db.scalar(select(SalesOrder).where(SalesOrder.quotation_id == quotation.id))
    if existing:
        return existing  # idempotent conversion
    if quotation.status not in ("APPROVED", "ACCEPTED"):
        raise conflict("NOT_CONVERTIBLE",
                       f"Quotation must be APPROVED or ACCEPTED to convert (is {quotation.status})")
    version = _current_version(ctx, quotation)
    items = ctx.db.scalars(select(QuotationItem).where(
        QuotationItem.quotation_version_id == version.id)).all()
    so = SalesOrder(
        organization_id=ctx.org_id, quotation_id=quotation.id, customer_id=quotation.customer_id,
        number=next_number(ctx.db, SalesOrder, ctx.org_id, prefix="SO"),
        status="CONFIRMED", total_value=version.total_selling_price,
        delivery_date=quotation.valid_until)
    ctx.db.add(so)
    ctx.db.flush()
    for it in items:
        ctx.db.add(SalesOrderItem(
            organization_id=ctx.org_id, sales_order_id=so.id, material_id=it.material_id,
            description=it.description, quantity=it.quantity, unit=it.unit,
            unit_price=it.unit_price))
    quotation.status = "CONVERTED"
    if quotation.inquiry_id:
        inquiry = ctx.db.get(CustomerInquiry, quotation.inquiry_id)
        if inquiry and inquiry.status in ("NEW", "QUOTED"):
            inquiry.status = "WON"
    return so
