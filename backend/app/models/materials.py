import uuid
from decimal import Decimal
from sqlalchemy import Boolean, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPKMixin


class MaterialCatalog(Base, UUIDPKMixin, TimestampMixin):
    """Global steel reference catalog (shared, read-only to tenants)."""
    __tablename__ = "material_catalog"
    __table_args__ = (UniqueConstraint("sku", name="uq_catalog_sku"),)
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    form: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    grade: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    standard: Mapped[str | None] = mapped_column(String(64), nullable=True)
    density: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    base_unit: Mapped[str] = mapped_column(String(16), default="MT")


class OrganizationMaterial(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "organization_materials"
    __table_args__ = (UniqueConstraint("organization_id", "sku", name="uq_org_material_sku"),)
    catalog_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("material_catalog.id", ondelete="SET NULL"), nullable=True)
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    form: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    grade: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    standard: Mapped[str | None] = mapped_column(String(64), nullable=True)
    base_unit: Mapped[str] = mapped_column(String(16), default="MT")
    density: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    specification: Mapped[dict] = mapped_column(JSONB, default=dict)
    low_stock_threshold: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class MaterialSpec(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "material_specs"
    organization_material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization_materials.id", ondelete="CASCADE"), nullable=False, index=True)
    dimension_type: Mapped[str] = mapped_column(String(64), nullable=False)
    dimensions: Mapped[dict] = mapped_column(JSONB, default=dict)
    weight_per_meter: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)


class UnitConversion(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "unit_conversions"
    __table_args__ = (UniqueConstraint("organization_id", "from_unit", "to_unit", name="uq_conversion"),)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    from_unit: Mapped[str] = mapped_column(String(16), nullable=False)
    to_unit: Mapped[str] = mapped_column(String(16), nullable=False)
    factor: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False)
