from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import DecimalStr, OrmModel


class PriceObservationIn(BaseModel):
    material_form: str
    grade: str
    region: str = "West India"
    dimension_note: str | None = None
    price_basis: str = "EX_WORKS"  # EX_WORKS/DELIVERED/FORWARD
    price_per_unit: Decimal = Field(gt=0)
    unit: str = "MT"
    currency: str = "INR"
    observed_on: date


class PriceObservationOut(PriceObservationIn, OrmModel):
    id: UUID
    price_per_unit: DecimalStr
    is_synthetic: bool
    source_name: str | None = None
    created_at: datetime


class TrendPoint(BaseModel):
    observed_on: date
    price_per_unit: DecimalStr
    is_synthetic: bool


class TrendOut(BaseModel):
    material_form: str
    grade: str
    region: str
    points: list[TrendPoint]
    latest: DecimalStr | None
    change_pct_30d: DecimalStr | None
    change_pct_90d: DecimalStr | None
    data_is_synthetic: bool
    freshness_days: int | None


class ScenarioIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    material_form: str
    grade: str
    region: str = "West India"
    planned_qty: Decimal = Field(gt=0)
    unit: str = "MT"
    price_delta_pct: Decimal = Decimal("0")  # e.g. 0.05 for +5%
    horizon_days: int = 30


class ScenarioOut(OrmModel):
    id: UUID
    name: str
    parameters: dict
    results: dict
    created_at: datetime
