from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import DecimalOrNone, DecimalStr, OrmModel


class QuotationItemIn(BaseModel):
    material_id: UUID | None = None
    description: str = Field(min_length=1, max_length=500)
    form: str | None = None
    grade: str | None = None
    quantity: Decimal = Field(gt=0)
    unit: str = "MT"
    unit_cost: Decimal = Field(ge=0)


class QuotationItemOut(OrmModel):
    id: UUID
    material_id: UUID | None
    description: str
    form: str | None
    grade: str | None
    quantity: DecimalStr
    unit: str
    unit_cost: DecimalStr
    unit_price: DecimalStr
    line_estimated_cost: DecimalStr
    line_selling_price: DecimalStr
    available_qty: DecimalStr
    shortage_qty: DecimalStr


class QuotationCreateIn(BaseModel):
    inquiry_id: UUID | None = None
    customer_id: UUID
    target_margin: Decimal = Field(default=Decimal("0.12"), ge=0, lt=1)
    valid_until: datetime | None = None
    items: list[QuotationItemIn] = Field(min_length=1)


class QuotationVersionOut(OrmModel):
    id: UUID
    quotation_id: UUID
    version_no: int
    status: str
    subtotal: DecimalStr
    total_estimated_cost: DecimalStr
    total_selling_price: DecimalStr
    gross_margin_pct: DecimalStr
    cost_estimate_id: UUID | None
    approved_by: UUID | None
    approved_at: datetime | None
    is_immutable: bool


class QuotationOut(OrmModel):
    id: UUID
    inquiry_id: UUID | None
    customer_id: UUID
    customer_name: str | None = None
    number: str
    status: str
    currency: str
    target_margin: DecimalStr
    valid_until: datetime | None
    created_at: datetime
    items: list[QuotationItemOut] = []
    versions: list[QuotationVersionOut] = []


class QuotationUpdateIn(BaseModel):
    target_margin: Decimal = Field(ge=0, lt=1)
    valid_until: datetime | None = None
    items: list[QuotationItemIn] = Field(min_length=1)


class ApproveIn(BaseModel):
    comment: str | None = None


class SalesOrderItemOut(OrmModel):
    id: UUID
    material_id: UUID | None
    description: str
    quantity: DecimalStr
    unit: str
    unit_price: DecimalStr
    reserved_qty: DecimalStr
    delivered_qty: DecimalStr


class SalesOrderOut(OrmModel):
    id: UUID
    quotation_id: UUID | None
    customer_id: UUID
    customer_name: str | None = None
    number: str
    status: str
    total_value: DecimalStr
    order_date: datetime
    delivery_date: datetime | None
    created_at: datetime
    items: list[SalesOrderItemOut] = []


class SalesOrderStatusIn(BaseModel):
    status: str = Field(pattern="^(CONFIRMED|IN_PRODUCTION|READY|DISPATCHED|CLOSED|CANCELLED)$")


class ReserveRequestIn(BaseModel):
    sales_order_item_id: UUID
    lot_id: UUID
    quantity: Decimal = Field(gt=0)
