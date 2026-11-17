import os
import hashlib
import logging
import uuid as uuid_mod
import zipfile
from io import BytesIO
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, UploadFile, File, Form
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.config import get_settings
from app.core.deps import TenantContext, require
from app.core.errors import bad_request, conflict, not_found
from app.core.pagination import Page, PageParams, paginate
from app.models.materials import OrganizationMaterial
from app.models.inventory import Reservation, StockLot
from app.models.procurement import PurchaseRequest, PurchaseRequestItem, RFQ, Supplier, SupplierQuote
from app.models.ops import AIJob, Approval, CostEstimate, CostLine
from app.models.projects import (BOQItem, ExtractionEvidence, Project, Tender, TenderDocument, TenderRequirementSnapshot, TenderSupplierSelection, TenderInventoryAllocation, TenderSubmission, TenderWorkflow, TenderRevision, TenderSourceProvenance)
from app.models.fabrication import BOMItem, BOMVersion
from app.models.crm import Customer
from app.models.sales import Quotation, QuotationItem, QuotationVersion
from app.schemas.projects import (BOQItemIn, BOQItemOut, BOQReviewIn, EvidenceOut,
                                  TenderDocumentOut, TenderIn, TenderOut, TenderStatusIn,
                                  TenderUpdate, TenderSupplierSelectionIn, TenderSupplierSelectionCancelIn,
                                  TenderRevisionOut, TenderSourceProvenanceOut)
from app.services.audit import record_audit
from app.services.tender_costing import compatible_offer
from app.services.tender_inventory import analyze_bom_item_inventory, mapping_compatibility
from app.services.numbering import next_number
from app.services.inventory import reserve_stock, unreserve_stock
from app.services.quotations import create_quotation
from app.services.tender_document_extraction import TenderExtractionError, extract_and_persist
from app.services.tender_source_events import TenderSourceEventError, record_provenance
from app.schemas.sales import QuotationCreateIn, QuotationItemIn
from app.calc.finance import ZERO, cost_estimate_total, q_money, q_qty, tender_commercials

router = APIRouter(prefix="/tenders", tags=["tenders"])
settings = get_settings()
log = logging.getLogger(__name__)

TENDER_DOCUMENT_TYPES = {
    ".pdf": {"application/pdf"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
}


def _queue_document_extraction(*, tender_id: UUID, document_id: UUID) -> None:
    """Queue the same persisted extraction service used by the manual retry.

    Upload must remain durable even when the broker is temporarily unavailable.
    The caller records PENDING in that case, exposing the existing retry action
    instead of claiming that extraction happened.
    """
    from app.worker import extract_tender_document_task
    extract_tender_document_task.delay(str(tender_id), str(document_id))


def _validate_tender_document(file_name: str, content: bytes) -> str:
    """Validate the two persisted/extractable tender source formats.

    The browser MIME type is metadata only; signatures prevent a renamed file
    from entering the extraction pipeline.
    """
    extension = os.path.splitext(file_name)[1].lower()
    if extension not in TENDER_DOCUMENT_TYPES:
        raise bad_request("UNSUPPORTED_FILE_TYPE", "Only PDF and XLSX tender documents are supported")
    if extension == ".pdf" and not content.startswith(b"%PDF-"):
        raise bad_request("INVALID_FILE", "The uploaded PDF does not have a valid PDF signature")
    if extension == ".xlsx" and not zipfile.is_zipfile(BytesIO(content)):
        raise bad_request("INVALID_FILE", "The uploaded XLSX is not a valid workbook package")
    return extension

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


class TenderDraftRFQIn(BaseModel):
    supplier_ids: list[UUID] = Field(min_length=1)
    valid_until: date | None = None
    notes: str | None = Field(default=None, max_length=2000)


class AuthoritativeEstimateIn(BaseModel):
    markup: Decimal | None = Field(default=None, ge=0)
    target_margin: Decimal | None = Field(default=None, ge=0, lt=1)
    proposed_pre_tax_bid: Decimal | None = Field(default=None, ge=0)
    fabrication: Decimal = Field(default=ZERO, ge=0)
    freight: Decimal = Field(default=ZERO, ge=0)
    testing: Decimal = Field(default=ZERO, ge=0)
    overhead: Decimal = Field(default=ZERO, ge=0)
    financing: Decimal = Field(default=ZERO, ge=0)
    other: Decimal = Field(default=ZERO, ge=0)


class TenderInventoryAllocationIn(BaseModel):
    bom_item_id: UUID
    stock_lot_id: UUID
    quantity: Decimal = Field(gt=0)
    valuation_rate: Decimal = Field(gt=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    valuation_source: dict = Field(default_factory=dict)


class TenderAllocationReleaseIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class EstimateApprovalIn(BaseModel):
    remarks: str | None = Field(default=None, max_length=2000)


class FinalQuotationIn(BaseModel):
    """No commercial values are accepted: they must come from the approved snapshot."""
    pass

class SubmissionDraftIn(BaseModel):
    quotation_id: UUID
    quotation_version_id: UUID
    submission_method: str | None = Field(default=None, max_length=64)
    portal_reference: str | None = Field(default=None, max_length=128)
    acknowledgment_reference: str | None = Field(default=None, max_length=128)
    evidence_document_id: UUID | None = None
    submitted_at: datetime | None = None

class OutcomeIn(BaseModel):
    status: str = Field(pattern="^(WON|LOST|CANCELLED)$")
    outcome_date: date
    reference: str | None = Field(default=None, max_length=128)
    remarks: str | None = Field(default=None, max_length=2000)
    award_value: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class RevisionAcknowledgementIn(BaseModel):
    acknowledgement_note: str | None = Field(default=None, max_length=1000)


@router.get("/{tender_id}/workflow/inventory-allocations")
def list_tender_inventory_allocations(tender_id: UUID, ctx: TenantContext = Depends(require("read"))):
    _get_tender(ctx, tender_id)
    rows=ctx.db.scalars(select(TenderInventoryAllocation).where(TenderInventoryAllocation.tender_id==tender_id,TenderInventoryAllocation.organization_id==ctx.org_id).order_by(TenderInventoryAllocation.created_at.desc())).all()
    return [{"id":str(x.id),"bom_item_id":str(x.bom_item_id),"stock_lot_id":str(x.stock_lot_id),"reservation_id":str(x.reservation_id),"quantity":str(x.quantity),"unit":x.unit,"valuation_rate":str(x.valuation_rate),"currency":x.currency,"valuation_source":x.valuation_source,"status":x.status,"created_at":x.created_at.isoformat()} for x in rows]


@router.get("/{tender_id}/workflow/bom-items/{bom_item_id}/eligible-lots")
def eligible_tender_lots(tender_id: UUID, bom_item_id: UUID, ctx: TenantContext = Depends(require("read"))):
    tender=_get_tender(ctx,tender_id); workflow=_workflow(ctx,tender_id)
    bom=ctx.db.scalar(select(BOMItem).where(BOMItem.id==bom_item_id,BOMItem.bom_version_id==workflow.bom_version_id if workflow and workflow.bom_version_id else False))
    if bom is None: raise not_found("Current BOM item")
    rows=[]
    for lot in ctx.db.scalars(select(StockLot).where(StockLot.organization_id==ctx.org_id,StockLot.material_id==bom.material_id,StockLot.quality_status=="OK",StockLot.unit==bom.unit)).all():
        if not tender.is_demo and str((lot.source or {}).get("classification","")).upper()=="TRAINING": continue
        available=max(ZERO,Decimal(str(lot.on_hand_qty))-Decimal(str(lot.reserved_qty)))
        if available>ZERO: rows.append({"id":str(lot.id),"lot_number":lot.lot_number,"quantity":str(available),"unit":lot.unit,"quality_status":lot.quality_status,"valuation_rate":str(lot.unit_cost) if lot.unit_cost is not None else None,"currency":tender.currency,"valuation_source":lot.source or {},"classification":(lot.source or {}).get("classification","OPERATIONAL")})
    return {"bom_item_id":str(bom.id),"items":rows}


@router.get("/{tender_id}/workspace/inventory-match")
def tender_workspace_inventory_match(tender_id: UUID, ctx: TenantContext = Depends(require("read"))):
    """Read-only per-BOM inventory projection for the unified tender workspace.

    Quantities never cross unit boundaries.  ``available`` excludes every
    reservation, while a tender's own allocation is added back only for its
    coverage calculation so the same reserved stock is never counted twice.
    """
    tender = _get_tender(ctx, tender_id)
    workflow = _workflow(ctx, tender_id)
    if workflow is None or workflow.bom_version_id is None:
        return {"tender_id": str(tender_id), "bom_version_id": None, "items": []}

    allocations = ctx.db.scalars(select(TenderInventoryAllocation).where(
        TenderInventoryAllocation.organization_id == ctx.org_id,
        TenderInventoryAllocation.tender_id == tender_id,
        TenderInventoryAllocation.bom_version_id == workflow.bom_version_id,
        TenderInventoryAllocation.status == "ACTIVE",
    )).all()
    allocated_by_bom: dict[UUID, Decimal] = {}
    for allocation in allocations:
        allocated_by_bom[allocation.bom_item_id] = allocated_by_bom.get(allocation.bom_item_id, ZERO) + Decimal(str(allocation.quantity))

    items = []
    for bom in ctx.db.scalars(select(BOMItem).where(BOMItem.bom_version_id == workflow.bom_version_id)).all():
        material = ctx.db.get(OrganizationMaterial, bom.material_id)
        snapshot = ctx.db.get(TenderRequirementSnapshot, bom.tender_requirement_snapshot_id) if bom.tender_requirement_snapshot_id else None
        analysis = analyze_bom_item_inventory(ctx.db, ctx.org_id, tender, bom)
        required = Decimal(str(bom.quantity))
        allocated = allocated_by_bom.get(bom.id, ZERO)
        eligible = reserved = quality_held = available = ZERO
        reasons = list(analysis.get("reasons", []))
        blocked = analysis["status"] == "BLOCKED" or material is None

        if not blocked:
            for lot in ctx.db.scalars(select(StockLot).where(
                StockLot.organization_id == ctx.org_id,
                StockLot.material_id == bom.material_id,
                StockLot.unit == bom.unit,
            )).all():
                # Operational tenders must not see training inventory as usable.
                if not tender.is_demo and str((lot.source or {}).get("classification", "")).upper() in {"TRAINING", "SIMULATED"}:
                    continue
                on_hand = Decimal(str(lot.on_hand_qty))
                if lot.quality_status != "OK":
                    quality_held += on_hand
                    continue
                eligible += on_hand
                reserved += Decimal(str(lot.reserved_qty))
            available = max(ZERO, eligible - reserved)

        coverage = available + allocated
        shortage = max(ZERO, required - coverage) if not blocked else required
        status = "BLOCKED" if blocked else ("READY" if shortage == ZERO else "SHORTAGE")
        items.append({
            "bom_item_id": str(bom.id),
            "requirement_snapshot_id": str(bom.tender_requirement_snapshot_id) if bom.tender_requirement_snapshot_id else None,
            "material_id": str(bom.material_id),
            "material_name": material.name if material else None,
            "form": getattr(snapshot, "form", None) or (material.form if material else None),
            "grade": getattr(snapshot, "grade", None) or (material.grade if material else None),
            "specification": getattr(snapshot, "specification", None) or (material.specification if material else {}),
            "required_quantity": str(q_qty(required)), "unit": bom.unit,
            "eligible_stock_quantity": str(q_qty(eligible)), "reserved_quantity": str(q_qty(reserved)),
            "quality_held_quantity": str(q_qty(quality_held)), "available_quantity": str(q_qty(available)),
            "tender_allocated_quantity": str(q_qty(allocated)), "shortage_quantity": str(q_qty(shortage)),
            "matching_status": status, "reasons": reasons,
        })
    return {"tender_id": str(tender_id), "bom_version_id": str(workflow.bom_version_id), "items": items}


@router.get("/{tender_id}/workflow/authoritative-estimates")
def list_authoritative_estimates(tender_id: UUID, ctx: TenantContext = Depends(require("read"))):
    _get_tender(ctx,tender_id)
    rows=ctx.db.scalars(select(CostEstimate).where(CostEstimate.organization_id==ctx.org_id,CostEstimate.tender_id==tender_id,CostEstimate.context["calculation_version"].astext=="AUTHORITATIVE_TENDER_V1").order_by(CostEstimate.version.desc())).all()
    return [{"id":str(x.id),"version":x.version,"parent_estimate_id":str(x.parent_estimate_id) if x.parent_estimate_id else None,"status":x.status,"total_cost":str(x.total_cost),"context":x.context,"created_at":x.created_at.isoformat()} for x in rows]


@router.get("/{tender_id}/workflow/authoritative-estimates/{estimate_id}/breakdown")
def authoritative_estimate_breakdown(tender_id: UUID, estimate_id: UUID, ctx: TenantContext = Depends(require("read"))):
    _get_tender(ctx,tender_id)
    estimate=ctx.db.scalar(select(CostEstimate).where(CostEstimate.id==estimate_id,CostEstimate.tender_id==tender_id,CostEstimate.organization_id==ctx.org_id,CostEstimate.context["calculation_version"].astext=="AUTHORITATIVE_TENDER_V1"))
    if estimate is None: raise not_found("Authoritative estimate")
    lines=ctx.db.scalars(select(CostLine).where(CostLine.cost_estimate_id==estimate.id)).all(); inventory=ZERO; supplier=ZERO; additional=ZERO; categories={}
    for line in lines:
        amount=Decimal(str(line.amount)); categories[line.category]=categories.get(line.category,ZERO)+amount
        if (line.source or {}).get("inventory_allocation_id"): inventory+=amount
        elif (line.source or {}).get("supplier_selection_id"): supplier+=amount
        else: additional+=amount
    commercial=(estimate.context or {}).get("commercial",{})
    return {"id":str(estimate.id),"version":estimate.version,"status":estimate.status,"currency":estimate.currency,
            "inventory_material_cost":str(q_money(inventory)),"supplier_procurement_cost":str(q_money(supplier)),
            "additional_costs":str(q_money(additional)),"categories":{k:str(q_money(v)) for k,v in categories.items()},
            "lines":[{"id":str(line.id),"category":line.category,"description":line.description,"quantity":str(line.quantity) if line.quantity is not None else None,"unit":line.unit,"unit_cost":str(line.unit_cost) if line.unit_cost is not None else None,"amount":str(line.amount),"source":line.source or {}} for line in lines],
            "total_estimated_cost":str(estimate.total_cost),"proposed_pre_tax_bid":commercial.get("proposed_pre_tax_bid"),"projected_profit":commercial.get("projected_profit"),"markup":commercial.get("markup"),"gross_margin":commercial.get("gross_margin"),"tax_state":(estimate.context or {}).get("tax_state","NOT_RECORDED")}


@router.get("/{tender_id}/workflow/authoritative-estimates/{estimate_id}/revalidation")
def revalidate_authoritative_estimate(tender_id: UUID, estimate_id: UUID, ctx: TenantContext = Depends(require("read"))):
    _get_tender(ctx,tender_id); estimate=ctx.db.scalar(select(CostEstimate).where(CostEstimate.id==estimate_id,CostEstimate.tender_id==tender_id,CostEstimate.organization_id==ctx.org_id));
    if estimate is None: raise not_found("Authoritative estimate")
    blockers=[]; context=estimate.context or {}; workflow=_workflow(ctx,tender_id)
    if workflow is None or workflow.bom_version_id is None or context.get("bom_version_id") != str(workflow.bom_version_id):
        blockers.append({"code":"STALE_BOM"})
    allocations_by_bom: dict[UUID, Decimal] = {}; selections_by_snapshot: dict[UUID, Decimal] = {}
    seen_allocations=set(); seen_selections=set()
    for allocation_id in context.get("inventory_allocation_ids",[]):
        if allocation_id in seen_allocations:
            blockers.append({"code":"DUPLICATE_INVENTORY_ALLOCATION","allocation_id":allocation_id}); continue
        seen_allocations.add(allocation_id)
        allocation=ctx.db.scalar(select(TenderInventoryAllocation).where(TenderInventoryAllocation.id==allocation_id,TenderInventoryAllocation.organization_id==ctx.org_id,TenderInventoryAllocation.tender_id==tender_id))
        reservation=ctx.db.scalar(select(Reservation).where(Reservation.id==allocation.reservation_id,Reservation.organization_id==ctx.org_id)) if allocation else None
        lot=ctx.db.scalar(select(StockLot).where(StockLot.id==allocation.stock_lot_id,StockLot.organization_id==ctx.org_id)) if allocation else None
        invalid=allocation is None or allocation.status!="ACTIVE" or reservation is None or reservation.status!="ACTIVE" or lot is None or allocation.bom_version_id != (workflow.bom_version_id if workflow else None) or allocation.quantity<=ZERO or allocation.valuation_rate is None or not allocation.valuation_source or allocation.currency!=estimate.currency or reservation.quantity!=allocation.quantity
        if invalid:
            blockers.append({"code":"INVALID_INVENTORY_ALLOCATION","allocation_id":allocation_id}); continue
        allocations_by_bom[allocation.bom_item_id]=allocations_by_bom.get(allocation.bom_item_id,ZERO)+Decimal(str(allocation.quantity))
    for selection_id in context.get("supplier_selection_ids",[]):
        if selection_id in seen_selections:
            blockers.append({"code":"DUPLICATE_SUPPLIER_SELECTION","selection_id":selection_id}); continue
        seen_selections.add(selection_id)
        selection=ctx.db.scalar(select(TenderSupplierSelection).where(TenderSupplierSelection.id==selection_id,TenderSupplierSelection.organization_id==ctx.org_id,TenderSupplierSelection.tender_id==tender_id))
        if selection is None or selection.status!="SELECTED" or selection.selected_qty<=ZERO or selection.landed_cost_per_unit is None or (selection.valid_until and selection.valid_until<date.today()):
            blockers.append({"code":"INVALID_SUPPLIER_SELECTION","selection_id":selection_id}); continue
        selections_by_snapshot[selection.tender_requirement_snapshot_id]=selections_by_snapshot.get(selection.tender_requirement_snapshot_id,ZERO)+Decimal(str(selection.selected_qty))
    if workflow and workflow.bom_version_id:
        for bom in ctx.db.scalars(select(BOMItem).where(BOMItem.bom_version_id==workflow.bom_version_id)).all():
            inventory_qty=allocations_by_bom.get(bom.id,ZERO); supplier_qty=selections_by_snapshot.get(bom.tender_requirement_snapshot_id,ZERO)
            if inventory_qty+supplier_qty < Decimal(str(bom.quantity)): blockers.append({"code":"INCOMPLETE_COVERAGE","bom_item_id":str(bom.id)})
            if inventory_qty+supplier_qty > Decimal(str(bom.quantity)): blockers.append({"code":"EXCESS_COVERAGE","bom_item_id":str(bom.id)})
    return {"estimate_id":str(estimate.id),"status":"READY_FOR_APPROVAL" if not blockers else "REVALIDATION_REQUIRED","blockers":blockers}


@router.post("/{tender_id}/workflow/authoritative-estimates/{estimate_id}/submit-review")
def submit_authoritative_estimate_review(tender_id: UUID, estimate_id: UUID, body: EstimateApprovalIn, ctx: TenantContext = Depends(require("quotations:write"))):
    _get_tender(ctx,tender_id); estimate=ctx.db.scalar(select(CostEstimate).where(CostEstimate.id==estimate_id,CostEstimate.tender_id==tender_id,CostEstimate.organization_id==ctx.org_id));
    if estimate is None: raise not_found("Authoritative estimate")
    if estimate.status!="DRAFT": raise conflict("INVALID_APPROVAL_STATE","Only draft authoritative estimates can be submitted")
    estimate.status="PENDING_REVIEW"; approval=Approval(organization_id=ctx.org_id,entity_type="authoritative_estimate",entity_id=estimate.id,approval_type="TENDER_COMMERCIAL",requested_by=ctx.user_id,status="PENDING",comment=body.remarks);ctx.db.add(approval);ctx.db.commit();return {"status":estimate.status,"approval_id":str(approval.id)}


@router.post("/{tender_id}/workflow/authoritative-estimates/{estimate_id}/approve")
def approve_authoritative_estimate(tender_id: UUID, estimate_id: UUID, body: EstimateApprovalIn, ctx: TenantContext = Depends(require("tenders:approve_bid"))):
    _get_tender(ctx,tender_id); estimate=ctx.db.scalar(select(CostEstimate).where(CostEstimate.id==estimate_id,CostEstimate.tender_id==tender_id,CostEstimate.organization_id==ctx.org_id).with_for_update());
    if estimate is None: raise not_found("Authoritative estimate")
    if estimate.status!="PENDING_REVIEW": raise conflict("INVALID_APPROVAL_STATE","Estimate is not pending review")
    if estimate.created_by==ctx.user_id: raise conflict("SELF_APPROVAL_FORBIDDEN","Estimate creator cannot approve this estimate")
    result=revalidate_authoritative_estimate(tender_id,estimate_id,ctx)
    if result["status"]!="READY_FOR_APPROVAL": raise conflict("REVALIDATION_REQUIRED","Estimate sources require revalidation",result)
    estimate.status="APPROVED"; approval=ctx.db.scalar(select(Approval).where(Approval.entity_type=="authoritative_estimate",Approval.entity_id==estimate.id,Approval.status=="PENDING").order_by(Approval.created_at.desc()));
    if approval: approval.status="APPROVED";approval.decided_by=ctx.user_id;approval.decided_at=datetime.now(timezone.utc);approval.comment=body.remarks
    ctx.db.commit();return {"status":"APPROVED"}


def _decide_authoritative_estimate(tender_id: UUID, estimate_id: UUID, body: EstimateApprovalIn, target: str, ctx: TenantContext):
    _get_tender(ctx,tender_id)
    if not body.remarks or not body.remarks.strip(): raise bad_request("DECISION_REMARKS_REQUIRED","Remarks are required for this decision")
    estimate=ctx.db.scalar(select(CostEstimate).where(CostEstimate.id==estimate_id,CostEstimate.tender_id==tender_id,CostEstimate.organization_id==ctx.org_id).with_for_update())
    if estimate is None: raise not_found("Authoritative estimate")
    if estimate.status!="PENDING_REVIEW": raise conflict("INVALID_APPROVAL_STATE","Only pending-review estimates can be decided")
    approval=ctx.db.scalar(select(Approval).where(Approval.entity_type=="authoritative_estimate",Approval.entity_id==estimate.id,Approval.status=="PENDING").order_by(Approval.created_at.desc()).with_for_update())
    if approval is None: raise conflict("APPROVAL_NOT_PENDING","No pending approval exists for this estimate")
    estimate.status=target;approval.status=target;approval.decided_by=ctx.user_id;approval.decided_at=datetime.now(timezone.utc);approval.comment=body.remarks
    ctx.db.commit();return {"status":target}


@router.post("/{tender_id}/workflow/authoritative-estimates/{estimate_id}/reject")
def reject_authoritative_estimate(tender_id: UUID, estimate_id: UUID, body: EstimateApprovalIn, ctx: TenantContext = Depends(require("tenders:approve_bid"))):
    return _decide_authoritative_estimate(tender_id,estimate_id,body,"REJECTED",ctx)


@router.post("/{tender_id}/workflow/authoritative-estimates/{estimate_id}/return-for-revision")
def return_authoritative_estimate(tender_id: UUID, estimate_id: UUID, body: EstimateApprovalIn, ctx: TenantContext = Depends(require("tenders:approve_bid"))):
    return _decide_authoritative_estimate(tender_id,estimate_id,body,"RETURNED",ctx)


@router.get("/{tender_id}/workflow/authoritative-estimates/{estimate_id}/approvals")
def authoritative_estimate_approvals(tender_id: UUID, estimate_id: UUID, ctx: TenantContext = Depends(require("read"))):
    _get_tender(ctx,tender_id); estimate=ctx.db.scalar(select(CostEstimate).where(CostEstimate.id==estimate_id,CostEstimate.tender_id==tender_id,CostEstimate.organization_id==ctx.org_id))
    if estimate is None: raise not_found("Authoritative estimate")
    rows=ctx.db.scalars(select(Approval).where(Approval.organization_id==ctx.org_id,Approval.entity_type=="authoritative_estimate",Approval.entity_id==estimate.id).order_by(Approval.created_at)).all()
    return {"estimate_id":str(estimate.id),"version":estimate.version,"status":estimate.status,"items":[{"id":str(x.id),"status":x.status,"submitted_by":str(x.requested_by) if x.requested_by else None,"submitted_at":x.created_at.isoformat(),"decided_by":str(x.decided_by) if x.decided_by else None,"decided_at":x.decided_at.isoformat() if x.decided_at else None,"remarks":x.comment} for x in rows]}


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
        tender = _get_tender(ctx, workflow.tender_id)
        for item in ctx.db.scalars(select(BOMItem).where(BOMItem.bom_version_id == workflow.bom_version_id)).all():
            analysis = analyze_bom_item_inventory(ctx.db, ctx.org_id, tender, item)
            available = analysis["eligible_quantity"]
            shortages.append({"bom_item_id": str(item.id), "snapshot_id": str(item.tender_requirement_snapshot_id) if item.tender_requirement_snapshot_id else None,
                              "material_id": str(item.material_id), "required_quantity": str(item.quantity),
                              "available_quantity": str(available), "shortage_quantity": str(analysis["shortage_quantity"]), "unit": item.unit,
                              "status": analysis["status"], "eligibility_notes": analysis["reasons"]})
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
        material = ctx.db.get(OrganizationMaterial, boq.material_id)
        if material is None or material.organization_id != ctx.org_id:
            raise bad_request("UNRESOLVED_MATERIAL", f"BOQ line {boq.line_no or boq.id} is not mapped to a tenant material")
        reasons = mapping_compatibility(material, boq)
        if reasons:
            raise bad_request("INCOMPATIBLE_BOQ_MAPPING", "A confirmed BOQ line does not match its mapped material", {"boq_item_id": str(boq.id), "reasons": reasons})
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
    if workflow.bom_version_id and workflow.requirement_snapshot_version == ctx.db.scalar(select(func.max(TenderRequirementSnapshot.version)).where(
        TenderRequirementSnapshot.organization_id == ctx.org_id, TenderRequirementSnapshot.tender_id == tender_id)):
        return _workflow_out(ctx, workflow)
    if workflow.cost_estimate_id:
        raise conflict("BOM_LOCKED_BY_ESTIMATE", "Create a new tender workflow revision before changing a BOM with a persisted estimate")
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
                     version_no=(ctx.db.scalar(select(func.max(BOMVersion.version_no)).where(
                         BOMVersion.organization_id == ctx.org_id, BOMVersion.bom_code == f"TND-{tender.number}-BOM")) or 0) + 1,
                     status="DRAFT")
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


@router.get("/{tender_id}/workflow/inventory-analysis")
def workflow_inventory_analysis(tender_id: UUID, ctx: TenantContext = Depends(require("read"))):
    """Compatibility-safe inventory coverage for the current tender BOM."""
    tender = _get_tender(ctx, tender_id)
    workflow = _workflow(ctx, tender_id)
    if workflow is None or workflow.bom_version_id is None:
        raise bad_request("MISSING_BOM", "Generate the tender BOM before analysing inventory")
    rows = []
    for item in ctx.db.scalars(select(BOMItem).where(BOMItem.bom_version_id == workflow.bom_version_id)).all():
        material = ctx.db.get(OrganizationMaterial, item.material_id)
        analysis = analyze_bom_item_inventory(ctx.db, ctx.org_id, tender, item)
        rows.append({"bom_item_id": str(item.id), "material_id": str(item.material_id),
                     "material": material.name if material else "Unresolved material", "form": material.form if material else None,
                     "grade": material.grade if material else None, "required_quantity": str(item.quantity), "unit": item.unit,
                     "eligible_quantity": str(analysis["eligible_quantity"]), "shortage_quantity": str(analysis["shortage_quantity"]),
                     "status": analysis["status"], "notes": analysis["reasons"]})
    return {"tender_id": str(tender_id), "bom_version_id": str(workflow.bom_version_id),
            "data_classification": tender.data_classification, "items": rows}


def _tender_procurement_request(ctx: TenantContext, tender_id: UUID, bom_version_id: UUID | None = None) -> PurchaseRequest | None:
    rows = ctx.db.scalars(select(PurchaseRequest).where(
        PurchaseRequest.organization_id == ctx.org_id, PurchaseRequest.source_type == "TENDER_SHORTAGE").order_by(PurchaseRequest.created_at.desc())).all()
    for row in rows:
        context = row.context or {}
        if context.get("tender_id") == str(tender_id) and (bom_version_id is None or context.get("bom_version_id") == str(bom_version_id)):
            return row
    return None


@router.post("/{tender_id}/workflow/procurement-requirements", status_code=201)
def generate_procurement_requirements(tender_id: UUID, ctx: TenantContext = Depends(require("procurement:write"))):
    """Freeze current BOM shortages as a draft purchase request; never issues an RFQ."""
    tender = _get_tender(ctx, tender_id)
    workflow = _workflow(ctx, tender_id)
    if workflow is None or workflow.bom_version_id is None:
        raise bad_request("MISSING_BOM", "Generate the tender BOM before procurement requirements")
    existing = _tender_procurement_request(ctx, tender_id, workflow.bom_version_id)
    if existing:
        items = ctx.db.scalars(select(PurchaseRequestItem).where(PurchaseRequestItem.purchase_request_id == existing.id)).all()
        return {"id": str(existing.id), "number": existing.number, "status": existing.status, "created": False, "lines": len(items)}
    if workflow.cost_estimate_id:
        raise conflict("PROCUREMENT_LOCKED_BY_ESTIMATE", "Do not change procurement requirements after an estimate is persisted")
    lines = []
    for item in ctx.db.scalars(select(BOMItem).where(BOMItem.bom_version_id == workflow.bom_version_id)).all():
        analysis = analyze_bom_item_inventory(ctx.db, ctx.org_id, tender, item)
        if analysis["status"] == "BLOCKED" or analysis["shortage_quantity"] <= ZERO:
            continue
        snapshot = ctx.db.get(TenderRequirementSnapshot, item.tender_requirement_snapshot_id)
        lines.append((item, snapshot, analysis))
    if not lines:
        return {"tender_id": str(tender_id), "status": "NO_PROCUREMENT_REQUIRED", "created": False, "lines": 0}
    pr = PurchaseRequest(organization_id=ctx.org_id, number=next_number(ctx.db, PurchaseRequest, ctx.org_id, prefix="PR"),
        status="DRAFT", source_type="TENDER_SHORTAGE", needed_by=tender.submission_deadline.date() if tender.submission_deadline else None,
        context={"tender_id": str(tender_id), "bom_version_id": str(workflow.bom_version_id),
                 "snapshot_version": workflow.requirement_snapshot_version, "data_classification": tender.data_classification,
                 "external_communication": "NOT_SENT"}, created_by=ctx.user_id)
    ctx.db.add(pr); ctx.db.flush()
    for item, snapshot, analysis in lines:
        ctx.db.add(PurchaseRequestItem(organization_id=ctx.org_id, purchase_request_id=pr.id, material_id=item.material_id,
            quantity=analysis["shortage_quantity"], unit=item.unit, required_by=pr.needed_by))
    record_audit(ctx, "tender.procurement_requirements.create", "purchase_request", pr.id,
                 {"after": {"tender_id": str(tender_id), "bom_version_id": str(workflow.bom_version_id), "lines": len(lines)}})
    ctx.db.commit()
    return {"id": str(pr.id), "number": pr.number, "status": pr.status, "created": True, "lines": len(lines)}


@router.get("/{tender_id}/workflow/procurement-requirements")
def list_procurement_requirements(tender_id: UUID, ctx: TenantContext = Depends(require("read"))):
    _get_tender(ctx, tender_id)
    workflow = _workflow(ctx, tender_id)
    request = _tender_procurement_request(ctx, tender_id, workflow.bom_version_id if workflow else None)
    if request is None:
        return {"status": "NOT_CREATED", "items": [], "rfqs": []}
    items = ctx.db.scalars(select(PurchaseRequestItem).where(PurchaseRequestItem.purchase_request_id == request.id)).all()
    rfqs = ctx.db.scalars(select(RFQ).where(RFQ.organization_id == ctx.org_id, RFQ.purchase_request_id == request.id)).all()
    return {"id": str(request.id), "number": request.number, "status": request.status, "context": request.context,
            "items": [{"id": str(item.id), "material_id": str(item.material_id), "quantity": str(item.quantity), "unit": item.unit,
                       "required_by": item.required_by.isoformat() if item.required_by else None} for item in items],
            "rfqs": [{"id": str(r.id), "number": r.number, "status": r.status, "valid_until": r.valid_until.isoformat() if r.valid_until else None, "notes": r.notes} for r in rfqs]}


@router.post("/{tender_id}/workflow/draft-rfqs", status_code=201)
def create_tender_draft_rfqs(tender_id: UUID, body: TenderDraftRFQIn, ctx: TenantContext = Depends(require("procurement:write"))):
    """Create internal DRAFT RFQs only.  Sending/e-mailing is deliberately out of scope."""
    _get_tender(ctx, tender_id)
    workflow = _workflow(ctx, tender_id)
    request = _tender_procurement_request(ctx, tender_id, workflow.bom_version_id if workflow else None)
    if request is None:
        raise bad_request("MISSING_PROCUREMENT_REQUIREMENTS", "Generate tender procurement requirements before draft RFQs")
    created = []
    for supplier_id in body.supplier_ids:
        supplier = ctx.db.scalar(select(Supplier).where(Supplier.id == supplier_id, Supplier.organization_id == ctx.org_id, Supplier.is_active.is_(True)))
        if supplier is None:
            raise not_found("Active supplier")
        existing = ctx.db.scalar(select(RFQ).where(RFQ.organization_id == ctx.org_id, RFQ.purchase_request_id == request.id,
            RFQ.status == "DRAFT", RFQ.notes.contains(f'"supplier_id": "{supplier_id}"')))
        if existing:
            created.append(existing); continue
        rfq = RFQ(organization_id=ctx.org_id, purchase_request_id=request.id, number=next_number(ctx.db, RFQ, ctx.org_id, prefix="RFQ"),
                  status="DRAFT", valid_until=body.valid_until,
                  notes=str({"supplier_id": str(supplier_id), "supplier": supplier.name, "delivery": request.needed_by.isoformat() if request.needed_by else None,
                             "external_communication": "NOT_SENT", "user_notes": body.notes}))
        ctx.db.add(rfq); created.append(rfq)
    request.status = "RFQ_DRAFT"
    ctx.db.flush(); record_audit(ctx, "tender.rfq.draft", "purchase_request", request.id, {"after": {"rfqs": len(created), "external_communication": "NOT_SENT"}})
    ctx.db.commit()
    return {"purchase_request_id": str(request.id), "status": request.status,
            "rfqs": [{"id": str(r.id), "number": r.number, "status": r.status} for r in created]}


@router.post("/{tender_id}/workflow/authoritative-estimates", status_code=201)
def create_authoritative_estimate(tender_id: UUID, body: AuthoritativeEstimateIn,
                                  ctx: TenantContext = Depends(require("quotations:write"))):
    """Persist a new immutable draft only when every BOM quantity has an auditable cost source."""
    tender = _get_tender(ctx, tender_id); workflow = _workflow(ctx, tender_id)
    if workflow is None or workflow.bom_version_id is None:
        raise bad_request("MISSING_BOM", "Generate the tender BOM before authoritative costing")
    blockers=[]; material_cost=ZERO; source_lines=[]; allocation_lines=[]
    for bom in ctx.db.scalars(select(BOMItem).where(BOMItem.bom_version_id == workflow.bom_version_id)).all():
        allocations=ctx.db.scalars(select(TenderInventoryAllocation).where(TenderInventoryAllocation.organization_id==ctx.org_id,TenderInventoryAllocation.tender_id==tender_id,TenderInventoryAllocation.bom_version_id==workflow.bom_version_id,TenderInventoryAllocation.bom_item_id==bom.id,TenderInventoryAllocation.status=="ACTIVE")).all()
        allocation_ids=set(); inventory_qty=ZERO
        for allocation in allocations:
            if allocation.id in allocation_ids: blockers.append({"bom_item_id":str(bom.id),"code":"DUPLICATE_ALLOCATION"}); continue
            allocation_ids.add(allocation.id)
            reservation=ctx.db.scalar(select(Reservation).where(Reservation.id==allocation.reservation_id,Reservation.organization_id==ctx.org_id))
            lot=ctx.db.scalar(select(StockLot).where(StockLot.id==allocation.stock_lot_id,StockLot.organization_id==ctx.org_id))
            if reservation is None or reservation.status!="ACTIVE" or lot is None or lot.material_id!=bom.material_id or allocation.unit!=bom.unit or allocation.quantity<=ZERO or allocation.valuation_rate is None or not allocation.valuation_source or allocation.currency!=tender.currency:
                blockers.append({"bom_item_id":str(bom.id),"code":"INVALID_INVENTORY_ALLOCATION","allocation_id":str(allocation.id)}); continue
            inventory_qty+=Decimal(str(allocation.quantity)); material_cost+=Decimal(str(allocation.quantity))*Decimal(str(allocation.valuation_rate)); allocation_lines.append(allocation)
        selected=ctx.db.scalars(select(TenderSupplierSelection).where(TenderSupplierSelection.tender_requirement_snapshot_id==bom.tender_requirement_snapshot_id,TenderSupplierSelection.status=="SELECTED")).all()
        selected_qty=sum((Decimal(str(x.selected_qty)) for x in selected),ZERO)
        if selected_qty + inventory_qty < Decimal(str(bom.quantity)): blockers.append({"bom_item_id":str(bom.id),"code":"INCOMPLETE_COVERAGE"})
        if selected_qty + inventory_qty > Decimal(str(bom.quantity)): blockers.append({"bom_item_id":str(bom.id),"code":"EXCESS_COVERAGE"})
        for selection in selected:
            if selection.valid_until and selection.valid_until < date.today(): blockers.append({"bom_item_id":str(bom.id),"code":"EXPIRED_SUPPLIER_SELECTION","selection_id":str(selection.id)})
            material_cost += Decimal(str(selection.selected_qty))*Decimal(str(selection.landed_cost_per_unit))
            source_lines.append(selection)
    if blockers: raise bad_request("ESTIMATE_NOT_READY","Authoritative estimate has unresolved cost blockers",{"blockers":blockers})
    additional=body.fabrication+body.freight+body.testing+body.overhead+body.financing+body.other
    total=q_money(material_cost+additional); commercial=tender_commercials(total,markup=body.markup,target_margin=body.target_margin,proposed_bid=body.proposed_pre_tax_bid)
    # Serialise revision-number allocation for this tender inside the request transaction.
    ctx.db.scalar(select(Tender).where(Tender.id == tender_id, Tender.organization_id == ctx.org_id).with_for_update())
    latest=ctx.db.scalar(select(CostEstimate).where(CostEstimate.organization_id==ctx.org_id,CostEstimate.tender_id==tender_id,CostEstimate.context["calculation_version"].astext=="AUTHORITATIVE_TENDER_V1").order_by(CostEstimate.version.desc()).limit(1)); prior=latest.version if latest else 0
    estimate=CostEstimate(organization_id=ctx.org_id,tender_id=tender_id,status="DRAFT",version=prior+1,parent_estimate_id=latest.id if latest else None,currency=tender.currency,material_cost=q_money(material_cost),fabrication_cost=body.fabrication,freight_cost=body.freight,overhead_cost=body.overhead,total_cost=total,created_by=ctx.user_id,context={"calculation_version":"AUTHORITATIVE_TENDER_V1","bom_version_id":str(workflow.bom_version_id),"snapshot_version":workflow.requirement_snapshot_version,"supplier_selection_ids":[str(x.id) for x in source_lines],"inventory_allocation_ids":[str(x.id) for x in allocation_lines],"commercial":{k:str(v) for k,v in commercial.items()},"tax_state":"NOT_RECORDED","classification":tender.data_classification})
    ctx.db.add(estimate);ctx.db.flush()
    for x in source_lines: ctx.db.add(CostLine(organization_id=ctx.org_id,cost_estimate_id=estimate.id,category="MATERIAL",description="Selected supplier landed cost",quantity=x.selected_qty,unit=x.unit,unit_cost=x.landed_cost_per_unit,amount=q_money(x.selected_qty*x.landed_cost_per_unit),source={"supplier_selection_id":str(x.id)}))
    for x in allocation_lines: ctx.db.add(CostLine(organization_id=ctx.org_id,cost_estimate_id=estimate.id,category="MATERIAL",description="Allocated inventory valuation",quantity=x.quantity,unit=x.unit,unit_cost=x.valuation_rate,amount=q_money(x.quantity*x.valuation_rate),source={"inventory_allocation_id":str(x.id),"stock_lot_id":str(x.stock_lot_id),"reservation_id":str(x.reservation_id),"valuation_source":x.valuation_source,"currency":x.currency}))
    for category,amount in (("FABRICATION",body.fabrication),("FREIGHT",body.freight),("TESTING",body.testing),("OVERHEAD",body.overhead),("FINANCING",body.financing),("OTHER",body.other)):
        if amount: ctx.db.add(CostLine(organization_id=ctx.org_id,cost_estimate_id=estimate.id,category=category,description="Explicit commercial input",amount=amount,source={"explicit":True}))
    # The estimate workbook is a supported workflow export.  Keep its
    # authoritative source discoverable through the workflow just as the
    # legacy estimate path does; quotation XLSX remains intentionally absent.
    workflow.cost_estimate_id = estimate.id
    ctx.db.commit();return {"id":str(estimate.id),"version":estimate.version,"status":estimate.status,"total_cost":str(total),**{k:str(v) for k,v in commercial.items()},"tax_state":"NOT_RECORDED"}


@router.post("/{tender_id}/workflow/inventory-allocations", status_code=201)
def allocate_tender_inventory(tender_id: UUID, body: TenderInventoryAllocationIn,
                              ctx: TenantContext = Depends(require("tenders:write"))):
    tender=_get_tender(ctx,tender_id); workflow=_workflow(ctx,tender_id)
    if not workflow or not workflow.bom_version_id: raise bad_request("MISSING_BOM","Generate BOM before allocation")
    bom=ctx.db.scalar(select(BOMItem).where(BOMItem.id==body.bom_item_id,BOMItem.bom_version_id==workflow.bom_version_id))
    lot=ctx.db.scalar(select(StockLot).where(StockLot.id==body.stock_lot_id,StockLot.organization_id==ctx.org_id))
    if bom is None or lot is None: raise not_found("BOM item or stock lot")
    if lot.material_id!=bom.material_id or lot.unit!=bom.unit: raise bad_request("INCOMPATIBLE_STOCK_LOT","Stock lot material or unit differs from BOM")
    if not tender.is_demo and str((lot.source or {}).get("classification","")).upper()=="TRAINING": raise bad_request("TRAINING_STOCK_EXCLUDED","Training stock cannot fulfill an operational tender")
    if body.currency != tender.currency: raise bad_request("CURRENCY_MISMATCH","Allocation valuation currency differs from tender currency")
    duplicate=ctx.db.scalar(select(TenderInventoryAllocation.id).where(TenderInventoryAllocation.organization_id==ctx.org_id,TenderInventoryAllocation.tender_id==tender_id,TenderInventoryAllocation.bom_version_id==workflow.bom_version_id,TenderInventoryAllocation.bom_item_id==bom.id,TenderInventoryAllocation.stock_lot_id==lot.id,TenderInventoryAllocation.status=="ACTIVE"))
    if duplicate: raise conflict("DUPLICATE_ALLOCATION","This stock lot is already actively allocated to the tender BOM requirement")
    allocation_key = "talloc:" + hashlib.sha256(f"{tender_id}:{bom.id}:{lot.id}:{body.quantity}".encode()).hexdigest()
    reservation=reserve_stock(ctx,lot_id=lot.id,quantity=body.quantity,context={"tender_id":str(tender_id),"bom_item_id":str(bom.id),"kind":"TENDER_ALLOCATION"},idempotency_key=allocation_key)
    allocation=TenderInventoryAllocation(organization_id=ctx.org_id,tender_id=tender_id,bom_version_id=workflow.bom_version_id,bom_item_id=bom.id,stock_lot_id=lot.id,reservation_id=reservation.id,quantity=body.quantity,unit=bom.unit,valuation_rate=body.valuation_rate,currency=body.currency,valuation_source=body.valuation_source,status="ACTIVE",created_by=ctx.user_id)
    ctx.db.add(allocation);ctx.db.flush();record_audit(ctx,"tender.inventory.allocate","tender_inventory_allocation",allocation.id,{"after":{"quantity":str(body.quantity),"valuation_rate":str(body.valuation_rate)}});ctx.db.commit()
    return {"id":str(allocation.id),"status":allocation.status,"reservation_id":str(reservation.id)}


@router.post("/{tender_id}/workflow/inventory-allocations/{allocation_id}/release")
def release_tender_inventory(tender_id: UUID, allocation_id: UUID, body: TenderAllocationReleaseIn, ctx: TenantContext = Depends(require("tenders:write"))):
    _get_tender(ctx,tender_id); row=ctx.db.scalar(select(TenderInventoryAllocation).where(TenderInventoryAllocation.id==allocation_id,TenderInventoryAllocation.tender_id==tender_id,TenderInventoryAllocation.organization_id==ctx.org_id).with_for_update())
    if row is None: raise not_found("Tender inventory allocation")
    if row.status != "ACTIVE": return {"id":str(row.id),"status":row.status,"idempotent":True}
    dependent=[]
    for estimate in ctx.db.scalars(select(CostEstimate).where(CostEstimate.organization_id==ctx.org_id,CostEstimate.tender_id==tender_id)).all():
        if str(row.id) in (estimate.context or {}).get("inventory_allocation_ids",[]): dependent.append(estimate)
    locked=[x for x in dependent if x.status in {"APPROVED","FINALIZED","LOCKED"}]
    if locked:
        raise conflict("ALLOCATION_LOCKED_BY_ESTIMATE","Allocation is referenced by a commercially locked estimate",{"allocation_id":str(row.id),"estimate_ids":[str(x.id) for x in locked]})
    unreserve_stock(ctx,reservation_id=row.reservation_id);row.status="CANCELLED";row.valuation_source={**(row.valuation_source or {}),"release_reason":body.reason,"released_by":str(ctx.user_id)}
    record_audit(ctx,"tender.inventory.release","tender_inventory_allocation",row.id,{"after":{"status":"CANCELLED","reason":body.reason}});ctx.db.commit();return {"id":str(row.id),"status":row.status}


@router.post("/{tender_id}/workflow/customer")
def select_workflow_customer(tender_id: UUID, body: WorkflowCustomerIn,
                             ctx: TenantContext = Depends(require("quotations:write"))):
    tender = _get_tender(ctx, tender_id)
    customer = ctx.db.scalar(select(Customer).where(Customer.id == body.customer_id,
                                                     Customer.organization_id == ctx.org_id,
                                                     Customer.is_active.is_(True)))
    if customer is None:
        raise not_found("Active customer")
    workflow = _workflow(ctx, tender_id, create=True)
    workflow.customer_id = customer.id
    # Submission readiness is tender-scoped while quotation creation uses the
    # workflow customer.  Persist the same authorized customer in both places.
    tender.customer = customer.name
    record_audit(ctx, "tender.workflow.customer", "tender_workflow", workflow.id,
                 {"after": {"customer_id": str(customer.id), "tender_customer": customer.name}})
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


@router.post("/{tender_id}/workflow/final-quotation", status_code=201)
def create_final_authoritative_quotation(tender_id: UUID, body: FinalQuotationIn,
                                         ctx: TenantContext = Depends(require("quotations:write"))):
    """Create a DRAFT customer quotation strictly from an approved authoritative snapshot.

    This is deliberately separate from the legacy/demo-rate quotation path above.
    It never assumes tax, validity, payment, delivery, or submission terms.
    """
    tender = _get_tender(ctx, tender_id); workflow = _workflow(ctx, tender_id)
    if workflow is None or workflow.bom_version_id is None or workflow.customer_id is None:
        raise bad_request("MISSING_FINAL_QUOTATION_PREREQUISITE", "A BOM and selected customer are required before final quotation generation")
    estimate = ctx.db.scalar(select(CostEstimate).where(
        CostEstimate.organization_id == ctx.org_id, CostEstimate.tender_id == tender_id,
        CostEstimate.context["calculation_version"].astext == "AUTHORITATIVE_TENDER_V1",
        CostEstimate.status == "APPROVED").order_by(CostEstimate.version.desc()).limit(1))
    if estimate is None:
        raise bad_request("APPROVED_AUTHORITATIVE_ESTIMATE_REQUIRED", "An approved authoritative estimate is required; demo-rate estimates cannot generate a final quotation")
    approval = ctx.db.scalar(select(Approval).where(Approval.organization_id == ctx.org_id,
        Approval.entity_type == "authoritative_estimate", Approval.entity_id == estimate.id,
        Approval.status == "APPROVED").order_by(Approval.decided_at.desc()).limit(1))
    if approval is None:
        raise bad_request("COMMERCIAL_APPROVAL_REQUIRED", "The authoritative estimate has no persisted commercial approval")
    revalidation = revalidate_authoritative_estimate(tender_id, estimate.id, ctx)
    if revalidation["status"] != "READY_FOR_APPROVAL":
        raise conflict("REVALIDATION_REQUIRED", "The approved snapshot requires revalidation before final quotation", revalidation)
    commercial = (estimate.context or {}).get("commercial", {})
    proposed_bid = Decimal(str(commercial.get("proposed_pre_tax_bid", "0")))
    if proposed_bid <= ZERO:
        raise bad_request("MISSING_PROPOSED_BID", "The approved estimate has no proposed pre-tax bid")
    boms = ctx.db.scalars(select(BOMItem).where(BOMItem.bom_version_id == workflow.bom_version_id)).all()
    by_bom: dict[UUID, Decimal] = {x.id: ZERO for x in boms}
    for line in ctx.db.scalars(select(CostLine).where(CostLine.cost_estimate_id == estimate.id)).all():
        source = line.source or {}; bom_id = None
        if source.get("inventory_allocation_id"):
            allocation = ctx.db.get(TenderInventoryAllocation, UUID(source["inventory_allocation_id"]))
            bom_id = allocation.bom_item_id if allocation else None
        elif source.get("supplier_selection_id"):
            selection = ctx.db.get(TenderSupplierSelection, UUID(source["supplier_selection_id"]))
            if selection:
                bom = ctx.db.scalar(select(BOMItem).where(BOMItem.bom_version_id == workflow.bom_version_id,
                    BOMItem.tender_requirement_snapshot_id == selection.tender_requirement_snapshot_id))
                bom_id = bom.id if bom else None
        if bom_id in by_bom:
            by_bom[bom_id] += Decimal(str(line.amount))
    material_cost = sum(by_bom.values(), ZERO)
    if not boms or material_cost <= ZERO:
        raise bad_request("UNQUOTABLE_APPROVED_SNAPSHOT", "Approved estimate has no traceable BOM material cost for quotation lines")
    existing = ctx.db.scalar(select(Quotation).join(QuotationVersion, QuotationVersion.quotation_id == Quotation.id).where(
        Quotation.organization_id == ctx.org_id, Quotation.tender_id == tender_id,
        QuotationVersion.cost_estimate_id == estimate.id).order_by(Quotation.created_at.desc()).limit(1))
    if existing is None:
        quotation = Quotation(organization_id=ctx.org_id, tender_id=tender_id, customer_id=workflow.customer_id,
            number=next_number(ctx.db, Quotation, ctx.org_id, prefix="QTN"), status="DRAFT", currency=estimate.currency,
            target_margin=Decimal(str(commercial.get("gross_margin", ZERO))), created_by=ctx.user_id)
        ctx.db.add(quotation); ctx.db.flush(); version_no = 1
    else:
        quotation = existing
        prior = ctx.db.scalar(select(QuotationVersion).where(QuotationVersion.quotation_id == quotation.id).order_by(QuotationVersion.version_no.desc()).limit(1))
        if prior: prior.is_immutable = True
        version_no = (prior.version_no if prior else 0) + 1
    version = QuotationVersion(organization_id=ctx.org_id, quotation_id=quotation.id, version_no=version_no,
        status="DRAFT", subtotal=q_money(proposed_bid), total_estimated_cost=q_money(estimate.total_cost),
        total_selling_price=q_money(proposed_bid), gross_margin_pct=Decimal(str(commercial.get("gross_margin", ZERO))),
        cost_estimate_id=estimate.id, is_immutable=False)
    ctx.db.add(version); ctx.db.flush()
    quoted_items=[]
    for bom in boms:
        line_cost = q_money(by_bom[bom.id]); line_selling = q_money(proposed_bid * line_cost / material_cost)
        quoted_items.append((bom, line_cost, line_selling))
    # Keep the persisted line total exactly equal to the approved snapshot despite money rounding.
    quoted_items[-1] = (quoted_items[-1][0], quoted_items[-1][1], q_money(quoted_items[-1][2] + q_money(proposed_bid) - sum((x[2] for x in quoted_items), ZERO)))
    for bom, line_cost, line_selling in quoted_items:
        ctx.db.add(QuotationItem(organization_id=ctx.org_id, quotation_version_id=version.id, material_id=bom.material_id,
            description=f"Tender BOM item {bom.id}", quantity=bom.quantity, unit=bom.unit,
            unit_cost=q_money(line_cost / bom.quantity) if bom.quantity else ZERO,
            unit_price=q_money(line_selling / bom.quantity) if bom.quantity else ZERO,
            line_estimated_cost=line_cost, line_selling_price=line_selling, available_qty=ZERO, shortage_qty=ZERO))
    workflow.quotation_id = quotation.id
    workflow.submission_status = "NOT_READY"
    record_audit(ctx, "tender.final_quotation.create", "quotation", quotation.id, {"after": {
        "tender_id": str(tender_id), "estimate_id": str(estimate.id), "estimate_version": estimate.version,
        "approval_id": str(approval.id), "quotation_version": version_no, "pricing_source": "APPROVED_AUTHORITATIVE_SNAPSHOT"}})
    ctx.db.commit()
    return {"id": str(quotation.id), "number": quotation.number, "status": quotation.status,
            "version": version_no, "estimate_id": str(estimate.id), "approval_id": str(approval.id),
            "total_selling_price": str(version.total_selling_price), "tax_state": "NOT_RECORDED",
            "submission_status": workflow.submission_status}


@router.get("/{tender_id}/workflow/final-quotation")
def get_final_quotation(tender_id: UUID, ctx: TenantContext = Depends(require("read"))):
    _get_tender(ctx, tender_id)
    quotations=ctx.db.scalars(select(Quotation).where(Quotation.organization_id==ctx.org_id,Quotation.tender_id==tender_id).order_by(Quotation.created_at.desc())).all()
    out=[]
    for quote in quotations:
        versions=ctx.db.scalars(select(QuotationVersion).where(QuotationVersion.quotation_id==quote.id).order_by(QuotationVersion.version_no.desc())).all()
        out.append({"id":str(quote.id),"number":quote.number,"status":quote.status,"customer_id":str(quote.customer_id),"currency":quote.currency,"created_at":quote.created_at.isoformat(),"versions":[{"id":str(v.id),"version":v.version_no,"status":v.status,"estimate_id":str(v.cost_estimate_id) if v.cost_estimate_id else None,"total_cost":str(v.total_estimated_cost),"total_pre_tax":str(v.total_selling_price),"gross_margin":str(v.gross_margin_pct),"immutable":v.is_immutable,"items":[{"description":i.description,"quantity":str(i.quantity),"unit":i.unit,"unit_price":str(i.unit_price),"amount":str(i.line_selling_price)} for i in ctx.db.scalars(select(QuotationItem).where(QuotationItem.quotation_version_id==v.id)).all()]} for v in versions]})
    return {"tax_state":"NOT_RECORDED","items":out}


@router.post("/{tender_id}/workflow/final-quotation/{quotation_id}/finalize")
def finalize_final_quotation(tender_id: UUID, quotation_id: UUID, ctx: TenantContext = Depends(require("quotations:approve"))):
    tender=_get_tender(ctx,tender_id); workflow=_workflow(ctx,tender_id)
    quote=ctx.db.scalar(select(Quotation).where(Quotation.id==quotation_id,Quotation.organization_id==ctx.org_id,Quotation.tender_id==tender_id).with_for_update())
    if quote is None: raise not_found("Tender quotation")
    version=ctx.db.scalar(select(QuotationVersion).where(QuotationVersion.quotation_id==quote.id).order_by(QuotationVersion.version_no.desc()).limit(1).with_for_update())
    if version is None or version.status!="DRAFT" or version.is_immutable: raise conflict("QUOTATION_NOT_FINALIZABLE","Only the current mutable draft quotation version can be finalized")
    estimate=ctx.db.scalar(select(CostEstimate).where(CostEstimate.id==version.cost_estimate_id,CostEstimate.organization_id==ctx.org_id,CostEstimate.status=="APPROVED"))
    if estimate is None: raise bad_request("APPROVED_AUTHORITATIVE_ESTIMATE_REQUIRED","Finalization requires an approved authoritative estimate")
    approval=ctx.db.scalar(select(Approval).where(Approval.organization_id==ctx.org_id,Approval.entity_type=="authoritative_estimate",Approval.entity_id==estimate.id,Approval.status=="APPROVED"))
    if approval is None: raise bad_request("COMMERCIAL_APPROVAL_REQUIRED","Finalization requires persisted commercial approval")
    revalidation=revalidate_authoritative_estimate(tender_id,estimate.id,ctx)
    if revalidation["status"]!="READY_FOR_APPROVAL": raise conflict("REVALIDATION_REQUIRED","Quotation sources require revalidation",revalidation)
    items=ctx.db.scalars(select(QuotationItem).where(QuotationItem.quotation_version_id==version.id)).all()
    if not items or q_money(sum((i.line_selling_price for i in items),ZERO))!=q_money(version.total_selling_price): raise bad_request("QUOTATION_TOTAL_MISMATCH","Quotation lines do not match the approved pre-tax total")
    quote.status="FINALIZED";version.status="FINALIZED";version.is_immutable=True;version.approved_by=ctx.user_id;version.approved_at=datetime.now(timezone.utc)
    if workflow: workflow.quotation_id=quote.id; workflow.submission_status="NOT_READY"
    record_audit(ctx,"tender.final_quotation.finalize","quotation",quote.id,{"after":{"version":version.version_no,"estimate_id":str(estimate.id),"approval_id":str(approval.id)}})
    ctx.db.commit();return {"id":str(quote.id),"status":quote.status,"version":version.version_no,"version_status":version.status,"submission_status":"NOT_READY"}


def _submission_readiness(ctx, tender_id):
    tender=_get_tender(ctx,tender_id); blockers=[]
    quote=ctx.db.scalar(select(Quotation).where(Quotation.organization_id==ctx.org_id,Quotation.tender_id==tender_id,Quotation.status=="FINALIZED"))
    version=ctx.db.scalar(select(QuotationVersion).where(QuotationVersion.quotation_id==quote.id,QuotationVersion.status=="FINALIZED").order_by(QuotationVersion.version_no.desc()).limit(1)) if quote else None
    if not version: blockers.append({"code":"FINALIZED_QUOTATION_REQUIRED"})
    estimate=ctx.db.get(CostEstimate,version.cost_estimate_id) if version and version.cost_estimate_id else None
    if not estimate or estimate.status!="APPROVED": blockers.append({"code":"APPROVED_ESTIMATE_REQUIRED"})
    if estimate and not ctx.db.scalar(select(Approval.id).where(Approval.organization_id==ctx.org_id,Approval.entity_type=="authoritative_estimate",Approval.entity_id==estimate.id,Approval.status=="APPROVED")): blockers.append({"code":"COMMERCIAL_APPROVAL_REQUIRED"})
    if estimate and revalidate_authoritative_estimate(tender_id,estimate.id,ctx)["status"]!="READY_FOR_APPROVAL": blockers.append({"code":"REVALIDATION_REQUIRED"})
    if not tender.customer: blockers.append({"code":"TENDER_CUSTOMER_REQUIRED"})
    if tender.submission_deadline and tender.submission_deadline < datetime.now(timezone.utc): blockers.append({"code":"SUBMISSION_DEADLINE_PASSED"})
    return {"status":"READY_FOR_SUBMISSION" if not blockers else "NOT_READY","blockers":blockers,"quotation_id":str(quote.id) if quote else None,"quotation_version_id":str(version.id) if version else None}

@router.get("/{tender_id}/workflow/submission-readiness")
def submission_readiness(tender_id: UUID, ctx: TenantContext = Depends(require("read"))):
    return _submission_readiness(ctx,tender_id)

@router.post("/{tender_id}/workflow/submissions", status_code=201)
def create_submission_draft(tender_id: UUID, body: SubmissionDraftIn, ctx: TenantContext = Depends(require("tenders:write"))):
    _get_tender(ctx,tender_id); quote=ctx.db.scalar(select(Quotation).where(Quotation.id==body.quotation_id,Quotation.tender_id==tender_id,Quotation.organization_id==ctx.org_id)); version=ctx.db.scalar(select(QuotationVersion).where(QuotationVersion.id==body.quotation_version_id,QuotationVersion.quotation_id==body.quotation_id,QuotationVersion.organization_id==ctx.org_id))
    if not quote or not version: raise not_found("Tender quotation version")
    row=TenderSubmission(organization_id=ctx.org_id,tender_id=tender_id,quotation_id=quote.id,quotation_version_id=version.id,submission_method=body.submission_method,portal_reference=body.portal_reference,acknowledgment_reference=body.acknowledgment_reference,evidence_document_id=body.evidence_document_id,submitted_at=body.submitted_at)
    ctx.db.add(row);ctx.db.commit();return {"id":str(row.id),"status":row.status}

@router.get("/{tender_id}/workflow/submissions")
def submission_history(tender_id: UUID, ctx: TenantContext = Depends(require("read"))):
    _get_tender(ctx,tender_id); rows=ctx.db.scalars(select(TenderSubmission).where(TenderSubmission.tender_id==tender_id,TenderSubmission.organization_id==ctx.org_id).order_by(TenderSubmission.created_at.desc())).all()
    return [{"id":str(x.id),"status":x.status,"quotation_id":str(x.quotation_id),"quotation_version_id":str(x.quotation_version_id),"method":x.submission_method,"portal_reference":x.portal_reference,"acknowledgment_reference":x.acknowledgment_reference,"evidence_document_id":str(x.evidence_document_id) if x.evidence_document_id else None,"submitted_at":x.submitted_at.isoformat() if x.submitted_at else None,"confirmed_at":x.confirmed_at.isoformat() if x.confirmed_at else None} for x in rows]

@router.get("/{tender_id}/workflow/submissions/{submission_id}")
def get_submission(tender_id: UUID, submission_id: UUID, ctx: TenantContext = Depends(require("read"))):
    _get_tender(ctx,tender_id); row=ctx.db.scalar(select(TenderSubmission).where(TenderSubmission.id==submission_id,TenderSubmission.tender_id==tender_id,TenderSubmission.organization_id==ctx.org_id))
    if row is None: raise not_found("Submission")
    return {"id":str(row.id),"status":row.status,"method":row.submission_method,"portal_reference":row.portal_reference,"acknowledgment_reference":row.acknowledgment_reference,"evidence_document_id":str(row.evidence_document_id) if row.evidence_document_id else None,"submitted_at":row.submitted_at.isoformat() if row.submitted_at else None,"parent_submission_id":str(row.parent_submission_id) if row.parent_submission_id else None,"correction_reason":row.correction_reason,"outcome_status":row.outcome_status}

@router.patch("/{tender_id}/workflow/submissions/{submission_id}")
def update_submission_draft(tender_id: UUID, submission_id: UUID, body: SubmissionDraftIn, ctx: TenantContext = Depends(require("tenders:write"))):
    row=ctx.db.scalar(select(TenderSubmission).where(TenderSubmission.id==submission_id,TenderSubmission.tender_id==tender_id,TenderSubmission.organization_id==ctx.org_id).with_for_update())
    if row is None: raise not_found("Submission draft")
    if row.status!="DRAFT": raise conflict("CONFIRMED_SUBMISSION_IMMUTABLE","Confirmed submissions cannot be edited")
    row.submission_method=body.submission_method;row.portal_reference=body.portal_reference;row.acknowledgment_reference=body.acknowledgment_reference;row.submitted_at=body.submitted_at
    if body.evidence_document_id:
        evidence=ctx.db.scalar(select(TenderDocument).where(TenderDocument.id==body.evidence_document_id,TenderDocument.tender_id==tender_id,TenderDocument.organization_id==ctx.org_id))
        if evidence is None: raise bad_request("INVALID_SUBMISSION_EVIDENCE","Evidence must belong to this tender")
        row.evidence_document_id=evidence.id
    ctx.db.commit();return {"id":str(row.id),"status":row.status}

@router.post("/{tender_id}/workflow/submissions/{submission_id}/correction", status_code=201)
def create_submission_correction(tender_id: UUID, submission_id: UUID, body: TenderAllocationReleaseIn, ctx: TenantContext = Depends(require("tenders:write"))):
    prior=ctx.db.scalar(select(TenderSubmission).where(TenderSubmission.id==submission_id,TenderSubmission.tender_id==tender_id,TenderSubmission.organization_id==ctx.org_id).with_for_update())
    if prior is None or prior.status!="CONFIRMED": raise bad_request("CONFIRMED_SUBMISSION_REQUIRED","Only a confirmed submission can be corrected")
    row=TenderSubmission(organization_id=ctx.org_id,tender_id=tender_id,quotation_id=prior.quotation_id,quotation_version_id=prior.quotation_version_id,parent_submission_id=prior.id,correction_reason=body.reason,submission_method=prior.submission_method,portal_reference=prior.portal_reference,acknowledgment_reference=prior.acknowledgment_reference,evidence_document_id=prior.evidence_document_id,submitted_at=prior.submitted_at)
    ctx.db.add(row);record_audit(ctx,"tender.submission.correction","tender_submission",prior.id,{"after":{"correction_id":str(row.id),"reason":body.reason}});ctx.db.commit();return {"id":str(row.id),"status":"DRAFT","parent_submission_id":str(prior.id)}

@router.post("/{tender_id}/workflow/submissions/{submission_id}/confirm")
def confirm_submission(tender_id: UUID, submission_id: UUID, ctx: TenantContext = Depends(require("tenders:write"))):
    ready=_submission_readiness(ctx,tender_id)
    if ready["status"]!="READY_FOR_SUBMISSION": raise conflict("SUBMISSION_NOT_READY","Submission prerequisites are incomplete",ready)
    row=ctx.db.scalar(select(TenderSubmission).where(TenderSubmission.id==submission_id,TenderSubmission.tender_id==tender_id,TenderSubmission.organization_id==ctx.org_id).with_for_update())
    if row is None: raise not_found("Submission draft")
    if row.status!="DRAFT": raise conflict("SUBMISSION_ALREADY_CONFIRMED","Only a draft can be confirmed")
    if not row.submission_method or not row.portal_reference or not row.evidence_document_id: raise bad_request("SUBMISSION_DETAILS_REQUIRED","Method, portal reference and evidence are required")
    evidence=ctx.db.scalar(select(TenderDocument).where(TenderDocument.id==row.evidence_document_id,TenderDocument.tender_id==tender_id,TenderDocument.organization_id==ctx.org_id))
    if evidence is None: raise bad_request("INVALID_SUBMISSION_EVIDENCE","Evidence must belong to this tender")
    row.status="CONFIRMED";row.submitted_by=ctx.user_id;row.confirmed_at=datetime.now(timezone.utc);row.submitted_at=row.submitted_at or row.confirmed_at
    tender=_get_tender(ctx,tender_id); tender.status="BID_SUBMITTED"; workflow=_workflow(ctx,tender_id,create=True);workflow.submission_status="MANUALLY_SUBMITTED";workflow.external_submission_reference=row.portal_reference;workflow.external_submitted_at=row.confirmed_at
    record_audit(ctx,"tender.submission.confirm","tender_submission",row.id,{"after":{"reference":row.portal_reference}});ctx.db.commit();return {"id":str(row.id),"status":row.status}

@router.post("/{tender_id}/workflow/submissions/{submission_id}/outcome")
def record_submission_outcome(tender_id: UUID, submission_id: UUID, body: OutcomeIn, ctx: TenantContext = Depends(require("tenders:approve_bid"))):
    row=ctx.db.scalar(select(TenderSubmission).where(TenderSubmission.id==submission_id,TenderSubmission.tender_id==tender_id,TenderSubmission.organization_id==ctx.org_id).with_for_update())
    if row is None or row.status!="CONFIRMED": raise bad_request("CONFIRMED_SUBMISSION_REQUIRED","Outcome requires a confirmed submission")
    if row.outcome_status is not None:
        raise conflict("OUTCOME_ALREADY_RECORDED", "A recorded outcome is immutable; create a correction/resubmission to record a later decision")
    tender=_get_tender(ctx,tender_id); row.outcome_status=body.status;row.outcome_date=body.outcome_date;row.outcome_reference=body.reference;row.outcome_remarks=body.remarks;row.outcome_value=body.award_value;row.outcome_currency=body.currency;tender.status=body.status
    record_audit(ctx,"tender.submission.outcome","tender_submission",row.id,{"after":{"status":body.status,"reference":body.reference}});ctx.db.commit();return {"id":str(row.id),"outcome_status":row.outcome_status}

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
    source_estimate=ctx.db.get(CostEstimate, version.cost_estimate_id) if version.cost_estimate_id else None
    authoritative=bool(source_estimate and (source_estimate.context or {}).get("calculation_version")=="AUTHORITATIVE_TENDER_V1")
    write(ctx.organization.name, 16, True); write(f"Quotation {quotation.number} · Version {version.version_no}", 18, True); write(f"Tender: {tender.number} — {tender.title}")
    write(f"Customer: {customer.name if customer else 'Not recorded'}"); write("Approved commercial quotation" if authoritative else "DEMONSTRATION COMMERCIAL RATES — NOT APPROVED SUPPLIER QUOTATIONS")
    if tender.is_demo: write("SIMULATED TRAINING DATA — NOT AN OFFICIAL GOVERNMENT TENDER OR SUPPLIER QUOTE.", 9, True)
    y += 8; write("Description | Quantity | Unit | Unit price | Amount", 10, True)
    for item in items: write(f"{item.description[:42]} | {item.quantity} | {item.unit} | {item.unit_price} | {item.line_selling_price}")
    y += 6; write(f"Total pre-tax quotation amount: {quotation.currency} {version.total_selling_price}", 12, True); write("Tax treatment: Not recorded")
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
    tender = _get_tender(ctx, tender_id)
    req = ctx.db.scalar(select(TenderRequirementSnapshot).where(TenderRequirementSnapshot.id == snapshot_id, TenderRequirementSnapshot.tender_id == tender_id, TenderRequirementSnapshot.organization_id == ctx.org_id))
    if req is None: raise not_found("Tender requirement snapshot")
    eligible = Decimal(str(ctx.db.scalar(select(func.coalesce(func.sum(StockLot.on_hand_qty - StockLot.reserved_qty), 0)).where(StockLot.organization_id == ctx.org_id, StockLot.material_id == req.material_id, StockLot.quality_status == "OK")) or 0))
    items = []
    for quote in ctx.db.scalars(select(SupplierQuote).where(SupplierQuote.organization_id == ctx.org_id, SupplierQuote.material_id == req.material_id)).all():
        result = compatible_offer(req, ctx.db.get(OrganizationMaterial, req.material_id), quote, ctx.db.get(OrganizationMaterial, quote.material_id), eligible)
        supplier = ctx.db.get(Supplier, quote.supplier_id)
        allocated = Decimal(str(ctx.db.scalar(select(func.coalesce(func.sum(TenderSupplierSelection.selected_qty), 0)).where(
            TenderSupplierSelection.supplier_quote_id == quote.id, TenderSupplierSelection.status == "SELECTED")) or 0))
        remaining = max(ZERO, Decimal(str(quote.quantity)) - allocated)
        incomplete = []
        if quote.valid_until is None: incomplete.append("offer validity not recorded")
        if not quote.currency: incomplete.append("currency not recorded")
        delivery_risk = bool(tender.submission_deadline and quote.lead_time_days is not None and
                             date.today().fromordinal(date.today().toordinal() + quote.lead_time_days) > tender.submission_deadline.date())
        if quote.valid_until and quote.valid_until < date.today(): comparison_status = "EXPIRED"
        elif not result["compatible"]: comparison_status = "INCOMPATIBLE"
        elif incomplete: comparison_status = "INCOMPLETE"
        elif delivery_risk: comparison_status = "DELIVERY_RISK"
        else: comparison_status = "COMPATIBLE"
        item = {"supplier_quote_id": str(quote.id), "supplier_name": supplier.name if supplier else None,
                "quantity": str(quote.quantity), "unit": quote.unit, "unit_price": str(quote.unit_price),
                "currency": quote.currency, "freight_per_unit": str(quote.freight_per_unit),
                "tax_recoverable": quote.tax_recoverable, "tax_pct": str(quote.tax_pct),
                "payment_terms_days": quote.payment_terms_days, "lead_time_days": quote.lead_time_days,
                "valid_until": str(quote.valid_until) if quote.valid_until else None,
                **{k: str(v) if isinstance(v, Decimal) else v for k, v in result.items()}}
        item["total_landed_cost"] = str(result["landed_cost_per_unit"] * quote.quantity)
        item.update({"allocated_quantity": str(allocated), "available_unallocated_quantity": str(remaining),
                     "comparison_status": comparison_status, "delivery_status": "DELIVERY_RISK" if delivery_risk else "NOT_RECORDED" if quote.lead_time_days is None else "RECORDED",
                     "incomplete_fields": incomplete, "coverage_quantity": str(min(remaining, result["shortage_qty"]))})
        items.append(item)
    return {"snapshot_id": str(snapshot_id), "items": items}


@router.get("/{tender_id}/workflow/estimation-readiness")
def tender_estimation_readiness(tender_id: UUID, ctx: TenantContext = Depends(require("read"))):
    """Read-only commercial coverage; it never creates or approves an estimate."""
    tender = _get_tender(ctx, tender_id)
    workflow = _workflow(ctx, tender_id)
    if workflow is None or workflow.bom_version_id is None:
        return {"status": "BLOCKED", "reason": "BOM is required", "items": []}
    items = []
    for bom in ctx.db.scalars(select(BOMItem).where(BOMItem.bom_version_id == workflow.bom_version_id)).all():
        analysis = analyze_bom_item_inventory(ctx.db, ctx.org_id, tender, bom)
        selected = Decimal(str(ctx.db.scalar(select(func.coalesce(func.sum(TenderSupplierSelection.selected_qty), 0)).where(
            TenderSupplierSelection.tender_requirement_snapshot_id == bom.tender_requirement_snapshot_id,
            TenderSupplierSelection.status == "SELECTED")) or 0))
        uncovered = max(ZERO, Decimal(str(bom.quantity)) - Decimal(str(analysis["eligible_quantity"])) - selected)
        items.append({"snapshot_id": str(bom.tender_requirement_snapshot_id) if bom.tender_requirement_snapshot_id else None,
                      "required_quantity": str(bom.quantity), "unit": bom.unit, "inventory_covered_quantity": str(analysis["eligible_quantity"]),
                      "supplier_covered_quantity": str(selected), "uncovered_quantity": str(uncovered),
                      "status": analysis["status"], "missing_cost_inputs": ["supplier allocation"] if uncovered > ZERO else [],
                      "blockers": analysis["reasons"]})
    return {"tender_id": str(tender_id), "status": "READY" if all(Decimal(x["uncovered_quantity"]) == ZERO and x["status"] != "BLOCKED" for x in items) else "INCOMPLETE", "items": items}


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
    exists = ctx.db.scalar(select(TenderSupplierSelection.id).where(TenderSupplierSelection.tender_requirement_snapshot_id == snapshot_id, TenderSupplierSelection.supplier_quote_id == quote.id, TenderSupplierSelection.status == "SELECTED"))
    if exists: raise conflict("DUPLICATE_ALLOCATION", "Supplier offer already allocated to this requirement")
    used = Decimal(str(ctx.db.scalar(select(func.coalesce(func.sum(TenderSupplierSelection.selected_qty), 0)).where(TenderSupplierSelection.tender_requirement_snapshot_id == snapshot_id, TenderSupplierSelection.status == "SELECTED")) or 0))
    if body.selected_qty + used > check["shortage_qty"]: raise bad_request("OVER_ALLOCATION", "Allocation exceeds current procurement shortage")
    quote_used = Decimal(str(ctx.db.scalar(select(func.coalesce(func.sum(TenderSupplierSelection.selected_qty), 0)).where(
        TenderSupplierSelection.supplier_quote_id == quote.id, TenderSupplierSelection.status == "SELECTED")) or 0))
    if body.selected_qty + quote_used > quote.quantity: raise bad_request("QUOTE_QUANTITY_EXCEEDED", "Allocation exceeds remaining supplier offer quantity")
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
                          registry_source_id: UUID | None = Form(None),
                          official_source_url: str | None = Form(None),
                          authorization_evidence_reference: str | None = Form(None),
                          external_tender_reference: str | None = Form(None),
                          ctx: TenantContext = Depends(require("tenders:write"))):
    """Upload a document, optionally recording approved manual-source provenance.

    The registry path is intentionally restricted to a profile whose permitted
    method is MANUAL_UPLOAD.  Existing document uploads remain supported and
    do not acquire an invented source record.
    """
    t = _get_tender(ctx, tender_id)
    content = await file.read()
    if len(content) > settings.request_body_limit_bytes:
        raise bad_request("FILE_TOO_LARGE", "File exceeds the upload size limit")
    safe_name = os.path.basename(file.filename or "document.pdf")
    extension = _validate_tender_document(safe_name, content)
    profile = None
    if registry_source_id is not None:
        from app.services.tender_source_registry import (
            TenderSourceRegistryError, load_visible_registry_source,
        )
        try:
            profile = load_visible_registry_source(
                ctx.db, organization_id=ctx.org_id, registry_source_id=registry_source_id)
        except TenderSourceRegistryError as exc:
            raise bad_request("INVALID_TENDER_SOURCE", str(exc)) from exc
        if profile.profile.permitted_ingestion_method != "MANUAL_UPLOAD":
            raise bad_request("INVALID_TENDER_SOURCE", "Selected source is not approved for manual tender upload")
    os.makedirs(os.path.join(settings.upload_dir, str(ctx.org_id)), exist_ok=True)
    storage_key = f"{ctx.org_id}/{t.id}/{uuid_mod.uuid4().hex}_{safe_name}"
    path = os.path.join(settings.upload_dir, storage_key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "wb") as fh:
            fh.write(content)
        doc = TenderDocument(
            organization_id=ctx.org_id, tender_id=t.id, file_name=safe_name,
            storage_key=storage_key, mime_type=next(iter(TENDER_DOCUMENT_TYPES[extension])), size_bytes=len(content),
            status="EXTRACTING", processing_status="QUEUED", uploaded_by=ctx.user_id)
        ctx.db.add(doc)
        ctx.db.flush()
        if profile is not None:
            try:
                provenance, _ = record_provenance(
                    ctx.db, organization_id=ctx.org_id, tender_id=t.id,
                    registry_source_id=profile.source.id, provider_name=profile.source.name,
                    source_type="MANUAL_UPLOAD", provider_record_id=f"manual-upload:{doc.id}",
                    data_classification=profile.profile.default_data_classification,
                    authorization_status="AUTHORIZED",
                    official_source_url=official_source_url,
                    external_tender_reference=external_tender_reference,
                    authorization_evidence_reference=authorization_evidence_reference,
                    source_status="DOCUMENT_UPLOADED",
                )
            except TenderSourceEventError as exc:
                raise bad_request("SOURCE_PROVENANCE_REJECTED", str(exc)) from exc
            record_audit(ctx, "tender.source_provenance.manual_upload", "tender_source_provenance", provenance.id,
                         {"after": {"registry_source_id": str(profile.source.id), "classification": provenance.data_classification}})
        record_audit(ctx, "tender.upload_document", "tender_document", doc.id,
                     {"after": {"file_name": safe_name, "size_bytes": len(content), "extraction": "QUEUED"}})
        ctx.db.commit()
        try:
            _queue_document_extraction(tender_id=t.id, document_id=doc.id)
        except Exception:
            # The source document is already persisted.  Make the existing
            # manual retry action available rather than failing or losing it.
            log.exception("tender_document_extraction_enqueue_failed document_id=%s", doc.id)
            doc.status = "UPLOADED"
            doc.processing_status = "PENDING"
            ctx.db.commit()
        return TenderDocumentOut.model_validate(doc)
    except Exception:
        ctx.db.rollback()
        if os.path.isfile(path):
            os.unlink(path)
        raise


@router.get("/{tender_id}/documents", response_model=list[TenderDocumentOut])
def list_documents(tender_id: UUID, ctx: TenantContext = Depends(require("read"))):
    _get_tender(ctx, tender_id)
    rows = ctx.db.scalars(select(TenderDocument).where(
        TenderDocument.tender_id == tender_id,
        TenderDocument.organization_id == ctx.org_id)).all()
    return [TenderDocumentOut.model_validate(r) for r in rows]


@router.get("/{tender_id}/source-provenance", response_model=list[TenderSourceProvenanceOut])
def list_tender_source_provenance(tender_id: UUID, ctx: TenantContext = Depends(require("read"))):
    _get_tender(ctx, tender_id)
    return [TenderSourceProvenanceOut.model_validate(row) for row in ctx.db.scalars(select(TenderSourceProvenance).where(
        TenderSourceProvenance.tender_id == tender_id,
        TenderSourceProvenance.organization_id == ctx.org_id,
    ).order_by(TenderSourceProvenance.created_at.desc())).all()]


@router.get("/{tender_id}/revisions", response_model=list[TenderRevisionOut])
def list_tender_revisions(tender_id: UUID, ctx: TenantContext = Depends(require("read"))):
    _get_tender(ctx, tender_id)
    return [TenderRevisionOut.model_validate(row) for row in ctx.db.scalars(select(TenderRevision).where(
        TenderRevision.tender_id == tender_id,
        TenderRevision.organization_id == ctx.org_id,
    ).order_by(TenderRevision.detected_at.desc(), TenderRevision.created_at.desc())).all()]


@router.post("/{tender_id}/revisions/{revision_id}/acknowledge", response_model=TenderRevisionOut)
def acknowledge_tender_revision(tender_id: UUID, revision_id: UUID, body: RevisionAcknowledgementIn,
                                ctx: TenantContext = Depends(require("tenders:write"))):
    _get_tender(ctx, tender_id)
    row = ctx.db.scalar(select(TenderRevision).where(TenderRevision.id == revision_id,
        TenderRevision.tender_id == tender_id, TenderRevision.organization_id == ctx.org_id))
    if row is None:
        raise not_found("Tender revision")
    if row.acknowledged_at is None:
        row.acknowledged_by = ctx.user_id
        row.acknowledged_at = datetime.now(timezone.utc)
        row.review_status = "ACKNOWLEDGED"
        record_audit(ctx, "tender.revision.acknowledge", "tender_revision", row.id,
                     {"after": {"note": body.acknowledgement_note or ""}})
        ctx.db.commit()
    return TenderRevisionOut.model_validate(row)


@router.get("/{tender_id}/documents/{document_id}/extraction-status")
def extraction_status(tender_id: UUID, document_id: UUID, ctx: TenantContext = Depends(require("read"))):
    _get_tender(ctx, tender_id)
    doc = ctx.db.scalar(select(TenderDocument).where(TenderDocument.id == document_id,
        TenderDocument.tender_id == tender_id, TenderDocument.organization_id == ctx.org_id))
    if doc is None:
        raise not_found("Tender document")
    job = ctx.db.scalars(select(AIJob).where(AIJob.organization_id == ctx.org_id,
        AIJob.job_type == "TENDER_EXTRACTION", AIJob.input["tender_document_id"].astext == str(document_id))
        .order_by(AIJob.created_at.desc()).limit(1)).first()
    return {"document_id": str(doc.id), "status": doc.status, "processing_status": doc.processing_status,
            "parser_version": doc.parser_version, "content_checksum": doc.content_checksum,
            "processed_at": doc.processed_at.isoformat() if doc.processed_at else None,
            "job": None if job is None else {"id": str(job.id), "status": job.status,
                    "output": job.output, "error": job.error, "completed_at": job.completed_at.isoformat() if job.completed_at else None}}


@router.post("/{tender_id}/documents/{document_id}/extract", status_code=202)
def extract_document(tender_id: UUID, document_id: UUID,
                     ctx: TenantContext = Depends(require("tenders:write"))):
    """Run rule-based BOQ extraction. All results land as PENDING review with evidence —
    no value is auto-confirmed. (Celery worker runs the same code path when deployed.)"""
    _get_tender(ctx, tender_id)
    try:
        result = extract_and_persist(ctx.db, organization_id=ctx.org_id, tender_id=tender_id,
                                     document_id=document_id, created_by=ctx.user_id)
    except TenderExtractionError as exc:
        raise bad_request("EXTRACTION_FAILED", str(exc))
    record_audit(ctx, "tender.extract", "tender_document", document_id,
                 {"after": {"candidates": result["candidates"], "idempotent": result["idempotent"]}})
    ctx.db.commit()
    return result


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
