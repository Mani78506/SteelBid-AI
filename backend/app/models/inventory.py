import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import OrgScopedMixin, TimestampMixin, UUIDPKMixin


class Warehouse(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "warehouses"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_warehouse_code"),)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class StorageLocation(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "storage_locations"
    __table_args__ = (UniqueConstraint("warehouse_id", "code", name="uq_location_code"),)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)


class StockLot(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "stock_lots"
    __table_args__ = (
        UniqueConstraint("organization_id", "material_id", "warehouse_id", "lot_number", name="uq_stock_lot"),
        CheckConstraint("on_hand_qty >= 0", name="ck_lot_on_hand_nonneg"),
        CheckConstraint("reserved_qty >= 0", name="ck_lot_reserved_nonneg"),
        CheckConstraint("reserved_qty <= on_hand_qty", name="ck_lot_reserved_le_onhand"),
    )
    material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization_materials.id", ondelete="RESTRICT"), nullable=False, index=True)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False, index=True)
    storage_location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("storage_locations.id", ondelete="SET NULL"), nullable=True)
    lot_number: Mapped[str] = mapped_column(String(64), nullable=False)
    heat_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    quality_status: Mapped[str] = mapped_column(String(16), default="OK", index=True)  # OK/QUARANTINED/REJECTED
    on_hand_qty: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    reserved_qty: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    unit: Mapped[str] = mapped_column(String(16), default="MT")
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    source: Mapped[dict] = mapped_column(JSONB, default=dict)


class InventoryMovement(Base, UUIDPKMixin, OrgScopedMixin):
    __tablename__ = "inventory_movements"
    __table_args__ = (UniqueConstraint("organization_id", "idempotency_key", name="uq_movement_idem"),)
    material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization_materials.id", ondelete="RESTRICT"), nullable=False, index=True)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False, index=True)
    stock_lot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_lots.id", ondelete="RESTRICT"), nullable=False, index=True)
    movement_type: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)  # signed
    unit: Mapped[str] = mapped_column(String(16), default="MT")
    balance_after_on_hand: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    reference: Mapped[dict] = mapped_column(JSONB, default=dict)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class Reservation(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "reservations"
    __table_args__ = (UniqueConstraint("organization_id", "idempotency_key", name="uq_reservation_idem"),)
    stock_lot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_lots.id", ondelete="RESTRICT"), nullable=False, index=True)
    material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization_materials.id", ondelete="RESTRICT"), nullable=False)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)  # ACTIVE/CONSUMED/CANCELLED
    context: Mapped[dict] = mapped_column(JSONB, default=dict)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)


class StockTransfer(Base, UUIDPKMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "stock_transfers"
    stock_lot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stock_lots.id", ondelete="RESTRICT"), nullable=False)
    from_warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False)
    to_warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="COMPLETED")
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
