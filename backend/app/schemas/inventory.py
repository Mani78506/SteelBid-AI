from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import DecimalOrNone, DecimalStr, OrmModel


class WarehouseIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=255)
    location: str | None = None


class WarehouseOut(WarehouseIn, OrmModel):
    id: UUID
    is_active: bool


class LocationIn(BaseModel):
    warehouse_id: UUID
    code: str = Field(min_length=1, max_length=32)
    name: str | None = None


class LocationOut(LocationIn, OrmModel):
    id: UUID


class StockLotOut(OrmModel):
    id: UUID
    material_id: UUID
    material_sku: str | None = None
    material_name: str | None = None
    warehouse_id: UUID
    warehouse_name: str | None = None
    storage_location_id: UUID | None
    lot_number: str
    heat_number: str | None
    quality_status: str
    on_hand_qty: DecimalStr
    reserved_qty: DecimalStr
    available_qty: DecimalStr | None = None
    unit: str
    unit_cost: DecimalOrNone
    created_at: datetime


class ReceiptIn(BaseModel):
    material_id: UUID
    warehouse_id: UUID
    lot_number: str = Field(min_length=1, max_length=64)
    quantity: Decimal = Field(gt=0)
    unit: str = "MT"
    heat_number: str | None = None
    unit_cost: Decimal | None = None
    quality_status: str = Field(default="OK", pattern="^(OK|QUARANTINED|REJECTED)$")
    received_on: date | None = None


class IssueIn(BaseModel):
    lot_id: UUID
    quantity: Decimal = Field(gt=0)
    movement_type: str = Field(default="ISSUE", pattern="^(ISSUE|CONSUME|SCRAP)$")
    reason: str | None = None


class AdjustmentIn(BaseModel):
    lot_id: UUID
    new_on_hand: Decimal = Field(ge=0)
    reason: str = Field(min_length=3, max_length=500)


class ReserveIn(BaseModel):
    lot_id: UUID
    quantity: Decimal = Field(gt=0)
    context: dict = {}


class ReservationOut(OrmModel):
    id: UUID
    stock_lot_id: UUID
    material_id: UUID
    warehouse_id: UUID
    quantity: DecimalStr
    status: str
    context: dict
    created_at: datetime


class TransferIn(BaseModel):
    lot_id: UUID
    to_warehouse_id: UUID
    quantity: Decimal = Field(gt=0)


class MovementOut(OrmModel):
    id: UUID
    movement_type: str
    material_id: UUID
    warehouse_id: UUID
    stock_lot_id: UUID
    quantity: DecimalStr
    balance_after_on_hand: DecimalStr
    unit: str
    reference: dict
    created_by: UUID | None
    created_at: datetime
