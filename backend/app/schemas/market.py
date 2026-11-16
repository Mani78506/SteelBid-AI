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
    price_basis: str = Field(min_length=1, max_length=32)  # explicitly supplied; never inferred
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


class PriceAlertIn(BaseModel):
    material_form: str
    grade: str
    region: str
    currency: str = "INR"
    unit: str = "MT"
    price_basis: str
    source_id: UUID | None = None
    price_condition: str = Field(pattern="^(ABOVE|BELOW)$")
    price_threshold: Decimal | None = Field(default=None, gt=0)
    movement_threshold_pct: Decimal | None = Field(default=None, gt=0)
    is_active: bool = True


class PriceAlertUpdate(BaseModel):
    price_threshold: Decimal | None = Field(default=None, gt=0)
    movement_threshold_pct: Decimal | None = Field(default=None, gt=0)
    is_active: bool | None = None


class TenderSourceRegistryOut(BaseModel):
    """Read-only, safe-to-display registry projection; never includes secrets."""
    id: UUID
    name: str
    source_category: str
    permitted_ingestion_method: str
    data_classification: str
    enabled_for_tender_ingestion: bool
    supports_discovery: bool
    supports_document_retrieval: bool
    supports_revision_tracking: bool
    reference_url: str | None
    attribution_text: str
    license_status: str
    usage_restrictions: str | None
    publication_frequency: str | None
    visibility: str
    redistribution_permitted: bool
    last_success_at: datetime | None = None
    last_checked_at: datetime | None = None
    health_status: str
