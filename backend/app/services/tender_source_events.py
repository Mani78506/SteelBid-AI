"""Internal, evidence-gated tender source event persistence.

These functions deliberately are not FastAPI endpoints.  A future authorized
ingestion adapter may call them after it has retrieved source evidence; the
public tender API remains read/acknowledge-only.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.projects import Tender, TenderRevision, TenderSourceProvenance
from app.services.tender_source_registry import (
    TenderSourceRegistryError, load_visible_registry_source,
    validate_provenance_registry_source,
)

CLASSIFICATIONS = {"AUTHENTIC", "DEMO", "FIXTURE_TEST"}
EVENT_TYPES = {"NEW_NOTICE", "CORRIGENDUM", "DEADLINE_CHANGED", "DOCUMENT_REVISED", "BOQ_REVISED", "CANCELLED", "RETENDERED", "AWARD_NOTICE", "OTHER"}


class TenderSourceEventError(ValueError):
    pass


def _tender(db: Session, organization_id: UUID, tender_id: UUID) -> Tender:
    row = db.scalar(select(Tender).where(Tender.id == tender_id, Tender.organization_id == organization_id))
    if row is None:
        raise TenderSourceEventError("Tender is not owned by the supplied organization")
    return row


def record_provenance(db: Session, *, organization_id: UUID, tender_id: UUID,
                      provider_name: str, source_type: str, provider_record_id: str,
                      data_classification: str, authorization_status: str = "UNVERIFIED",
                      official_source_url: str | None = None,
                      external_tender_reference: str | None = None,
                      authorization_evidence_reference: str | None = None,
                      registry_source_id: UUID | None = None,
                      first_discovered_at: datetime | None = None,
                      last_retrieved_at: datetime | None = None,
                      last_successfully_checked_at: datetime | None = None,
                      normalized_payload_checksum: str | None = None,
                      source_status: str = "PENDING", retrieval_error: str | None = None) -> tuple[TenderSourceProvenance, bool]:
    """Return an existing source record or persist one guarded by source evidence."""
    _tender(db, organization_id, tender_id)
    classification = data_classification.upper()
    authorization = authorization_status.upper()
    if classification not in CLASSIFICATIONS:
        raise TenderSourceEventError("Unsupported source classification")
    if not provider_name.strip() or not source_type.strip() or not provider_record_id.strip():
        raise TenderSourceEventError("Provider name, source type and provider record ID are required")
    if classification == "AUTHENTIC" and (authorization != "AUTHORIZED" or not official_source_url or not authorization_evidence_reference):
        raise TenderSourceEventError("AUTHENTIC sources require AUTHORIZED status, official URL and authorization evidence")
    if registry_source_id is not None:
        try:
            registry = load_visible_registry_source(
                db, organization_id=organization_id, registry_source_id=registry_source_id)
            validate_provenance_registry_source(
                registry, data_classification=classification,
                authorization_status=authorization, official_source_url=official_source_url,
                source_type=source_type,
            )
        except TenderSourceRegistryError as exc:
            raise TenderSourceEventError(str(exc)) from exc
    # Classification is explicit and never inferred from a provider name.
    existing = db.scalar(select(TenderSourceProvenance).where(
        TenderSourceProvenance.organization_id == organization_id,
        TenderSourceProvenance.provider_name == provider_name,
        TenderSourceProvenance.provider_record_id == provider_record_id,
    ))
    if existing is not None:
        if existing.tender_id != tender_id:
            raise TenderSourceEventError("Provider record is already linked to another tender in this organization")
        return existing, False
    row = TenderSourceProvenance(
        organization_id=organization_id, tender_id=tender_id, registry_source_id=registry_source_id, provider_name=provider_name,
        source_type=source_type, provider_record_id=provider_record_id,
        data_classification=classification, authorization_status=authorization,
        official_source_url=official_source_url, external_tender_reference=external_tender_reference,
        authorization_evidence_reference=authorization_evidence_reference,
        first_discovered_at=first_discovered_at or datetime.now(timezone.utc),
        last_retrieved_at=last_retrieved_at, last_successfully_checked_at=last_successfully_checked_at,
        normalized_payload_checksum=normalized_payload_checksum, source_status=source_status,
        retrieval_error=retrieval_error,
    )
    db.add(row); db.flush()
    return row, True


def revision_fingerprint(*, source_provenance_id: UUID | None, event_type: str, published_at: datetime | None,
                         effective_at: datetime | None, previous_value: dict | None, new_value: dict | None,
                         document_checksum: str | None, evidence_reference: str | None, evidence_page_ref: str | None) -> str:
    payload = {"source_provenance_id": str(source_provenance_id) if source_provenance_id else None,
               "event_type": event_type.upper(), "published_at": published_at.isoformat() if published_at else None,
               "effective_at": effective_at.isoformat() if effective_at else None, "previous_value": previous_value or {},
               "new_value": new_value or {}, "document_checksum": document_checksum,
               "evidence_reference": evidence_reference, "evidence_page_ref": evidence_page_ref}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def record_revision(db: Session, *, organization_id: UUID, tender_id: UUID, source_provenance_id: UUID | None,
                    event_type: str, detected_at: datetime | None = None, published_at: datetime | None = None,
                    effective_at: datetime | None = None, previous_value: dict | None = None,
                    new_value: dict | None = None, related_document_id: UUID | None = None,
                    document_checksum: str | None = None, evidence_reference: str | None = None,
                    evidence_page_ref: str | None = None) -> tuple[TenderRevision, bool]:
    """Persist an immutable, evidence-backed event without altering tender workflow data."""
    _tender(db, organization_id, tender_id)
    kind = event_type.upper()
    if kind not in EVENT_TYPES:
        raise TenderSourceEventError("Unsupported tender revision event type")
    if source_provenance_id is not None:
        source = db.scalar(select(TenderSourceProvenance).where(TenderSourceProvenance.id == source_provenance_id,
            TenderSourceProvenance.tender_id == tender_id, TenderSourceProvenance.organization_id == organization_id))
        if source is None:
            raise TenderSourceEventError("Source provenance is not owned by this tender and organization")
    fingerprint = revision_fingerprint(source_provenance_id=source_provenance_id, event_type=kind,
        published_at=published_at, effective_at=effective_at, previous_value=previous_value, new_value=new_value,
        document_checksum=document_checksum, evidence_reference=evidence_reference, evidence_page_ref=evidence_page_ref)
    existing = db.scalar(select(TenderRevision).where(TenderRevision.organization_id == organization_id,
        TenderRevision.source_provenance_id == source_provenance_id, TenderRevision.event_fingerprint == fingerprint))
    if existing is not None:
        return existing, False
    row = TenderRevision(organization_id=organization_id, tender_id=tender_id, source_provenance_id=source_provenance_id,
        event_type=kind, detected_at=detected_at or datetime.now(timezone.utc), published_at=published_at,
        effective_at=effective_at, previous_value=previous_value or {}, new_value=new_value or {},
        related_document_id=related_document_id, document_checksum=document_checksum,
        evidence_reference=evidence_reference, evidence_page_ref=evidence_page_ref, event_fingerprint=fingerprint)
    db.add(row); db.flush()
    return row, True
