import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPKMixin


class Quotation(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "quotations"
    __table_args__ = (UniqueConstraint("organization_id", "number", name="uq_quotation_number"),)
    inquiry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_inquiries.id", ondelete="SET NULL"), nullable=True)
    # Deliberately nullable: no legacy record is inferred to belong to a tender.
    tender_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenders.id", ondelete="SET NULL"), nullable=True, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    number: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT", index=True)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    target_margin: Mapped[Decimal] = mapped_column(Numeric(8, 6), default=Decimal("0.12"))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)


class QuotationVersion(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "quotation_versions"
    __table_args__ = (UniqueConstraint("quotation_id", "version_no", name="uq_quotation_version"),)
    quotation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotations.id", ondelete="CASCADE"), nullable=False, index=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    subtotal: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    total_estimated_cost: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    total_selling_price: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    gross_margin_pct: Mapped[Decimal] = mapped_column(Numeric(8, 6), default=0)
    cost_estimate_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_immutable: Mapped[bool] = mapped_column(Boolean, default=False)


class QuotationItem(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "quotation_items"
    quotation_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotation_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    material_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization_materials.id", ondelete="SET NULL"), nullable=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    form: Mapped[str | None] = mapped_column(String(32), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(64), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), default="MT")
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    line_estimated_cost: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    line_selling_price: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    available_qty: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=0)
    shortage_qty: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=0)


class SalesOrder(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "sales_orders"
    __table_args__ = (UniqueConstraint("organization_id", "number", name="uq_sales_order_number"),)
    quotation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotations.id", ondelete="SET NULL"), nullable=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    number: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="CONFIRMED", index=True)
    total_value: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    order_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    delivery_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class SalesOrderItem(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "sales_order_items"
    sales_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sales_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    material_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization_materials.id", ondelete="SET NULL"), nullable=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), default="MT")
    unit_price: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    reserved_qty: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=0)
    delivered_qty: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=0)
