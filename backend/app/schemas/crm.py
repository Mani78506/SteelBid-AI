from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import DecimalOrNone, OrmModel


class CustomerIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=255)
    category: str | None = None
    gstin: str | None = None
    credit_terms_days: int = 30
    currency: str = "INR"


class CustomerUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    gstin: str | None = None
    credit_terms_days: int | None = None
    is_active: bool | None = None


class CustomerOut(OrmModel):
    id: UUID
    code: str
    name: str
    category: str | None
    gstin: str | None
    credit_terms_days: int
    currency: str
    is_active: bool
    is_demo: bool


class ContactIn(BaseModel):
    name: str = Field(min_length=1)
    email: str | None = None
    phone: str | None = None
    designation: str | None = None


class ContactOut(ContactIn, OrmModel):
    id: UUID
    customer_id: UUID


class InquiryItemIn(BaseModel):
    material_id: UUID | None = None
    description: str = Field(min_length=1, max_length=500)
    form: str | None = None
    grade: str | None = None
    specification: dict = {}
    quantity: Decimal = Field(gt=0)
    unit: str = "MT"
    target_price: Decimal | None = None


class InquiryItemOut(InquiryItemIn, OrmModel):
    id: UUID
    inquiry_id: UUID
    quantity: DecimalOrNone
    target_price: DecimalOrNone
    material_name: str | None = None


class InquiryIn(BaseModel):
    customer_id: UUID
    reference: str = Field(min_length=1, max_length=64)
    source: str = "MANUAL"
    required_by: datetime | None = None
    notes: str | None = None
    items: list[InquiryItemIn] = []


class InquiryOut(OrmModel):
    id: UUID
    customer_id: UUID
    customer_name: str | None = None
    reference: str
    source: str
    status: str
    received_at: datetime
    required_by: datetime | None
    notes: str | None
    items: list[InquiryItemOut] = []


class InquiryStatusIn(BaseModel):
    status: str = Field(pattern="^(NEW|QUOTED|WON|LOST|CANCELLED)$")
