from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import DecimalOrNone, DecimalStr, OrmModel


class MaterialIn(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    form: str = Field(min_length=1, max_length=32)
    grade: str = Field(min_length=1, max_length=64)
    standard: str | None = None
    base_unit: str = "MT"
    density: Decimal | None = None
    specification: dict = {}
    low_stock_threshold: Decimal | None = None


class MaterialUpdate(BaseModel):
    name: str | None = None
    standard: str | None = None
    specification: dict | None = None
    low_stock_threshold: Decimal | None = None
    density: Decimal | None = None
    is_active: bool | None = None


class MaterialOut(OrmModel):
    id: UUID
    sku: str
    name: str
    form: str
    grade: str
    standard: str | None
    base_unit: str
    density: DecimalOrNone
    specification: dict
    low_stock_threshold: DecimalOrNone
    is_active: bool


class AvailabilityOut(BaseModel):
    material_id: UUID
    sku: str | None = None
    name: str | None = None
    on_hand: DecimalStr
    reserved: DecimalStr
    available: DecimalStr
    quality_held: DecimalStr
    low_stock_threshold: DecimalOrNone = None
    is_low: bool = False
