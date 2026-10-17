from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import DecimalOrNone, DecimalStr, OrmModel


class BOMItemIn(BaseModel):
    material_id: UUID
    quantity: Decimal = Field(gt=0)
    unit: str = "MT"
    theoretical_waste_pct: Decimal = Decimal("0")
    notes: str | None = None


class RoutingIn(BaseModel):
    sequence: int = Field(ge=1)
    operation_type: str
    work_center: str | None = None
    est_hours: Decimal = Decimal("0")
    rate_per_hour: Decimal = Decimal("0")


class BOMCreateIn(BaseModel):
    bom_code: str = Field(min_length=1, max_length=64)
    product_name: str = Field(min_length=1, max_length=255)
    items: list[BOMItemIn] = Field(min_length=1)
    routings: list[RoutingIn] = []


class BOMItemOut(BOMItemIn, OrmModel):
    id: UUID
    quantity: DecimalStr
    theoretical_waste_pct: DecimalStr
    material_name: str | None = None
    estimated_cost: DecimalStr | None = None


class RoutingOut(RoutingIn, OrmModel):
    id: UUID
    sequence: int
    est_hours: DecimalStr
    rate_per_hour: DecimalStr


class BOMOut(OrmModel):
    id: UUID
    bom_code: str
    product_name: str
    version_no: int
    status: str
    estimated_material_cost: DecimalStr
    estimated_total_cost: DecimalStr
    created_at: datetime
    items: list[BOMItemOut] = []
    routings: list[RoutingOut] = []


class WorkOrderIn(BaseModel):
    bom_version_id: UUID | None = None
    sales_order_id: UUID | None = None
    planned_qty: Decimal = Field(gt=0)
    due_date: date | None = None


class OperationOut(OrmModel):
    id: UUID
    sequence: int
    operation_type: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    actual_hours: DecimalOrNone
    operator: str | None


class WorkOrderOut(OrmModel):
    id: UUID
    bom_version_id: UUID | None
    sales_order_id: UUID | None
    number: str
    status: str
    planned_qty: DecimalStr
    produced_qty: DecimalStr
    start_date: date | None
    due_date: date | None
    actual_material_cost: DecimalStr
    actual_labour_cost: DecimalStr
    created_at: datetime
    operations: list[OperationOut] = []


class OperationUpdateIn(BaseModel):
    status: str = Field(pattern="^(PENDING|IN_PROGRESS|COMPLETED|SKIPPED)$")
    actual_hours: Decimal | None = None
    operator: str | None = None


class AllocateIn(BaseModel):
    lot_id: UUID
    material_id: UUID
    quantity: Decimal = Field(gt=0)


class AllocateOut(OrmModel):
    id: UUID
    work_order_id: UUID
    stock_lot_id: UUID
    material_id: UUID
    allocated_qty: DecimalStr
    consumed_qty: DecimalStr
    status: str


class InspectionIn(BaseModel):
    inspection_type: str = Field(min_length=1)
    result: str = Field(pattern="^(PASS|FAIL|CONDITIONAL)$")
    inspector: str | None = None
    notes: str | None = None
    is_final: bool = False


class InspectionOut(InspectionIn, OrmModel):
    id: UUID
    work_order_id: UUID
    inspected_at: datetime


class ScrapIn(BaseModel):
    material_id: UUID | None = None
    quantity: Decimal = Field(gt=0)
    unit: str = "KG"
    reason: str | None = None
