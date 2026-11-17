"""Single persisted tender-document extraction path for HTTP and Celery.

The caller supplies the already-authorized organization identifier.  This keeps
authorization at the API boundary while allowing the worker to apply exactly the
same tenant fence and persistence rules.
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ai.extraction import detect_injection_warnings, extract_boq_candidates, extract_text_pages
from app.config import get_settings
from app.models.materials import OrganizationMaterial
from app.models.ops import AIJob
from app.models.projects import BOQItem, ExtractionEvidence, Tender, TenderDocument
from app.services.tender_inventory import mapping_compatibility

PARSER_VERSION = "document-ai-boq-v2"
SUPPORTED_SUFFIXES = {".pdf", ".xlsx"}


class TenderExtractionError(ValueError):
    pass


def _load(db: Session, *, organization_id: UUID, tender_id: UUID, document_id: UUID) -> tuple[Tender, TenderDocument]:
    tender = db.scalar(select(Tender).where(Tender.id == tender_id, Tender.organization_id == organization_id))
    document = db.scalar(select(TenderDocument).where(
        TenderDocument.id == document_id, TenderDocument.tender_id == tender_id,
        TenderDocument.organization_id == organization_id,
    ))
    if tender is None or document is None:
        raise TenderExtractionError("Tender document was not found in the active organization")
    return tender, document


def _source_path(document: TenderDocument) -> str:
    path = os.path.join(get_settings().upload_dir, document.storage_key)
    if not os.path.isfile(path):
        raise TenderExtractionError("Document bytes are not available in configured storage")
    if Path(document.file_name).suffix.lower() not in SUPPORTED_SUFFIXES:
        raise TenderExtractionError("Only PDF and XLSX tender documents can be extracted")
    return path


def _latest_job(db: Session, organization_id: UUID, document_id: UUID) -> AIJob | None:
    return db.scalars(select(AIJob).where(
        AIJob.organization_id == organization_id,
        AIJob.job_type == "TENDER_EXTRACTION",
        AIJob.input["tender_document_id"].astext == str(document_id),
    ).order_by(AIJob.created_at.desc()).limit(1)).first()


def extract_and_persist(db: Session, *, organization_id: UUID, tender_id: UUID, document_id: UUID,
                        created_by: UUID | None = None, retry: bool = False) -> dict:
    """Extract one document exactly once for its bytes/parser version.

    Retrying a failed document first removes only prior *unreviewed AI* output.
    Reviewed rows are deliberately never deleted or overwritten.
    """
    _, document = _load(db, organization_id=organization_id, tender_id=tender_id, document_id=document_id)
    path = _source_path(document)
    checksum = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    prior = _latest_job(db, organization_id, document_id)
    if document.processing_status in {"COMPLETED", "COMPLETED_WITH_WARNINGS"} and document.content_checksum == checksum and document.parser_version == PARSER_VERSION:
        return {"job_id": str(prior.id) if prior else None, "status": "SUCCEEDED", "candidates": 0, "idempotent": True}
    if document.processing_status == "PROCESSING" and not retry:
        raise TenderExtractionError("Document extraction is already processing")

    job = AIJob(organization_id=organization_id, job_type="TENDER_EXTRACTION", status="RUNNING",
                input={"tender_document_id": str(document.id), "parser_version": PARSER_VERSION}, created_by=created_by)
    db.add(job)
    document.status = "EXTRACTING"
    document.processing_status = "PROCESSING"
    document.content_checksum = checksum
    document.parser_version = PARSER_VERSION
    db.commit()

    try:
        # A retry may replace only non-reviewed machine candidates for this exact document.
        pending_ids = select(BOQItem.id).where(
            BOQItem.organization_id == organization_id, BOQItem.tender_document_id == document.id,
            BOQItem.source == "AI", BOQItem.review_status == "PENDING",
        )
        db.execute(delete(ExtractionEvidence).where(
            ExtractionEvidence.organization_id == organization_id,
            ExtractionEvidence.document_id == document.id,
            ExtractionEvidence.review_status == "PENDING",
        ))
        db.execute(delete(BOQItem).where(BOQItem.id.in_(pending_ids)))
        db.flush()

        total = 0
        warnings = 0
        extraction_methods: set[str] = set()
        for page_no, text in extract_text_pages(path):
            injection_warnings = detect_injection_warnings(text)
            candidates, method, extraction_warnings = extract_boq_candidates(text)
            extraction_methods.add(method)
            for candidate in candidates:
                material_id = None
                if candidate["form"] and candidate["grade"]:
                    material = db.scalar(select(OrganizationMaterial).where(
                        OrganizationMaterial.organization_id == organization_id,
                        OrganizationMaterial.form == candidate["form"],
                        OrganizationMaterial.grade == candidate["grade"],
                        OrganizationMaterial.base_unit == candidate["unit"],
                    ).limit(1))
                    requirement = SimpleNamespace(form=candidate["form"], grade=candidate["grade"],
                                                  unit=candidate["unit"], specification=candidate["specification"])
                    # Form/grade alone is never enough: an ISMB 300 must not be
                    # silently mapped to an ISMB 200, for example.  Leave the
                    # candidate unmapped for human review when compatibility is
                    # not exact under the same rule used by BOM/inventory.
                    material_id = material.id if material and not mapping_compatibility(material, requirement) else None
                boq = BOQItem(
                    organization_id=organization_id, tender_id=tender_id, tender_document_id=document.id,
                    line_no=str(total + 1), raw_description=candidate["raw_description"], form=candidate["form"],
                    grade=candidate["grade"], specification=candidate["specification"],
                    quantity=Decimal(candidate["quantity"]) if candidate["quantity"] else None,
                    unit=candidate["unit"], material_id=material_id, review_status="PENDING", source="AI",
                    page_ref=f"p.{page_no}",
                )
                db.add(boq); db.flush()
                db.add(ExtractionEvidence(
                    organization_id=organization_id, document_id=document.id, ai_job_id=job.id, page=page_no,
                    field="boq_line", raw_value=candidate["raw_description"],
                    normalized_value={"quantity": candidate["quantity"], "unit": candidate["unit"],
                                      "form": candidate["form"], "grade": candidate["grade"],
                                      "boq_item_id": str(boq.id), "parser_version": PARSER_VERSION},
                    confidence=Decimal(candidate["confidence"]), review_status="PENDING",
                    warnings={key: value for key, value in {
                        "injection": injection_warnings or None,
                        "extraction": extraction_warnings or candidate.get("warnings") or None,
                        "method": method,
                    }.items() if value is not None},
                ))
                warnings += bool(injection_warnings or extraction_warnings or candidate.get("warnings"))
                total += 1
        if total == 0:
            raise TenderExtractionError(
                "No reviewable BOQ lines were found. Use a text-searchable PDF or XLSX, "
                "or re-upload a clearer document; no BOQ records were created."
            )
        document.status = "EXTRACTED"
        document.processing_status = "COMPLETED_WITH_WARNINGS" if warnings else "COMPLETED"
        document.processed_at = datetime.now(timezone.utc)
        job.status = "SUCCEEDED"
        job.output = {"candidates": total, "parser_version": PARSER_VERSION, "checksum": checksum,
                      "warnings": warnings, "extraction_methods": sorted(extraction_methods)}
        job.completed_at = document.processed_at
        db.commit()
        return {"job_id": str(job.id), "status": job.status, "candidates": total, "idempotent": False}
    except Exception as exc:
        document.status = "FAILED"; document.processing_status = "FAILED"; document.processed_at = datetime.now(timezone.utc)
        job.status = "FAILED"; job.error = str(exc)[:2000]; job.completed_at = document.processed_at
        db.commit()
        if isinstance(exc, TenderExtractionError):
            raise
        raise TenderExtractionError(f"Extraction failed: {exc}") from exc
