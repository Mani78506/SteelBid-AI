from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import DecimalOrNone, DecimalStr, OrmModel


class SupplierIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=255)
    category: str | None = None
    contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    city: str | None = None
    payment_terms_days: int = 30
    lead_time_days: int = 14
    rating: Decimal | None = None
    material_capabilities: list[str] = []


class SupplierUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    city: str | None = None
    payment_terms_days: int | None = None
    lead_time_days: int | None = None
    rating: Decimal | None = None
    material_capabilities: list[str] | None = None
    is_active: bool | None = None


class SupplierOut(SupplierIn, OrmModel):
    id: UUID
    rating: DecimalOrNone
    is_active: bool
    is_demo: bool


class PRItemIn(BaseModel):
    material_id: UUID
    quantity: Decimal = Field(gt=0)
    unit: str = "MT"
    required_by: date | None = None


class PurchaseRequestIn(BaseModel):
    source_type: str = "MANUAL"
    context: dict = {}
    needed_by: date | None = None
    notes: str | None = None
    items: list[PRItemIn] = Field(min_length=1)


class PRItemOut(PRItemIn, OrmModel):
    id: UUID
    quantity: DecimalStr
    material_name: str | None = None


class PurchaseRequestOut(OrmModel):
    id: UUID
    number: str
    status: str
    source_type: str
    context: dict
    needed_by: date | None
    notes: str | None
    created_at: datetime
    items: list[PRItemOut] = []


class SupplierQuoteIn(BaseModel):
    rfq_id: UUID | None = None
    supplier_id: UUID
    material_id: UUID
    quantity: Decimal = Field(gt=0)
    unit: str = "MT"
    unit_price: Decimal = Field(ge=0)
    currency: str = "INR"
    fx_rate_to_org_ccy: Decimal = Decimal("1")
    freight_per_unit: Decimal = Decimal("0")
    duty_pct: Decimal = Decimal("0")
    tax_pct: Decimal = Decimal("0")
    tax_recoverable: bool = True
    payment_terms_days: int = 30
    lead_time_days: int = 14
    valid_until: date | None = None


class SupplierQuoteOut(SupplierQuoteIn, OrmModel):
    id: UUID
    quantity: DecimalStr
    unit_price: DecimalStr
    fx_rate_to_org_ccy: DecimalStr
    freight_per_unit: DecimalStr
    duty_pct: DecimalStr
    tax_pct: DecimalStr
    status: str
    supplier_name: str | None = None
    landed_cost: DecimalStr | None = None


class ComparisonOut(BaseModel):
    material_id: UUID | None = None
    items: list[dict]


class POItemIn(BaseModel):
    material_id: UUID
    quantity: Decimal = Field(gt=0)
    unit: str = "MT"
    unit_price: Decimal = Field(ge=0)


class PurchaseOrderIn(BaseModel):
    supplier_id: UUID
    purchase_request_id: UUID | None = None
    expected_delivery: date | None = None
    items: list[POItemIn] = Field(min_length=1)


class POItemOut(POItemIn, OrmModel):
    id: UUID
    quantity: DecimalStr
    unit_price: DecimalStr
    received_qty: DecimalStr
    material_name: str | None = None


class PurchaseOrderOut(OrmModel):
    id: UUID
    supplier_id: UUID
    supplier_name: str | None = None
    purchase_request_id: UUID | None
    number: str
    status: str
    total_value: DecimalStr
    expected_delivery: date | None
    approved_by: UUID | None
    approved_at: datetime | None
    created_at: datetime
    items: list[POItemOut] = []


class GoodsReceiptIn(BaseModel):
    purchase_order_id: UUID
    warehouse_id: UUID
    lot_number_prefix: str | None = None


class GoodsReceiptOut(OrmModel):
    id: UUID
    purchase_order_id: UUID
    warehouse_id: UUID
    number: str
    received_on: date
    status: str


class ShortageRequestIn(BaseModel):
    material_id: UUID
    quantity: Decimal = Field(gt=0)
    needed_by: date | None = None
    context: dict = {}
