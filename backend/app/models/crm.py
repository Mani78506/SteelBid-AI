import uuid
from decimal import Decimal
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPKMixin


class Customer(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_customer_code"),)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    gstin: Mapped[str | None] = mapped_column(String(32), nullable=True)
    credit_terms_days: Mapped[int] = mapped_column(default=30)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class CustomerContact(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "customer_contacts"
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    designation: Mapped[str | None] = mapped_column(String(64), nullable=True)


class CustomerInquiry(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "customer_inquiries"
    __table_args__ = (UniqueConstraint("organization_id", "reference", name="uq_inquiry_ref"),)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    reference: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="MANUAL")
    status: Mapped[str] = mapped_column(String(16), default="NEW", index=True)  # NEW/QUOTED/WON/LOST/CANCELLED
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    required_by: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class InquiryItem(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "inquiry_items"
    inquiry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_inquiries.id", ondelete="CASCADE"), nullable=False, index=True)
    material_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization_materials.id", ondelete="SET NULL"), nullable=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    form: Mapped[str | None] = mapped_column(String(32), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(64), nullable=True)
    specification: Mapped[dict] = mapped_column(JSONB, default=dict)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), default="MT")
    target_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
