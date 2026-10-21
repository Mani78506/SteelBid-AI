import uuid
from datetime import date
from decimal import Decimal
from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String
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
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class PriceScenario(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "price_scenarios"
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict)
    results: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
