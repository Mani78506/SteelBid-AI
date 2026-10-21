import uuid
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDPKMixin


class PriceSource(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "price_sources"
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), default="SYNTHETIC")  # SYNTHETIC/MANUAL/PROVIDER
    provider_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class MarketSource(Base, UUIDPKMixin, TimestampMixin):
    """A reviewed reference source; observations are never published from this record alone."""
    __tablename__ = "market_sources"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_market_source_org_name"),
        CheckConstraint("license_status IN ('PENDING','APPROVED','RESTRICTED','EXPIRED')", name="ck_market_source_license"),
        CheckConstraint("visibility IN ('OWNER_ONLY','ENTITLED','GLOBAL')", name="ck_market_source_visibility"),
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    provenance_classification: Mapped[str] = mapped_column(String(32), nullable=False)  # OFFICIAL_REFERENCE/MANUAL/PROVIDER
    reference_url: Mapped[str | None] = mapped_column(String(2048))
    document_reference: Mapped[str | None] = mapped_column(String(512))
    attribution_text: Mapped[str] = mapped_column(String(1000), nullable=False)
    license_status: Mapped[str] = mapped_column(String(32), nullable=False)  # PENDING/APPROVED/RESTRICTED
    usage_restrictions: Mapped[str | None] = mapped_column(String(2000))
    publication_frequency: Mapped[str | None] = mapped_column(String(64))
    visibility: Mapped[str] = mapped_column(String(24), nullable=False, default="OWNER_ONLY")  # OWNER_ONLY/ENTITLED/GLOBAL
    redistribution_permitted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class MarketImportBatch(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "market_import_batches"
    __table_args__ = (
        CheckConstraint("status IN ('DRAFT','VALIDATED','PENDING_APPROVAL','APPROVED','REJECTED')", name="ck_market_import_batch_status"),
        UniqueConstraint("organization_id", "import_key", name="uq_market_import_batch_org_key"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("market_sources.id", ondelete="RESTRICT"), nullable=False, index=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="DRAFT", index=True)
    file_name: Mapped[str | None] = mapped_column(String(512))
    import_key: Mapped[str] = mapped_column(String(128), nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valid_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MarketImportStagedRow(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "market_import_staged_rows"
    __table_args__ = (
        UniqueConstraint("batch_id", "row_number", name="uq_market_import_row"),
        CheckConstraint("status IN ('DRAFT','VALID','INVALID','DUPLICATE','COMMITTED')", name="ck_market_import_row_status"),
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("market_import_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    original_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    normalized_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    validation_errors: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="DRAFT", index=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(128), index=True)


class PriceObservation(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "price_observations"
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("price_sources.id", ondelete="SET NULL"), nullable=True)
    material_form: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    grade: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    region: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    dimension_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    price_basis: Mapped[str] = mapped_column(String(32), default="EX_WORKS", index=True)  # EX_WORKS/DELIVERED/FORWAREIGHT
    price_per_unit: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), default="MT")
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    observed_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    external_observation_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class MarketIngestionRun(Base, UUIDPKMixin, TimestampMixin):
    """Operational record for one provider attempt; credentials/payloads stay out of it."""
    __tablename__ = "market_ingestion_runs"
    __table_args__ = (
        UniqueConstraint("organization_id", "provider_key", "idempotency_key", name="uq_market_ingestion_run_key"),
        CheckConstraint("status IN ('RUNNING','SUCCEEDED','FAILED','PARTIAL','SKIPPED')", name="ck_market_ingestion_run_status"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("price_sources.id", ondelete="RESTRICT"), nullable=False, index=True)
    provider_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="RUNNING", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    inserted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_summary: Mapped[str | None] = mapped_column(String(2000))


class MarketPriceAlertRule(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "market_price_alert_rules"
    __table_args__ = (
        CheckConstraint("price_condition IN ('ABOVE','BELOW')", name="ck_market_alert_condition"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    material_form: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    grade: Mapped[str] = mapped_column(String(64), nullable=False)
    region: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    price_basis: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("price_sources.id", ondelete="RESTRICT"), nullable=True, index=True)
    price_condition: Mapped[str] = mapped_column(String(8), nullable=False)
    price_threshold: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    movement_threshold_pct: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class MarketPriceAlertEvent(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "market_price_alert_events"
    __table_args__ = (UniqueConstraint("alert_rule_id", "observation_id", name="uq_market_alert_event_observation"),)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    alert_rule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("market_price_alert_rules.id", ondelete="CASCADE"), nullable=False, index=True)
    observation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("price_observations.id", ondelete="CASCADE"), nullable=False, index=True)
    notification_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False, index=True)
    trigger_type: Mapped[str] = mapped_column(String(16), nullable=False)


class PriceScenario(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "price_scenarios"
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict)
    results: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
