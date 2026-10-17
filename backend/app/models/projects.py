import uuid
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
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


class TenderDocument(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "tender_documents"
    tender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="UPLOADED")  # UPLOADED/EXTRACTING/EXTRACTED/REVIEWED/FAILED
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)


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
