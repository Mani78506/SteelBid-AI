import uuid
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPKMixin


class BOMVersion(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "bom_versions"
    __table_args__ = (UniqueConstraint("organization_id", "bom_code", "version_no", name="uq_bom_version"),)
    bom_code: Mapped[str] = mapped_column(String(64), nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT")  # DRAFT/APPROVED/OBSOLETE
    estimated_material_cost: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    estimated_total_cost: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BOMItem(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "bom_items"
    bom_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bom_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization_materials.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), default="MT")
    theoretical_waste_pct: Mapped[Decimal] = mapped_column(Numeric(8, 6), default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Routing(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "routings"
    bom_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bom_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    operation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    work_center: Mapped[str | None] = mapped_column(String(128), nullable=True)
    est_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    rate_per_hour: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)


class WorkOrder(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "work_orders"
    __table_args__ = (UniqueConstraint("organization_id", "number", name="uq_work_order_number"),)
    bom_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bom_versions.id", ondelete="SET NULL"), nullable=True)
    sales_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sales_orders.id", ondelete="SET NULL"), nullable=True)
    number: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="PLANNED", index=True)
    planned_qty: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=0)
    produced_qty: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=0)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_material_cost: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    actual_labour_cost: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)


class ProductionOperation(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "production_operations"
    work_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    routing_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("routings.id", ondelete="SET NULL"), nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    operation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_hours: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    operator: Mapped[str | None] = mapped_column(String(255), nullable=True)


class MaterialAllocation(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "material_allocations"
    work_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    stock_lot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_lots.id", ondelete="RESTRICT"), nullable=False)
    material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization_materials.id", ondelete="RESTRICT"), nullable=False)
    allocated_qty: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    consumed_qty: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=0)
    status: Mapped[str] = mapped_column(String(16), default="ALLOCATED")  # ALLOCATED/CONSUMED/RELEASED


class ScrapRecord(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "scrap_records"
    work_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    material_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization_materials.id", ondelete="SET NULL"), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), default="KG")
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)


class QualityInspection(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "quality_inspections"
    work_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    inspection_type: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[str] = mapped_column(String(16), nullable=False)  # PASS/FAIL/CONDITIONAL
    inspector: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    inspected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)
