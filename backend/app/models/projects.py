import uuid
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPKMixin


class Project(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_project_code"),)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    project_type: Mapped[str] = mapped_column(String(32), nullable=False)  # RAILWAY/BRIDGE/BUILDING/INDUSTRIAL/FABRICATION
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE", index=True)
    estimated_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class Tender(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "tenders"
    __table_args__ = (UniqueConstraint("organization_id", "number", name="uq_tender_number"),)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    number: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    customer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    project_type: Mapped[str] = mapped_column(String(32), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    submission_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    estimated_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT", index=True)
    # Discovery provenance is intentionally independent from a tenant's commercial data.
    # These nullable/defaulted fields keep all existing tender records backward compatible.
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    data_classification: Mapped[str] = mapped_column(String(32), default="OPERATIONAL", nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(32), default="USER_UPLOAD", nullable=False)
    original_source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    publication_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rate_approval_status: Mapped[str] = mapped_column(String(32), default="NOT_APPLICABLE", nullable=False)


class TenderDocument(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "tender_documents"
    tender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="UPLOADED")  # UPLOADED/EXTRACTING/EXTRACTED/REVIEWED/FAILED
    # The legacy status is retained for existing clients.  These fields make
    # processing reproducible without disclosing the storage location.
    processing_status: Mapped[str] = mapped_column(String(32), default="PENDING", nullable=False, index=True)
    content_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    parser_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)


class TenderSourceProvenance(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    """Authorized provenance for one tenant tender; never contains provider secrets."""
    __tablename__ = "tender_source_provenance"
    __table_args__ = (
        UniqueConstraint("organization_id", "provider_name", "provider_record_id", name="uq_tender_source_provider_record"),
    )
    tender_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False, index=True)
    # Nullable to preserve all legacy/manual provenance records.  Snapshot
    # fields below remain immutable evidence even if registry policy changes.
    registry_source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("market_sources.id", ondelete="SET NULL"), nullable=True, index=True)
    provider_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    official_source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    external_tender_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_record_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    authorization_status: Mapped[str] = mapped_column(String(32), nullable=False, default="UNVERIFIED")
    authorization_evidence_reference: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    data_classification: Mapped[str] = mapped_column(String(32), nullable=False, default="DEMO")
    first_discovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_successfully_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    normalized_payload_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    retrieval_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class TenderRevision(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    """Evidence-backed source event. It never replaces approved commercial inputs."""
    __tablename__ = "tender_revisions"
    __table_args__ = (
        UniqueConstraint("organization_id", "source_provenance_id", "event_fingerprint", name="uq_tender_revision_event"),
    )
    tender_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False, index=True)
    source_provenance_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tender_source_provenance.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    previous_value: Mapped[dict] = mapped_column(JSONB, default=dict)
    new_value: Mapped[dict] = mapped_column(JSONB, default=dict)
    related_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tender_documents.id", ondelete="SET NULL"), nullable=True)
    document_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evidence_reference: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    evidence_page_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING_REVIEW")
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    event_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)


class BOQItem(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "boq_items"
    tender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False, index=True)
    tender_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tender_documents.id", ondelete="SET NULL"), nullable=True)
    line_no: Mapped[str | None] = mapped_column(String(32), nullable=True)
    raw_description: Mapped[str] = mapped_column(Text, nullable=False)
    form: Mapped[str | None] = mapped_column(String(32), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(64), nullable=True)
    specification: Mapped[dict] = mapped_column(JSONB, default=dict)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    material_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization_materials.id", ondelete="SET NULL"), nullable=True)
    review_status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)  # PENDING/CONFIRMED/REJECTED
    source: Mapped[str] = mapped_column(String(8), default="MANUAL")  # MANUAL/AI
    page_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ProjectRequirement(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "project_requirements"
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization_materials.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), default="MT")
    required_by: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str] = mapped_column(String(8), default="MANUAL")  # BOQ/MANUAL


class ExtractionEvidence(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "extraction_evidence"
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tender_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    ai_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cell_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    field: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_value: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_value: Mapped[dict] = mapped_column(JSONB, default=dict)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    review_status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    warnings: Mapped[dict] = mapped_column(JSONB, default=dict)


class TenderRequirementSnapshot(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    """Immutable commercial input copied only from confirmed BOQ lines."""
    __tablename__ = "tender_requirement_snapshots"
    __table_args__ = (UniqueConstraint("tender_id", "version", "source_boq_item_id", name="uq_tender_req_snapshot"),)
    tender_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenders.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_boq_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("boq_items.id", ondelete="RESTRICT"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    material_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organization_materials.id", ondelete="RESTRICT"), nullable=False)
    form: Mapped[str | None] = mapped_column(String(32), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(64), nullable=True)
    specification: Mapped[dict] = mapped_column(JSONB, default=dict)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    wastage_pct: Mapped[Decimal] = mapped_column(Numeric(8, 6), default=0)
    engineering_status: Mapped[str] = mapped_column(String(16), default="APPROVED")
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TenderWorkflow(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    """Tenant-scoped orchestration record; legacy tender records remain independent."""
    __tablename__ = "tender_workflows"
    __table_args__ = (UniqueConstraint("organization_id", "tender_id", name="uq_tender_workflow"),)
    tender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False, index=True)
    requirement_snapshot_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bom_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bom_versions.id", ondelete="SET NULL"), nullable=True, index=True)
    cost_estimate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cost_estimates.id", ondelete="SET NULL"), nullable=True, index=True)
    quotation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotations.id", ondelete="SET NULL"), nullable=True, index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True)
    use_demo_commercial_rates: Mapped[bool] = mapped_column(Boolean, default=False)
    submission_status: Mapped[str] = mapped_column(String(24), default="NOT_READY", index=True)
    external_submission_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    external_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submission_notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class TenderSubmission(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    """Auditable manual tender submission record; CONFIRMED rows are immutable."""
    __tablename__ = "tender_submissions"
    tender_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenders.id", ondelete="RESTRICT"), nullable=False, index=True)
    quotation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("quotations.id", ondelete="RESTRICT"), nullable=False)
    quotation_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("quotation_versions.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT", index=True)
    submission_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    portal_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    acknowledgment_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    evidence_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tender_documents.id", ondelete="RESTRICT"), nullable=True)
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    outcome_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    outcome_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    outcome_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    outcome_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    outcome_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_submission_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tender_submissions.id", ondelete="RESTRICT"), nullable=True, index=True)
    correction_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class TenderSupplierSelection(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "tender_supplier_selections"
    __table_args__ = (UniqueConstraint("tender_requirement_snapshot_id", "supplier_quote_id", name="uq_tender_supplier_selection"),)
    tender_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenders.id", ondelete="RESTRICT"), nullable=False, index=True)
    tender_requirement_snapshot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tender_requirement_snapshots.id", ondelete="RESTRICT"), nullable=False, index=True)
    supplier_quote_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("supplier_quotes.id", ondelete="RESTRICT"), nullable=False)
    selected_qty: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    freight_per_unit: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    nonrecoverable_tax_per_unit: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    landed_cost_per_unit: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    delivery_terms: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="SELECTED", index=True)
    selected_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class TenderInventoryAllocation(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    """Tender-BOM stock lock plus valuation snapshot; never inferred at estimate time."""
    __tablename__ = "tender_inventory_allocations"
    tender_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenders.id", ondelete="RESTRICT"), nullable=False, index=True)
    bom_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bom_versions.id", ondelete="RESTRICT"), nullable=False)
    bom_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bom_items.id", ondelete="RESTRICT"), nullable=False, index=True)
    stock_lot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stock_lots.id", ondelete="RESTRICT"), nullable=False)
    reservation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("reservations.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    valuation_rate: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    valuation_source: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
