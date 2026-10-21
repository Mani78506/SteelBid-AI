import os
import uuid as uuid_mod
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, UploadFile, File
from sqlalchemy import func, select

from app.ai.extraction import detect_injection_warnings, extract_text_pages, parse_boq_lines
from app.config import get_settings
from app.core.deps import TenantContext, require
from app.core.errors import bad_request, conflict, not_found
from app.core.pagination import Page, PageParams, paginate
from app.models.materials import OrganizationMaterial
from app.models.inventory import StockLot
from app.models.procurement import Supplier, SupplierQuote
from app.models.ops import AIJob, CostEstimate
from app.models.projects import (BOQItem, ExtractionEvidence, Project, Tender, TenderDocument, TenderRequirementSnapshot, TenderSupplierSelection)
from app.schemas.projects import (BOQItemIn, BOQItemOut, BOQReviewIn, EvidenceOut,
                                  TenderDocumentOut, TenderIn, TenderOut, TenderStatusIn,
                                  TenderUpdate, TenderSupplierSelectionIn, TenderSupplierSelectionCancelIn)
from app.services.audit import record_audit
from app.services.tender_costing import compatible_offer

router = APIRouter(prefix="/tenders", tags=["tenders"])
settings = get_settings()

TENDER_FLOW = {
    "DRAFT": {"IN_REVIEW", "CANCELLED"},
    "IN_REVIEW": {"ESTIMATING", "CANCELLED"},
    "ESTIMATING": {"BID_SUBMITTED", "CANCELLED"},
    "BID_SUBMITTED": {"WON", "LOST"},
    "WON": set(), "LOST": set(), "CANCELLED": set(),
}


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
            quantity=boq.quantity, unit=boq.unit, approved_at=now))
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
                 status: str | None = Query(None), project_type: str | None = Query(None)):
    stmt = select(Tender).where(Tender.organization_id == ctx.org_id)
    if search:
        like = f"%{search}%"
        stmt = stmt.where((Tender.number.ilike(like)) | (Tender.title.ilike(like)))
    if status:
        stmt = stmt.where(Tender.status == status)
    if project_type:
        stmt = stmt.where(Tender.project_type == project_type)
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
