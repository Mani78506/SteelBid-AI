"""Logistics, Finance, Governance models."""
import uuid
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPKMixin


# ---------- Logistics ----------
class Dispatch(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "dispatches"
    __table_args__ = (UniqueConstraint("organization_id", "number", name="uq_dispatch_number"),)
    sales_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sales_orders.id", ondelete="SET NULL"), nullable=True)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False)
    number: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="PLANNED", index=True)
    vehicle: Mapped[str | None] = mapped_column(String(64), nullable=True)
    transporter: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dispatch_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class DispatchItem(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "dispatch_items"
    dispatch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dispatches.id", ondelete="CASCADE"), nullable=False, index=True)
    sales_order_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sales_order_items.id", ondelete="SET NULL"), nullable=True)
    stock_lot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_lots.id", ondelete="SET NULL"), nullable=True)
    material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization_materials.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), default="MT")


class Shipment(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "shipments"
    dispatch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dispatches.id", ondelete="CASCADE"), nullable=False, index=True)
    tracking_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="IN_TRANSIT")
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


# ---------- Finance ----------
class CostEstimate(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "cost_estimates"
    context: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT")  # DRAFT/APPROVED
    version: Mapped[int] = mapped_column(Integer, default=1)
    parent_estimate_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    material_cost: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    fabrication_cost: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    labour_cost: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    freight_cost: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    installation_cost: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    subcontracting_cost: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    overhead_cost: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    contingency_pct: Mapped[Decimal] = mapped_column(Numeric(8, 6), default=0)
    contingency_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)


class CostLine(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "cost_lines"
    cost_estimate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cost_estimates.id", ondelete="CASCADE"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False)  # MATERIAL/FABRICATION/LABOUR/FREIGHT/INSTALLATION/SUBCONTRACTING/OVERHEAD/CONTINGENCY
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    material_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization_materials.id", ondelete="SET NULL"), nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    source: Mapped[dict] = mapped_column(JSONB, default=dict)


class Invoice(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "invoices"
    __table_args__ = (UniqueConstraint("organization_id", "invoice_type", "number", name="uq_invoice_number"),)
    invoice_type: Mapped[str] = mapped_column(String(8), nullable=False)  # SALES/PURCHASE
    number: Mapped[str] = mapped_column(String(64), nullable=False)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True)
    sales_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sales_orders.id", ondelete="SET NULL"), nullable=True)
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="SET NULL"), nullable=True)
    issue_date: Mapped[date] = mapped_column(Date, server_default="now()")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[str] = mapped_column(String(24), default="DRAFT", index=True)


class Payment(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "payments"
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    paid_on: Mapped[date] = mapped_column(Date, server_default="now()")
    method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(128), nullable=True)


# ---------- Governance ----------
class Approval(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "approvals"
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    approval_type: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)


class AuditEvent(Base, UUIDPKMixin, OrgScopedMixin):
    __tablename__ = "audit_events"
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    diff: Mapped[dict] = mapped_column(JSONB, default=dict)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", index=True)


class Notification(Base, UUIDPKMixin, OrgScopedMixin):
    __tablename__ = "notifications"
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class AIJob(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "ai_jobs"
    job_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default="QUEUED", index=True)
    input: Mapped[dict] = mapped_column(JSONB, default=dict)
    output: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
