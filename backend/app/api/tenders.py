import os
import uuid as uuid_mod
from io import BytesIO
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.ai.extraction import detect_injection_warnings, extract_text_pages, parse_boq_lines
from app.config import get_settings
from app.core.deps import TenantContext, require
from app.core.errors import bad_request, conflict, not_found
from app.core.pagination import Page, PageParams, paginate
from app.models.materials import OrganizationMaterial
from app.models.inventory import StockLot
from app.models.procurement import RFQ, Supplier, SupplierQuote
from app.models.ops import AIJob, CostEstimate, CostLine
from app.models.projects import (BOQItem, ExtractionEvidence, Project, Tender, TenderDocument, TenderRequirementSnapshot, TenderSupplierSelection, TenderWorkflow)
from app.models.fabrication import BOMItem, BOMVersion
from app.models.crm import Customer
from app.models.sales import QuotationVersion
from app.schemas.projects import (BOQItemIn, BOQItemOut, BOQReviewIn, EvidenceOut,
                                  TenderDocumentOut, TenderIn, TenderOut, TenderStatusIn,
                                  TenderUpdate, TenderSupplierSelectionIn, TenderSupplierSelectionCancelIn)
from app.services.audit import record_audit
from app.services.tender_costing import compatible_offer
from app.services.quotations import create_quotation
from app.schemas.sales import QuotationCreateIn, QuotationItemIn
from app.calc.finance import ZERO, cost_estimate_total, q_money, q_qty

router = APIRouter(prefix="/tenders", tags=["tenders"])
settings = get_settings()

TENDER_FLOW = {
    "DRAFT": {"IN_REVIEW", "CANCELLED"},
    "IN_REVIEW": {"ESTIMATING", "CANCELLED"},
    "ESTIMATING": {"BID_SUBMITTED", "CANCELLED"},
    "BID_SUBMITTED": {"WON", "LOST"},
    "WON": set(), "LOST": set(), "CANCELLED": set(),
}


class DemoRateIn(BaseModel):
    tender_requirement_snapshot_id: UUID
    unit_rate: Decimal = Field(gt=0)


class WorkflowEstimateIn(BaseModel):
    demo_rates: list[DemoRateIn] = Field(min_length=1)
    processing_cost: Decimal = Field(default=Decimal("0"), ge=0)
    freight_cost: Decimal = Field(default=Decimal("0"), ge=0)
    testing_cost: Decimal = Field(default=Decimal("0"), ge=0)
    overhead_cost: Decimal = Field(default=Decimal("0"), ge=0)
    contingency_pct: Decimal = Field(default=Decimal("0"), ge=0, lt=1)


class WorkflowCustomerIn(BaseModel):
    customer_id: UUID


class WorkflowQuotationIn(BaseModel):
    target_margin: Decimal = Field(default=Decimal("0.12"), ge=0, lt=1)


class WorkflowSubmissionIn(BaseModel):
    status: str = Field(pattern="^(READY|MANUALLY_SUBMITTED|NOT_SUBMITTED)$")
    external_submission_reference: str | None = Field(default=None, max_length=128)
    submission_notes: str | None = Field(default=None, max_length=2000)


def _workflow(ctx: TenantContext, tender_id: UUID, *, create: bool = False) -> TenderWorkflow | None:
    row = ctx.db.scalar(select(TenderWorkflow).where(
        TenderWorkflow.organization_id == ctx.org_id, TenderWorkflow.tender_id == tender_id))
    if row is None and create:
        now = datetime.now(timezone.utc)
        row = TenderWorkflow(organization_id=ctx.org_id, tender_id=tender_id,
                             created_at=now, updated_at=now)
        ctx.db.add(row)
        ctx.db.flush()
    return row


def _workflow_out(ctx: TenantContext, workflow: TenderWorkflow) -> dict:
    shortages = []
    if workflow.bom_version_id:
        for item in ctx.db.scalars(select(BOMItem).where(BOMItem.bom_version_id == workflow.bom_version_id)).all():
            available = Decimal(str(ctx.db.scalar(select(func.coalesce(func.sum(
                StockLot.on_hand_qty - StockLot.reserved_qty), 0)).where(
                StockLot.organization_id == ctx.org_id, StockLot.material_id == item.material_id,
                StockLot.quality_status == "OK")) or 0))
            shortages.append({"bom_item_id": str(item.id), "snapshot_id": str(item.tender_requirement_snapshot_id) if item.tender_requirement_snapshot_id else None,
                              "material_id": str(item.material_id), "required_quantity": str(item.quantity),
                              "available_quantity": str(available), "shortage_quantity": str(max(ZERO, item.quantity - available)), "unit": item.unit})
    return {"id": str(workflow.id), "tender_id": str(workflow.tender_id),
            "requirement_snapshot_version": workflow.requirement_snapshot_version,
            "bom_version_id": str(workflow.bom_version_id) if workflow.bom_version_id else None,
            "cost_estimate_id": str(workflow.cost_estimate_id) if workflow.cost_estimate_id else None,
            "quotation_id": str(workflow.quotation_id) if workflow.quotation_id else None,
            "customer_id": str(workflow.customer_id) if workflow.customer_id else None,
            "use_demo_commercial_rates": workflow.use_demo_commercial_rates,
            "submission_status": workflow.submission_status,
            "external_submission_reference": workflow.external_submission_reference,
            "submission_notes": workflow.submission_notes, "shortages": shortages}


@router.post("/{tender_id}/requirement-snapshots", status_code=201)
def snapshot_confirmed_requirements(tender_id: UUID, ctx: TenantContext = Depends(require("tenders:write"))):
    """Freeze only confirmed, mapped BOQ lines for commercial costing."""
    _get_tender(ctx, tender_id)
    rows = ctx.db.scalars(select(BOQItem).where(BOQItem.tender_id == tender_id,
        BOQItem.organization_id == ctx.org_id, BOQItem.review_status == "CONFIRMED",
        BOQItem.material_id.isnot(None), BOQItem.quantity.isnot(None), BOQItem.unit.isnot(None))).all()
    if not rows:
        raise bad_request("NO_APPROVED_REQUIREMENTS", "Confirm mapped BOQ requirements before snapshotting")
    version = (ctx.db.scalar(select(func.max(TenderRequirementSnapshot.version)).where(
        TenderRequirementSnapshot.tender_id == tender_id)) or 0) + 1
    now = datetime.now(timezone.utc)
    for boq in rows:
        ctx.db.add(TenderRequirementSnapshot(organization_id=ctx.org_id, tender_id=tender_id,
            source_boq_item_id=boq.id, version=version, material_id=boq.material_id,
            form=boq.form, grade=boq.grade, specification=boq.specification,
            quantity=boq.quantity, unit=boq.unit, approved_at=now,
            # Older databases have NOT NULL timestamp columns without server defaults.
            created_at=now, updated_at=now))
    ctx.db.flush()
    record_audit(ctx, "tender.requirements_snapshot", "tender", tender_id,
                 {"after": {"version": version, "lines": len(rows)}})
    ctx.db.commit()
    return {"tender_id": str(tender_id), "version": version, "lines": len(rows), "status": "APPROVED_REQUIREMENTS"}


@router.get("/{tender_id}/requirement-snapshots")
def list_requirement_snapshots(tender_id: UUID, ctx: TenantContext = Depends(require("read"))):
    _get_tender(ctx, tender_id)
    rows = ctx.db.scalars(select(TenderRequirementSnapshot).where(
        TenderRequirementSnapshot.tender_id == tender_id,
        TenderRequirementSnapshot.organization_id == ctx.org_id).order_by(
        TenderRequirementSnapshot.version.desc(), TenderRequirementSnapshot.created_at.desc())).all()
    return [{"id": str(r.id), "version": r.version, "material_id": str(r.material_id),
             "form": r.form, "grade": r.grade, "specification": r.specification,
             "quantity": str(r.quantity), "unit": r.unit, "wastage_pct": str(r.wastage_pct),
             "engineering_status": r.engineering_status, "approved_at": r.approved_at.isoformat()} for r in rows]


@router.get("/{tender_id}/workflow")
def get_workflow(tender_id: UUID, ctx: TenantContext = Depends(require("read"))):
    _get_tender(ctx, tender_id)
    workflow = _workflow(ctx, tender_id)
    return _workflow_out(ctx, workflow) if workflow else {"tender_id": str(tender_id), "status": "NOT_STARTED", "shortages": []}


@router.post("/{tender_id}/workflow/bom", status_code=201)
def generate_workflow_bom(tender_id: UUID, ctx: TenantContext = Depends(require("fabrication:write"))):
    """Create one traceable BOM from the latest approved requirement snapshot."""
    tender = _get_tender(ctx, tender_id)
    workflow = _workflow(ctx, tender_id, create=True)
    if workflow.bom_version_id:
        return _workflow_out(ctx, workflow)
    version = ctx.db.scalar(select(func.max(TenderRequirementSnapshot.version)).where(
        TenderRequirementSnapshot.organization_id == ctx.org_id,
        TenderRequirementSnapshot.tender_id == tender_id))
    if version is None:
        raise bad_request("MISSING_REQUIREMENT_SNAPSHOT", "Approve and snapshot BOQ requirements before generating a BOM")
    snapshots = ctx.db.scalars(select(TenderRequirementSnapshot).where(
        TenderRequirementSnapshot.organization_id == ctx.org_id,
        TenderRequirementSnapshot.tender_id == tender_id,
        TenderRequirementSnapshot.version == version).order_by(TenderRequirementSnapshot.created_at)).all()
    if not snapshots:
        raise bad_request("MISSING_REQUIREMENT_SNAPSHOT", "No approved requirement snapshots were found")
    bom = BOMVersion(organization_id=ctx.org_id, tender_id=tender_id,
                     requirement_snapshot_version=version,
                     bom_code=f"TND-{tender.number}-BOM", product_name=tender.title,
                     version_no=1, status="DRAFT")
    ctx.db.add(bom)
    ctx.db.flush()
    for req in snapshots:
        material = ctx.db.get(OrganizationMaterial, req.material_id)
        if material is None or material.organization_id != ctx.org_id:
            raise bad_request("UNRESOLVED_MATERIAL", f"Snapshot {req.id} is not mapped to a tenant material")
        quantity = q_qty(req.quantity * (Decimal("1") + req.wastage_pct))
        ctx.db.add(BOMItem(organization_id=ctx.org_id, bom_version_id=bom.id,
                           tender_requirement_snapshot_id=req.id, material_id=req.material_id,
                           quantity=quantity, unit=req.unit, theoretical_waste_pct=req.wastage_pct,
                           notes=f"Tender BOQ line {req.source_boq_item_id}; snapshot v{version}"))
    workflow.requirement_snapshot_version = version
    workflow.bom_version_id = bom.id
    record_audit(ctx, "tender.workflow.bom", "tender_workflow", workflow.id,
                 {"after": {"bom_version_id": str(bom.id), "snapshot_version": version}})
    ctx.db.commit()
    return _workflow_out(ctx, workflow)


@router.post("/{tender_id}/workflow/customer")
def select_workflow_customer(tender_id: UUID, body: WorkflowCustomerIn,
                             ctx: TenantContext = Depends(require("quotations:write"))):
    _get_tender(ctx, tender_id)
    customer = ctx.db.scalar(select(Customer).where(Customer.id == body.customer_id,
                                                     Customer.organization_id == ctx.org_id,
                                                     Customer.is_active.is_(True)))
    if customer is None:
        raise not_found("Active customer")
    workflow = _workflow(ctx, tender_id, create=True)
    workflow.customer_id = customer.id
    record_audit(ctx, "tender.workflow.customer", "tender_workflow", workflow.id,
                 {"after": {"customer_id": str(customer.id)}})
    ctx.db.commit()
    return _workflow_out(ctx, workflow)


@router.post("/{tender_id}/workflow/estimate", status_code=201)
def create_workflow_estimate(tender_id: UUID, body: WorkflowEstimateIn,
                             ctx: TenantContext = Depends(require("quotations:write"))):
    """Persist a draft estimate using explicitly-labelled demonstration commercial rates only."""
    _get_tender(ctx, tender_id)
    workflow = _workflow(ctx, tender_id, create=True)
    if workflow.cost_estimate_id:
        return _workflow_out(ctx, workflow)
    if not workflow.bom_version_id:
        raise bad_request("MISSING_BOM", "Generate the tender BOM before creating an estimate")
    rates = {r.tender_requirement_snapshot_id: r.unit_rate for r in body.demo_rates}
    items = ctx.db.scalars(select(BOMItem).where(BOMItem.bom_version_id == workflow.bom_version_id)).all()
    missing = [str(i.tender_requirement_snapshot_id) for i in items if i.tender_requirement_snapshot_id not in rates]
    if missing:
        raise bad_request("MISSING_COMMERCIAL_RATES", "Provide a demo commercial rate for every BOM requirement", {"snapshot_ids": missing})
    estimate = CostEstimate(organization_id=ctx.org_id, tender_id=tender_id, status="DRAFT",
                            context={"tender_workflow_id": str(workflow.id), "rate_basis": "DEMO_COMMERCIAL_RATE", "approval_required": True},
                            overhead_cost=q_money(body.overhead_cost), contingency_pct=body.contingency_pct,
                            currency=ctx.organization.currency_code, created_by=ctx.user_id)
    ctx.db.add(estimate)
    ctx.db.flush()
    material_total = ZERO
    for item in items:
        rate = rates[item.tender_requirement_snapshot_id]
        amount = q_money(item.quantity * rate)
        material_total += amount
        ctx.db.add(CostLine(organization_id=ctx.org_id, cost_estimate_id=estimate.id, category="MATERIAL",
                            description=f"Demo commercial rate for BOM item {item.id}", material_id=item.material_id,
                            quantity=item.quantity, unit=item.unit, unit_cost=rate, amount=amount,
                            source={"kind": "DEMO_COMMERCIAL_RATE", "tender_requirement_snapshot_id": str(item.tender_requirement_snapshot_id), "approved_supplier_quote": False}))
    extras = (("FABRICATION", "Processing", body.processing_cost), ("FREIGHT", "Freight", body.freight_cost),
              ("SUBCONTRACTING", "Testing", body.testing_cost))
    for category, description, amount in extras:
        if amount:
            ctx.db.add(CostLine(organization_id=ctx.org_id, cost_estimate_id=estimate.id, category=category,
                                description=description, amount=q_money(amount), source={"kind": "DEMO_COMMERCIAL_RATE"}))
    subtotal, total = cost_estimate_total(material=material_total, fabrication=body.processing_cost,
                                          freight=body.freight_cost, subcontracting=body.testing_cost,
                                          overhead=body.overhead_cost, contingency_pct=body.contingency_pct)
    estimate.material_cost = q_money(material_total); estimate.fabrication_cost = q_money(body.processing_cost)
    estimate.freight_cost = q_money(body.freight_cost); estimate.subcontracting_cost = q_money(body.testing_cost)
    estimate.contingency_amount = q_money(total - subtotal); estimate.total_cost = total
    workflow.cost_estimate_id = estimate.id; workflow.use_demo_commercial_rates = True
    record_audit(ctx, "tender.workflow.estimate", "tender_workflow", workflow.id,
                 {"after": {"cost_estimate_id": str(estimate.id), "total_cost": str(total), "demo_rates": True}})
    ctx.db.commit()
    return _workflow_out(ctx, workflow)


@router.post("/{tender_id}/workflow/quotation", status_code=201)
def create_workflow_quotation(tender_id: UUID, body: WorkflowQuotationIn,
                              ctx: TenantContext = Depends(require("quotations:write"))):
    _get_tender(ctx, tender_id)
    workflow = _workflow(ctx, tender_id)
    if workflow is None or not workflow.bom_version_id or not workflow.cost_estimate_id:
        raise bad_request("MISSING_ESTIMATE", "Generate the tender BOM and estimate before quotation")
    if workflow.quotation_id:
        return _workflow_out(ctx, workflow)
    if workflow.customer_id is None:
        raise bad_request("MISSING_CUSTOMER", "Select an existing authorized customer before generating a quotation")
    estimate = ctx.db.scalar(select(CostEstimate).where(CostEstimate.id == workflow.cost_estimate_id,
        CostEstimate.organization_id == ctx.org_id))
    if estimate is None: raise not_found("Cost estimate")
    items = ctx.db.scalars(select(BOMItem).where(BOMItem.bom_version_id == workflow.bom_version_id)).all()
    material_total = sum((i.quantity for i in items), ZERO)
    if material_total <= 0: raise bad_request("EMPTY_BOM", "Cannot quote an empty BOM")
    # Allocate non-material costs proportionally so the existing quotation service produces the persisted estimate total.
    rate_by_snapshot = {line.source.get("tender_requirement_snapshot_id"): line.unit_cost for line in ctx.db.scalars(
        select(CostLine).where(CostLine.cost_estimate_id == estimate.id, CostLine.category == "MATERIAL")).all()}
    base_cost = sum((i.quantity * Decimal(str(rate_by_snapshot.get(str(i.tender_requirement_snapshot_id), 0))) for i in items), ZERO)
    uplift = (estimate.total_cost / base_cost) if base_cost > 0 else Decimal("1")
    quote_items = [QuotationItemIn(material_id=i.material_id, description=f"Tender BOM item {i.id}", quantity=i.quantity,
                                   unit=i.unit, unit_cost=q_money(Decimal(str(rate_by_snapshot[str(i.tender_requirement_snapshot_id)])) * uplift)) for i in items]
    quotation = create_quotation(ctx, QuotationCreateIn(customer_id=workflow.customer_id,
        target_margin=body.target_margin, items=quote_items))
    quotation.tender_id = tender_id
    version = ctx.db.scalar(select(QuotationVersion).where(QuotationVersion.quotation_id == quotation.id,
        QuotationVersion.version_no == 1))
    if version: version.cost_estimate_id = estimate.id
    workflow.quotation_id = quotation.id
    workflow.submission_status = "READY"
    record_audit(ctx, "tender.workflow.quotation", "tender_workflow", workflow.id,
                 {"after": {"quotation_id": str(quotation.id), "customer_id": str(workflow.customer_id)}})
    ctx.db.commit()
    return _workflow_out(ctx, workflow)


@router.post("/{tender_id}/workflow/submission")
def update_workflow_submission(tender_id: UUID, body: WorkflowSubmissionIn,
                               ctx: TenantContext = Depends(require("tenders:write"))):
    _get_tender(ctx, tender_id)
    workflow = _workflow(ctx, tender_id)
    if workflow is None or not workflow.quotation_id:
        raise bad_request("QUOTATION_REQUIRED", "Generate a quotation before tracking submission")
    if body.status == "MANUALLY_SUBMITTED" and not body.external_submission_reference:
        raise bad_request("SUBMISSION_REFERENCE_REQUIRED", "Record the external submission reference before marking submitted")
    workflow.submission_status = body.status
    workflow.external_submission_reference = body.external_submission_reference
    workflow.submission_notes = body.submission_notes
    workflow.external_submitted_at = datetime.now(timezone.utc) if body.status == "MANUALLY_SUBMITTED" else None
    record_audit(ctx, "tender.workflow.submission", "tender_workflow", workflow.id,
                 {"after": {"status": body.status, "reference": body.external_submission_reference}})
    ctx.db.commit()
    return _workflow_out(ctx, workflow)


def _xlsx_download(filename: str, columns: list[str], rows: list[list[object]]) -> Response:
    from openpyxl import Workbook
    book = Workbook(); sheet = book.active; sheet.title = "SteelBid export"
    sheet.append(columns)
    for row in rows: sheet.append([str(value) if value is not None else "" for value in row])
    for cell in sheet[1]: cell.font = cell.font.copy(bold=True)
    for column in sheet.columns:
        sheet.column_dimensions[column[0].column_letter].width = min(60, max(12, max(len(str(c.value or "")) for c in column) + 2))
    stream = BytesIO(); book.save(stream)
    return Response(stream.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/{tender_id}/workflow/boq.xlsx")
def export_workflow_boq(tender_id: UUID, ctx: TenantContext = Depends(require("read"))):
    _get_tender(ctx, tender_id)
    rows = ctx.db.scalars(select(BOQItem).where(BOQItem.tender_id == tender_id,
        BOQItem.organization_id == ctx.org_id).order_by(BOQItem.created_at)).all()
    return _xlsx_download(f"BOQ-{tender_id}.xlsx", ["Line", "Description", "Form", "Grade", "Quantity", "Unit", "Review", "Source page"],
                          [[r.line_no, r.raw_description, r.form, r.grade, r.quantity, r.unit, r.review_status, r.page_ref] for r in rows])


@router.get("/{tender_id}/workflow/bom.xlsx")
def export_workflow_bom(tender_id: UUID, ctx: TenantContext = Depends(require("read"))):
    _get_tender(ctx, tender_id)
    workflow = _workflow(ctx, tender_id)
    if workflow is None or workflow.bom_version_id is None: raise bad_request("MISSING_BOM", "Generate the tender BOM before exporting")
    rows = ctx.db.scalars(select(BOMItem).where(BOMItem.bom_version_id == workflow.bom_version_id)).all()
    tender = _get_tender(ctx, tender_id)
    export_rows = []
    for r in rows:
        material = ctx.db.get(OrganizationMaterial, r.material_id)
        export_rows.append([material.name if material else str(r.material_id), material.form if material else "", material.grade if material else "", r.tender_requirement_snapshot_id, r.quantity, r.unit, r.theoretical_waste_pct, r.notes])
    return _xlsx_download(f"BOM-{tender.number}.xlsx", ["Material", "Form", "Grade", "Requirement snapshot", "Quantity", "Unit", "Wastage %", "BOQ trace"], export_rows)


@router.get("/{tender_id}/workflow/estimate.xlsx")
def export_workflow_estimate(tender_id: UUID, ctx: TenantContext = Depends(require("read"))):
    _get_tender(ctx, tender_id)
    workflow = _workflow(ctx, tender_id)
    if workflow is None or workflow.cost_estimate_id is None: raise bad_request("MISSING_ESTIMATE", "Create the tender estimate before exporting")
    estimate = ctx.db.scalar(select(CostEstimate).where(CostEstimate.id == workflow.cost_estimate_id,
        CostEstimate.organization_id == ctx.org_id))
    if estimate is None: raise not_found("Cost estimate")
    lines = ctx.db.scalars(select(CostLine).where(CostLine.cost_estimate_id == estimate.id)).all()
    rows = [[line.category, line.description, line.quantity, line.unit, line.unit_cost, line.amount] for line in lines]
    rows.append(["TOTAL", "Tender estimate", "", "", "", estimate.total_cost])
    return _xlsx_download(f"Estimate-{tender_id}.xlsx", ["Category", "Description", "Quantity", "Unit", "Unit cost", "Amount"], rows)


@router.get("/{tender_id}/workflow/quotation.pdf")
def export_workflow_quotation_pdf(tender_id: UUID, ctx: TenantContext = Depends(require("read"))):
    tender = _get_tender(ctx, tender_id)
    workflow = _workflow(ctx, tender_id)
    if workflow is None or workflow.quotation_id is None: raise bad_request("MISSING_QUOTATION", "Generate the tender quotation before exporting")
    from app.models.sales import Quotation, QuotationItem
    quotation = ctx.db.scalar(select(Quotation).where(Quotation.id == workflow.quotation_id,
        Quotation.organization_id == ctx.org_id))
    version = ctx.db.scalar(select(QuotationVersion).where(QuotationVersion.quotation_id == workflow.quotation_id).order_by(QuotationVersion.version_no.desc()))
    if quotation is None or version is None: raise not_found("Quotation")
    customer = ctx.db.get(Customer, quotation.customer_id)
    items = ctx.db.scalars(select(QuotationItem).where(QuotationItem.quotation_version_id == version.id)).all()
    import fitz
    document = fitz.open(); page = document.new_page(); y = 48
    def write(text: str, size: int = 10, bold: bool = False):
        nonlocal y, page
        if y > 780: page = document.new_page(); y = 48
        page.insert_text((48, y), text, fontsize=size, fontname="hebo" if bold else "helv"); y += size + 8
    write(ctx.organization.name, 16, True); write(f"Quotation {quotation.number}", 18, True); write(f"Tender: {tender.number} — {tender.title}")
    write(f"Customer: {customer.name if customer else 'Not recorded'}"); write("DEMONSTRATION COMMERCIAL RATES — NOT APPROVED SUPPLIER QUOTATIONS" if workflow.use_demo_commercial_rates else "Commercial rate basis: authorised inputs")
    if tender.is_demo: write("SIMULATED TRAINING DATA — NOT AN OFFICIAL GOVERNMENT TENDER OR SUPPLIER QUOTE.", 9, True)
    y += 8; write("Description | Quantity | Unit | Unit price | Amount", 10, True)
    for item in items: write(f"{item.description[:42]} | {item.quantity} | {item.unit} | {item.unit_price} | {item.line_selling_price}")
    y += 6; write(f"Total quotation amount: INR {version.total_selling_price}", 12, True)
    payload = document.tobytes(); document.close()
    return Response(payload, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="Quotation-{quotation.number}.pdf"'})


def _report_pdf(ctx: TenantContext, tender: Tender, report_name: str, lines: list[str]) -> Response:
    """Tenant-scoped PDF renderer used by workflow reports; never returns HTML."""
    import fitz
    document = fitz.open(); page = document.new_page(); y = 48
    def write(text: str, size: int = 10, bold: bool = False):
        nonlocal page, y
        if y > 780:
            page = document.new_page(); y = 48
        page.insert_text((44, y), text[:145], fontsize=size, fontname="hebo" if bold else "helv"); y += size + 8
    write(ctx.organization.name, 16, True); write(report_name, 14, True)
    write(f"Tender: {tender.number} — {tender.title}")
    write(f"Generated: {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')}")
    write(f"Source classification: {tender.data_classification} / {tender.source_type}")
    if tender.is_demo:
        write("SIMULATED TRAINING DATA — NOT AN OFFICIAL GOVERNMENT TENDER OR SUPPLIER QUOTE.", 9, True)
    y += 6
    for line in lines: write(line)
    for pno, p in enumerate(document, 1):
        p.insert_text((44, 815), f"SteelBid AI · {report_name} · Page {pno}", fontsize=8)
    payload = document.tobytes(); document.close()
    slug = report_name.lower().replace(" ", "-").replace("&", "and")
    return Response(payload, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{slug}-{tender.number}.pdf"'})


@router.get("/{tender_id}/reports/analysis.pdf")
def report_analysis(tender_id: UUID, ctx: TenantContext = Depends(require("read"))):
    tender = _get_tender(ctx, tender_id); workflow = _workflow(ctx, tender_id)
    boq = ctx.db.scalars(select(BOQItem).where(BOQItem.tender_id == tender_id, BOQItem.organization_id == ctx.org_id)).all()
    lines = [f"Submission deadline: {tender.submission_deadline or 'Not recorded'}", f"BOQ review: {sum(x.review_status == 'CONFIRMED' for x in boq)}/{len(boq)} confirmed", f"BOM: {'Generated' if workflow and workflow.bom_version_id else 'Pending'}"]
    lines += [f"{x.raw_description} | {x.grade or '—'} | {x.quantity or '—'} {x.unit or ''} | {x.review_status}" for x in boq]
    return _report_pdf(ctx, tender, "Tender Analysis Report", lines)


@router.get("/{tender_id}/reports/boq.pdf")
def report_boq(tender_id: UUID, ctx: TenantContext = Depends(require("read"))):
    tender = _get_tender(ctx, tender_id)
    rows = ctx.db.scalars(select(BOQItem).where(BOQItem.tender_id == tender_id, BOQItem.organization_id == ctx.org_id).order_by(BOQItem.created_at)).all()
    return _report_pdf(ctx, tender, "BOQ Report", [f"{r.line_no or '—'} | {r.raw_description} | Grade {r.grade or '—'} | {r.quantity or '—'} {r.unit or ''} | {r.review_status}" for r in rows])


@router.get("/{tender_id}/reports/bom.pdf")
def report_bom(tender_id: UUID, ctx: TenantContext = Depends(require("read"))):
    tender = _get_tender(ctx, tender_id); workflow = _workflow(ctx, tender_id)
    if not workflow or not workflow.bom_version_id: raise bad_request("MISSING_BOM", "Generate the tender BOM before exporting")
    rows = ctx.db.scalars(select(BOMItem).where(BOMItem.bom_version_id == workflow.bom_version_id)).all()
    lines = []
    for r in rows:
        material = ctx.db.get(OrganizationMaterial, r.material_id)
        lines.append(f"{material.name if material else r.material_id} | {material.form if material else 'Unknown'} | Grade {material.grade if material else 'Unknown'} | {r.quantity} {r.unit} | source BOQ {r.tender_requirement_snapshot_id}")
    return _report_pdf(ctx, tender, "BOM Report", lines)


@router.get("/{tender_id}/reports/inventory.pdf")
def report_inventory(tender_id: UUID, ctx: TenantContext = Depends(require("read"))):
    tender = _get_tender(ctx, tender_id); workflow = _workflow(ctx, tender_id)
    if not workflow or not workflow.bom_version_id: raise bad_request("MISSING_BOM", "Generate the tender BOM before exporting")
    rows = ctx.db.scalars(select(BOMItem).where(BOMItem.bom_version_id == workflow.bom_version_id)).all(); lines=[]
    for r in rows:
        available = ctx.db.scalar(select(func.coalesce(func.sum(StockLot.on_hand_qty - StockLot.reserved_qty), 0)).where(StockLot.organization_id == ctx.org_id, StockLot.material_id == r.material_id, StockLot.quality_status == "OK")) or ZERO
        covered=min(Decimal(str(r.quantity)), Decimal(str(available))); material = ctx.db.get(OrganizationMaterial, r.material_id)
        lines.append(f"{material.name if material else r.material_id} | Grade {material.grade if material else 'Unknown'} | required {r.quantity} {r.unit} | eligible {available} {r.unit} | shortage {Decimal(str(r.quantity))-covered} {r.unit}")
    return _report_pdf(ctx, tender, "Inventory and Shortage Report", lines)


@router.get("/{tender_id}/reports/estimate.pdf")
def report_estimate(tender_id: UUID, ctx: TenantContext = Depends(require("read"))):
    tender = _get_tender(ctx, tender_id); workflow = _workflow(ctx, tender_id)
    if not workflow or not workflow.cost_estimate_id: raise bad_request("MISSING_ESTIMATE", "Create the tender estimate before exporting")
    estimate = ctx.db.scalar(select(CostEstimate).where(CostEstimate.id == workflow.cost_estimate_id, CostEstimate.organization_id == ctx.org_id))
    if estimate is None: raise not_found("Cost estimate")
    rows = ctx.db.scalars(select(CostLine).where(CostLine.cost_estimate_id == estimate.id)).all()
    lines = [f"{row.category} | {row.description} | {row.quantity or ''} {row.unit or ''} | INR {row.amount}" for row in rows]
    lines.append(f"TOTAL ESTIMATED COST | INR {estimate.total_cost}")
    return _report_pdf(ctx, tender, "Detailed Cost Estimate", lines)


@router.get("/{tender_id}/reports/supplier-comparison.pdf")
def report_supplier_comparison(tender_id: UUID, ctx: TenantContext = Depends(require("read"))):
    tender = _get_tender(ctx, tender_id)
    snapshots = ctx.db.scalars(select(TenderRequirementSnapshot).where(
        TenderRequirementSnapshot.tender_id == tender_id, TenderRequirementSnapshot.organization_id == ctx.org_id)).all()
    # Approved requirement snapshots are the tender provenance boundary: do
    # not infer or include any offer for a material outside this tender.
    material_ids = list({x.material_id for x in snapshots})
    quotes = ctx.db.scalars(select(SupplierQuote).where(SupplierQuote.organization_id == ctx.org_id,
        SupplierQuote.material_id.in_(material_ids))).all() if material_ids else []
    requirements = {x.material_id: x for x in snapshots}
    lines = ["Comparison basis: persisted supplier offers matching approved tender requirement materials.",
             "Data provenance: supplier_quotes, rfqs, suppliers and tender_requirement_snapshots (tenant scoped)."]
    if not quotes:
        lines += ["Comparison status: NO OFFERS RECORDED.",
                  "No persisted supplier offers are available for this tender's approved requirements; no quotation has been inferred."]
    for quote in quotes:
        supplier = ctx.db.get(Supplier, quote.supplier_id); rfq = ctx.db.get(RFQ, quote.rfq_id) if quote.rfq_id else None
        material = ctx.db.get(OrganizationMaterial, quote.material_id)
        total = Decimal(str(quote.quantity)) * Decimal(str(quote.unit_price))
        requirement = requirements.get(quote.material_id)
        delivery = f"lead {quote.lead_time_days} days; payment {quote.payment_terms_days} days"
        lines.append(f"Supplier: {supplier.name if supplier else 'Supplier unavailable'} | RFQ: {rfq.number if rfq else 'Not linked'} | comparison status: {quote.status}")
        lines.append(f"Material: {material.name if material else quote.material_id} | form {material.form if material else 'Unknown'} | grade {material.grade if material else 'Unknown'} | tender requirement {requirement.quantity if requirement else 'Unknown'} {requirement.unit if requirement else ''}")
        lines.append(f"Offer: {quote.quantity} {quote.unit} at {quote.currency} {quote.unit_price}/{quote.unit} | total offer value {quote.currency} {total} | delivery terms: {delivery} | valid until {quote.valid_until or 'Not recorded'}")
        lines.append("Data provenance: persisted training supplier offer." if tender.is_demo else "Data provenance: persisted supplier offer.")
    return _report_pdf(ctx, tender, "Supplier Comparison Report", lines)


@router.get("/{tender_id}/requirement-snapshots/{snapshot_id}/supplier-offers")
def compatible_supplier_offers(tender_id: UUID, snapshot_id: UUID, ctx: TenantContext = Depends(require("read"))):
    _get_tender(ctx, tender_id)
    req = ctx.db.scalar(select(TenderRequirementSnapshot).where(TenderRequirementSnapshot.id == snapshot_id, TenderRequirementSnapshot.tender_id == tender_id, TenderRequirementSnapshot.organization_id == ctx.org_id))
    if req is None: raise not_found("Tender requirement snapshot")
    eligible = Decimal(str(ctx.db.scalar(select(func.coalesce(func.sum(StockLot.on_hand_qty - StockLot.reserved_qty), 0)).where(StockLot.organization_id == ctx.org_id, StockLot.material_id == req.material_id, StockLot.quality_status == "OK")) or 0))
    items = []
    for quote in ctx.db.scalars(select(SupplierQuote).where(SupplierQuote.organization_id == ctx.org_id, SupplierQuote.material_id == req.material_id)).all():
        result = compatible_offer(req, ctx.db.get(OrganizationMaterial, req.material_id), quote, ctx.db.get(OrganizationMaterial, quote.material_id), eligible)
        supplier = ctx.db.get(Supplier, quote.supplier_id)
        item = {"supplier_quote_id": str(quote.id), "supplier_name": supplier.name if supplier else None, "quantity": str(quote.quantity), "unit": quote.unit, "unit_price": str(quote.unit_price), "freight_per_unit": str(quote.freight_per_unit), "tax_recoverable": quote.tax_recoverable, "tax_pct": str(quote.tax_pct), "valid_until": str(quote.valid_until) if quote.valid_until else None, **{k: str(v) if isinstance(v, Decimal) else v for k, v in result.items()}}
        item["total_landed_cost"] = str(result["landed_cost_per_unit"] * quote.quantity)
        items.append(item)
    return {"snapshot_id": str(snapshot_id), "items": items}


@router.get("/{tender_id}/supplier-selections")
def list_supplier_selections(tender_id: UUID, ctx: TenantContext = Depends(require("read"))):
    _get_tender(ctx, tender_id)
    rows = ctx.db.scalars(select(TenderSupplierSelection).where(TenderSupplierSelection.tender_id == tender_id, TenderSupplierSelection.organization_id == ctx.org_id).order_by(TenderSupplierSelection.created_at)).all()
    return [{"id": str(x.id), "snapshot_id": str(x.tender_requirement_snapshot_id), "supplier_quote_id": str(x.supplier_quote_id), "selected_qty": str(x.selected_qty), "unit": x.unit, "landed_cost_per_unit": str(x.landed_cost_per_unit), "total_landed_cost": str(x.selected_qty * x.landed_cost_per_unit), "valid_until": str(x.valid_until) if x.valid_until else None, "delivery_terms": x.delivery_terms, "status": x.status, "created_at": x.created_at.isoformat()} for x in rows]


@router.post("/{tender_id}/requirement-snapshots/{snapshot_id}/supplier-selections", status_code=201)
def create_supplier_selection(tender_id: UUID, snapshot_id: UUID, body: TenderSupplierSelectionIn, ctx: TenantContext = Depends(require("procurement:write"))):
    _get_tender(ctx, tender_id)
    req = ctx.db.scalar(select(TenderRequirementSnapshot).where(TenderRequirementSnapshot.id == snapshot_id, TenderRequirementSnapshot.tender_id == tender_id, TenderRequirementSnapshot.organization_id == ctx.org_id).with_for_update())
    if req is None: raise not_found("Tender requirement snapshot")
    quote = ctx.db.scalar(select(SupplierQuote).where(SupplierQuote.id == body.supplier_quote_id, SupplierQuote.organization_id == ctx.org_id))
    if quote is None: raise not_found("Supplier quote")
    eligible = Decimal(str(ctx.db.scalar(select(func.coalesce(func.sum(StockLot.on_hand_qty - StockLot.reserved_qty), 0)).where(StockLot.organization_id == ctx.org_id, StockLot.material_id == req.material_id, StockLot.quality_status == "OK")) or 0))
    check = compatible_offer(req, ctx.db.get(OrganizationMaterial, req.material_id), quote, ctx.db.get(OrganizationMaterial, quote.material_id), eligible)
    if not check["compatible"]: raise bad_request("INCOMPATIBLE_SUPPLIER_OFFER", "; ".join(check["reasons"]))
    used = Decimal(str(ctx.db.scalar(select(func.coalesce(func.sum(TenderSupplierSelection.selected_qty), 0)).where(TenderSupplierSelection.tender_requirement_snapshot_id == snapshot_id, TenderSupplierSelection.status == "SELECTED")) or 0))
    if body.selected_qty + used > check["shortage_qty"]: raise bad_request("OVER_ALLOCATION", "Allocation exceeds current procurement shortage")
    if body.selected_qty > quote.quantity: raise bad_request("QUOTE_QUANTITY_EXCEEDED", "Allocation exceeds supplier offer quantity")
    exists = ctx.db.scalar(select(TenderSupplierSelection.id).where(TenderSupplierSelection.tender_requirement_snapshot_id == snapshot_id, TenderSupplierSelection.supplier_quote_id == quote.id, TenderSupplierSelection.status == "SELECTED"))
    if exists: raise conflict("DUPLICATE_ALLOCATION", "Supplier offer already allocated to this requirement")
    tax = Decimal("0") if quote.tax_recoverable else quote.unit_price * quote.fx_rate_to_org_ccy * quote.tax_pct
    row = TenderSupplierSelection(organization_id=ctx.org_id, tender_id=tender_id, tender_requirement_snapshot_id=snapshot_id, supplier_quote_id=quote.id, selected_qty=body.selected_qty, unit=req.unit, unit_price=quote.unit_price, freight_per_unit=quote.freight_per_unit, nonrecoverable_tax_per_unit=tax, landed_cost_per_unit=check["landed_cost_per_unit"], valid_until=quote.valid_until, delivery_terms=body.delivery_terms, selected_by=ctx.user_id)
    ctx.db.add(row); ctx.db.flush(); record_audit(ctx, "tender.supplier_selection.create", "tender_supplier_selection", row.id, {"after": {"tender_id": str(tender_id), "snapshot_id": str(snapshot_id), "quote_id": str(quote.id), "quantity": str(body.selected_qty)}}); ctx.db.commit()
    return {"id": str(row.id), "selected_qty": str(row.selected_qty), "landed_cost_per_unit": str(row.landed_cost_per_unit)}


@router.post("/{tender_id}/supplier-selections/{selection_id}/cancel")
def cancel_supplier_selection(tender_id: UUID, selection_id: UUID, body: TenderSupplierSelectionCancelIn,
                              ctx: TenantContext = Depends(require("procurement:write"))):
    _get_tender(ctx, tender_id)
    locked = ctx.db.scalar(select(CostEstimate.id).where(CostEstimate.tender_id == tender_id,
        CostEstimate.organization_id == ctx.org_id, CostEstimate.status == "APPROVED"))
    if locked: raise conflict("SELECTIONS_LOCKED", "Approved tender costing locks supplier selections")
    row = ctx.db.scalar(select(TenderSupplierSelection).where(TenderSupplierSelection.id == selection_id,
        TenderSupplierSelection.tender_id == tender_id, TenderSupplierSelection.organization_id == ctx.org_id).with_for_update())
    if row is None: raise not_found("Tender supplier selection")
    if row.status != "SELECTED": raise conflict("SELECTION_NOT_ACTIVE", "Only active selections can be cancelled")
    row.status = "CANCELLED"; row.cancellation_reason = body.reason
    record_audit(ctx, "tender.supplier_selection.cancel", "tender_supplier_selection", row.id,
                 {"before": {"status": "SELECTED"}, "after": {"status": "CANCELLED", "reason": body.reason}})
    ctx.db.commit()
    return {"id": str(row.id), "status": row.status, "reason": row.cancellation_reason}


@router.get("/{tender_id}/supplier-selections/history")
def supplier_selection_history(tender_id: UUID, ctx: TenantContext = Depends(require("read"))):
    _get_tender(ctx, tender_id)
    rows = ctx.db.scalars(select(TenderSupplierSelection).where(TenderSupplierSelection.tender_id == tender_id,
        TenderSupplierSelection.organization_id == ctx.org_id).order_by(TenderSupplierSelection.created_at.desc())).all()
    return [{"id": str(x.id), "snapshot_id": str(x.tender_requirement_snapshot_id), "supplier_quote_id": str(x.supplier_quote_id),
             "quantity": str(x.selected_qty), "status": x.status, "reason": x.cancellation_reason,
             "selected_by": str(x.selected_by) if x.selected_by else None, "created_at": x.created_at.isoformat()} for x in rows]


def _t_out(ctx: TenantContext, t: Tender) -> TenderOut:
    out = TenderOut.model_validate(t)
    out.documents_count = ctx.db.scalar(select(func.count()).select_from(TenderDocument).where(
        TenderDocument.tender_id == t.id)) or 0
    out.boq_items_count = ctx.db.scalar(select(func.count()).select_from(BOQItem).where(
        BOQItem.tender_id == t.id)) or 0
    return out


def _get_tender(ctx: TenantContext, tender_id: UUID) -> Tender:
    t = ctx.db.scalar(select(Tender).where(Tender.id == tender_id,
                                           Tender.organization_id == ctx.org_id))
    if t is None:
        raise not_found("Tender")
    return t


@router.get("", response_model=Page[TenderOut])
def list_tenders(ctx: TenantContext = Depends(require("read")),
                 params: PageParams = Depends(), search: str | None = Query(None),
                 status: str | None = Query(None), project_type: str | None = Query(None),
                 data_classification: str | None = Query(None)):
    stmt = select(Tender).where(Tender.organization_id == ctx.org_id)
    if search:
        like = f"%{search}%"
        stmt = stmt.where((Tender.number.ilike(like)) | (Tender.title.ilike(like)))
    if status:
        stmt = stmt.where(Tender.status == status)
    if project_type:
        stmt = stmt.where(Tender.project_type == project_type)
    if data_classification:
        stmt = stmt.where(Tender.data_classification == data_classification)
    stmt = stmt.order_by(Tender.submission_deadline.asc().nullslast(), Tender.created_at.desc())
    rows, total = paginate(ctx.db, stmt, params)
    return Page(items=[_t_out(ctx, t) for t in rows], total=total,
                page=params.page, page_size=params.page_size)


VALID_TYPES = {"RAILWAY", "BRIDGE", "BUILDING", "INDUSTRIAL", "FABRICATION"}


@router.post("", response_model=TenderOut, status_code=201)
def create_tender(body: TenderIn, ctx: TenantContext = Depends(require("tenders:write"))):
    if body.project_type not in VALID_TYPES:
        raise bad_request("INVALID_PROJECT_TYPE", f"project_type must be one of {sorted(VALID_TYPES)}")
    if body.project_id:
        p = ctx.db.get(Project, body.project_id)
        if p is None or p.organization_id != ctx.org_id:
            raise not_found("Project")
    exists = ctx.db.scalar(select(Tender.id).where(Tender.organization_id == ctx.org_id,
                                                   Tender.number == body.number))
    if exists:
        raise conflict("DUPLICATE_NUMBER", f"Tender number '{body.number}' already exists")
    t = Tender(organization_id=ctx.org_id, **body.model_dump())
    ctx.db.add(t)
    ctx.db.flush()
    record_audit(ctx, "tender.create", "tender", t.id, {"after": body.model_dump()})
    ctx.db.commit()
    return _t_out(ctx, t)


@router.get("/{tender_id}", response_model=TenderOut)
def get_tender(tender_id: UUID, ctx: TenantContext = Depends(require("read"))):
    return _t_out(ctx, _get_tender(ctx, tender_id))


@router.patch("/{tender_id}", response_model=TenderOut)
def update_tender(tender_id: UUID, body: TenderUpdate,
                  ctx: TenantContext = Depends(require("tenders:write"))):
    t = _get_tender(ctx, tender_id)
    if t.status in ("WON", "LOST", "CANCELLED"):
        raise conflict("TENDER_CLOSED", f"Tender is {t.status}")
    changes = body.model_dump(exclude_unset=True)
    before = {k: getattr(t, k) for k in changes}
    for k, v in changes.items():
        setattr(t, k, v)
    record_audit(ctx, "tender.update", "tender", t.id, {"before": before, "after": changes})
    ctx.db.commit()
    return _t_out(ctx, t)


@router.patch("/{tender_id}/status", response_model=TenderOut)
def set_status(tender_id: UUID, body: TenderStatusIn,
               ctx: TenantContext = Depends(require("tenders:write"))):
    t = _get_tender(ctx, tender_id)
    allowed = TENDER_FLOW.get(t.status, set())
    if body.status not in allowed:
        raise conflict("INVALID_TRANSITION",
                       f"Cannot move tender from {t.status} to {body.status}",
                       {"allowed": sorted(allowed)})
    before = t.status
    t.status = body.status
    record_audit(ctx, "tender.status", "tender", t.id,
                 {"before": {"status": before}, "after": {"status": body.status}})
    ctx.db.commit()
    return _t_out(ctx, t)


# ---------------- Documents & extraction ----------------
@router.post("/{tender_id}/documents", response_model=TenderDocumentOut, status_code=201)
async def upload_document(tender_id: UUID, file: UploadFile = File(...),
                          ctx: TenantContext = Depends(require("tenders:write"))):
    t = _get_tender(ctx, tender_id)
    content = await file.read()
    if len(content) > settings.request_body_limit_bytes:
        raise bad_request("FILE_TOO_LARGE", "File exceeds the upload size limit")
    safe_name = os.path.basename(file.filename or "document.pdf")
    os.makedirs(os.path.join(settings.upload_dir, str(ctx.org_id)), exist_ok=True)
    storage_key = f"{ctx.org_id}/{t.id}/{uuid_mod.uuid4().hex}_{safe_name}"
    path = os.path.join(settings.upload_dir, storage_key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(content)
    doc = TenderDocument(
        organization_id=ctx.org_id, tender_id=t.id, file_name=safe_name,
        storage_key=storage_key, mime_type=file.content_type, size_bytes=len(content),
        status="UPLOADED", uploaded_by=ctx.user_id)
    ctx.db.add(doc)
    ctx.db.flush()
    record_audit(ctx, "tender.upload_document", "tender_document", doc.id,
                 {"after": {"file_name": safe_name, "size_bytes": len(content)}})
    ctx.db.commit()
    return TenderDocumentOut.model_validate(doc)


@router.get("/{tender_id}/documents", response_model=list[TenderDocumentOut])
def list_documents(tender_id: UUID, ctx: TenantContext = Depends(require("read"))):
    _get_tender(ctx, tender_id)
    rows = ctx.db.scalars(select(TenderDocument).where(
        TenderDocument.tender_id == tender_id,
        TenderDocument.organization_id == ctx.org_id)).all()
    return [TenderDocumentOut.model_validate(r) for r in rows]


@router.post("/{tender_id}/documents/{document_id}/extract", status_code=202)
def extract_document(tender_id: UUID, document_id: UUID,
                     ctx: TenantContext = Depends(require("tenders:write"))):
    """Run rule-based BOQ extraction. All results land as PENDING review with evidence —
    no value is auto-confirmed. (Celery worker runs the same code path when deployed.)"""
    _get_tender(ctx, tender_id)
    doc = ctx.db.scalar(select(TenderDocument).where(
        TenderDocument.id == document_id, TenderDocument.tender_id == tender_id,
        TenderDocument.organization_id == ctx.org_id))
    if doc is None:
        raise not_found("Document")
    job = AIJob(organization_id=ctx.org_id, job_type="TENDER_EXTRACTION", status="RUNNING",
                input={"tender_document_id": str(doc.id)}, created_by=ctx.user_id)
    ctx.db.add(job)
    doc.status = "EXTRACTING"
    ctx.db.flush()
    path = os.path.join(settings.upload_dir, doc.storage_key)
    total_candidates = 0
    try:
        if not os.path.exists(path):
            raise bad_request("FILE_MISSING", "Document bytes not found in storage")
        pages = extract_text_pages(path)
        line_no = 0
        for page_no, text in pages:
            injection_warnings = detect_injection_warnings(text)
            for cand in parse_boq_lines(text):
                line_no += 1
                # map to an org material by matching form+grade (never substitute silently)
                material_id = None
                if cand["form"] and cand["grade"]:
                    mat = ctx.db.scalar(select(OrganizationMaterial).where(
                        OrganizationMaterial.organization_id == ctx.org_id,
                        OrganizationMaterial.form == cand["form"],
                        OrganizationMaterial.grade == cand["grade"]).limit(1))
                    material_id = mat.id if mat else None
                boq = BOQItem(
                    organization_id=ctx.org_id, tender_id=tender_id,
                    tender_document_id=doc.id, line_no=str(line_no),
                    raw_description=cand["raw_description"], form=cand["form"],
                    grade=cand["grade"], specification=cand["specification"],
                    quantity=Decimal(cand["quantity"]) if cand["quantity"] else None,
                    unit=cand["unit"], material_id=material_id,
                    review_status="PENDING", source="AI", page_ref=f"p.{page_no}")
                ctx.db.add(boq)
                ctx.db.flush()
                ctx.db.add(ExtractionEvidence(
                    organization_id=ctx.org_id, document_id=doc.id, ai_job_id=job.id,
                    page=page_no, field="boq_line", raw_value=cand["raw_description"],
                    normalized_value={"quantity": cand["quantity"], "unit": cand["unit"],
                                      "form": cand["form"], "grade": cand["grade"],
                                      "boq_item_id": str(boq.id)},
                    confidence=Decimal(cand["confidence"]), review_status="PENDING",
                    warnings={"injection": injection_warnings} if injection_warnings else {}))
                total_candidates += 1
        doc.status = "EXTRACTED"
        job.status = "SUCCEEDED"
        job.output = {"candidates": total_candidates, "pages": len(pages)}
        job.completed_at = datetime.now(timezone.utc)
    except Exception as exc:
        doc.status = "FAILED"
        job.status = "FAILED"
        job.error = str(exc)[:2000]
        job.completed_at = datetime.now(timezone.utc)
        ctx.db.commit()
        raise bad_request("EXTRACTION_FAILED", f"Extraction failed: {exc}")
    record_audit(ctx, "tender.extract", "tender_document", doc.id,
                 {"after": {"candidates": total_candidates}})
    ctx.db.commit()
    return {"job_id": str(job.id), "status": job.status, "candidates": total_candidates}


# ---------------- BOQ ----------------
def _boq_out(ctx: TenantContext, b: BOQItem) -> BOQItemOut:
    out = BOQItemOut.model_validate(b)
    if b.material_id:
        m = ctx.db.get(OrganizationMaterial, b.material_id)
        out.material_name = m.name if m else None
    return out


@router.get("/{tender_id}/boq", response_model=list[BOQItemOut])
def list_boq(tender_id: UUID, ctx: TenantContext = Depends(require("read")),
             review_status: str | None = Query(None)):
    _get_tender(ctx, tender_id)
    stmt = select(BOQItem).where(BOQItem.tender_id == tender_id,
                                 BOQItem.organization_id == ctx.org_id)
    if review_status:
        stmt = stmt.where(BOQItem.review_status == review_status)
    rows = ctx.db.scalars(stmt.order_by(BOQItem.created_at)).all()
    return [_boq_out(ctx, b) for b in rows]


@router.post("/{tender_id}/boq", response_model=BOQItemOut, status_code=201)
def add_boq_item(tender_id: UUID, body: BOQItemIn,
                 ctx: TenantContext = Depends(require("tenders:write"))):
    _get_tender(ctx, tender_id)
    if body.material_id:
        m = ctx.db.get(OrganizationMaterial, body.material_id)
        if m is None or m.organization_id != ctx.org_id:
            raise not_found("Material")
    b = BOQItem(organization_id=ctx.org_id, tender_id=tender_id, source="MANUAL",
                review_status="CONFIRMED", **body.model_dump())
    ctx.db.add(b)
    ctx.db.flush()
    record_audit(ctx, "tender.add_boq_item", "boq_item", b.id, {"after": body.model_dump()})
    ctx.db.commit()
    return _boq_out(ctx, b)


@router.patch("/{tender_id}/boq/{item_id}/review", response_model=BOQItemOut)
def review_boq_item(tender_id: UUID, item_id: UUID, body: BOQReviewIn,
                    ctx: TenantContext = Depends(require("tenders:write"))):
    _get_tender(ctx, tender_id)
    b = ctx.db.scalar(select(BOQItem).where(BOQItem.id == item_id, BOQItem.tender_id == tender_id,
                                            BOQItem.organization_id == ctx.org_id))
    if b is None:
        raise not_found("BOQ item")
    if body.material_id:
        m = ctx.db.get(OrganizationMaterial, body.material_id)
        if m is None or m.organization_id != ctx.org_id:
            raise not_found("Material")
        b.material_id = body.material_id
    if body.quantity is not None:
        b.quantity = body.quantity
    before = b.review_status
    b.review_status = body.review_status
    # close the evidence record as reviewed too
    evidence = ctx.db.scalars(select(ExtractionEvidence).where(
        ExtractionEvidence.organization_id == ctx.org_id,
        ExtractionEvidence.normalized_value["boq_item_id"].astext == str(b.id))).all()
    for ev in evidence:
        ev.review_status = "CONFIRMED" if body.review_status == "CONFIRMED" else "REJECTED"
        ev.reviewer_id = ctx.user_id
        ev.reviewed_at = datetime.now(timezone.utc)
    record_audit(ctx, "tender.review_boq_item", "boq_item", b.id,
                 {"before": {"review_status": before}, "after": {"review_status": body.review_status}})
    ctx.db.commit()
    return _boq_out(ctx, b)


@router.get("/{tender_id}/boq/requirements-preview")
def requirements_preview(tender_id: UUID, ctx: TenantContext = Depends(require("read"))):
    """Aggregate CONFIRMED BOQ lines into material requirements, checking live availability."""
    from app.services.inventory import material_availability
    _get_tender(ctx, tender_id)
    rows = ctx.db.execute(
        select(BOQItem.material_id, func.sum(BOQItem.quantity)).where(
            BOQItem.tender_id == tender_id, BOQItem.organization_id == ctx.org_id,
            BOQItem.review_status == "CONFIRMED", BOQItem.material_id.isnot(None))
        .group_by(BOQItem.material_id)).all()
    out = []
    for material_id, qty in rows:
        mat = ctx.db.get(OrganizationMaterial, material_id)
        av = material_availability(None, ctx.db, ctx.org_id, material_id)
        shortage = max(Decimal("0"), Decimal(str(qty)) - av["available"])
        out.append({"material_id": str(material_id), "sku": mat.sku if mat else None,
                    "name": mat.name if mat else None, "required_qty": str(qty),
                    "available_qty": str(av["available"]), "shortage_qty": str(shortage)})
    return {"items": out}


@router.get("/{tender_id}/evidence", response_model=list[EvidenceOut])
def list_evidence(tender_id: UUID, ctx: TenantContext = Depends(require("read")),
                  review_status: str | None = Query(None)):
    _get_tender(ctx, tender_id)
    stmt = select(ExtractionEvidence).join(
        TenderDocument, ExtractionEvidence.document_id == TenderDocument.id).where(
        TenderDocument.tender_id == tender_id,
        ExtractionEvidence.organization_id == ctx.org_id)
    if review_status:
        stmt = stmt.where(ExtractionEvidence.review_status == review_status)
    rows = ctx.db.scalars(stmt.order_by(ExtractionEvidence.created_at)).all()
    return [EvidenceOut.model_validate(r) for r in rows]
