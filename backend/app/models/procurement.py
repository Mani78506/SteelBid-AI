import uuid
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPKMixin


class Supplier(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "suppliers"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_supplier_code"),)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payment_terms_days: Mapped[int] = mapped_column(default=30)
    lead_time_days: Mapped[int] = mapped_column(default=14)
    rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    material_capabilities: Mapped[list[str]] = mapped_column(ARRAY(String(64)), default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class PurchaseRequest(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "purchase_requests"
    __table_args__ = (
        UniqueConstraint("organization_id", "number", name="uq_pr_number"),
        UniqueConstraint("organization_id", "idempotency_key", name="uq_pr_idem"),
    )
    number: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT", index=True)
    source_type: Mapped[str] = mapped_column(String(24), default="MANUAL")  # SHORTAGE/MANUAL
    context: Mapped[dict] = mapped_column(JSONB, default=dict)  # e.g. {"sales_order_id": ...}
    needed_by: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)


class PurchaseRequestItem(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "purchase_request_items"
    purchase_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization_materials.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), default="MT")
    required_by: Mapped[date | None] = mapped_column(Date, nullable=True)


class RFQ(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "rfqs"
    __table_args__ = (UniqueConstraint("organization_id", "number", name="uq_rfq_number"),)
    purchase_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_requests.id", ondelete="SET NULL"), nullable=True)
    number: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="ISSUED")
    issued_on: Mapped[date] = mapped_column(Date, server_default="now()")
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class SupplierQuote(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "supplier_quotes"
    rfq_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rfqs.id", ondelete="SET NULL"), nullable=True, index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True)
    material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization_materials.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), default="MT")
    unit_price: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    fx_rate_to_org_ccy: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=1)
    freight_per_unit: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    duty_pct: Mapped[Decimal] = mapped_column(Numeric(8, 6), default=0)
    tax_pct: Mapped[Decimal] = mapped_column(Numeric(8, 6), default=0)
    tax_recoverable: Mapped[bool] = mapped_column(Boolean, default=True)
    payment_terms_days: Mapped[int] = mapped_column(default=30)
    lead_time_days: Mapped[int] = mapped_column(default=14)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="OPEN")


class PurchaseOrder(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        UniqueConstraint("organization_id", "number", name="uq_po_number"),
        UniqueConstraint("organization_id", "idempotency_key", name="uq_po_idem"),
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True)
    purchase_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_requests.id", ondelete="SET NULL"), nullable=True)
    number: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT", index=True)
    total_value: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    expected_delivery: Mapped[date | None] = mapped_column(Date, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)


class PurchaseOrderItem(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "purchase_order_items"
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization_materials.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), default="MT")
    unit_price: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    received_qty: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=0)


class GoodsReceipt(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "goods_receipts"
    __table_args__ = (
        UniqueConstraint("organization_id", "number", name="uq_grn_number"),
        UniqueConstraint("organization_id", "idempotency_key", name="uq_grn_idem"),
    )
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="RESTRICT"), nullable=False, index=True)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False)
    number: Mapped[str] = mapped_column(String(64), nullable=False)
    received_on: Mapped[date] = mapped_column(Date, server_default="now()")
    status: Mapped[str] = mapped_column(String(16), default="POSTED")
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
