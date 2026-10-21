from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import DecimalOrNone, DecimalStr, OrmModel


class ProjectIn(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    customer_id: UUID | None = None
    project_type: str
    location: str | None = None
    estimated_value: Decimal | None = None
    start_date: date | None = None
    end_date: date | None = None


class ProjectOut(ProjectIn, OrmModel):
    id: UUID
    status: str
    currency: str
    estimated_value: DecimalOrNone
    created_at: datetime


class TenderIn(BaseModel):
    project_id: UUID | None = None
    number: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=500)
    customer: str | None = None
    project_type: str
    location: str | None = None
    submission_deadline: datetime | None = None
    estimated_value: Decimal | None = None
    currency: str = "INR"
    description: str | None = None


class TenderUpdate(BaseModel):
    title: str | None = None
    customer: str | None = None
    location: str | None = None
    submission_deadline: datetime | None = None
    estimated_value: Decimal | None = None
    description: str | None = None


class TenderStatusIn(BaseModel):
    status: str = Field(pattern="^(DRAFT|IN_REVIEW|ESTIMATING|BID_SUBMITTED|WON|LOST|CANCELLED)$")


class TenderOut(TenderIn, OrmModel):
    id: UUID
    status: str
    estimated_value: DecimalOrNone
    created_at: datetime
    documents_count: int = 0
    boq_items_count: int = 0


class TenderDocumentOut(OrmModel):
    id: UUID
    tender_id: UUID
    file_name: str
    mime_type: str | None
    size_bytes: int | None
    status: str
    created_at: datetime


class BOQItemIn(BaseModel):
    line_no: str | None = None
    raw_description: str = Field(min_length=1)
    form: str | None = None
    grade: str | None = None
    specification: dict = {}
    quantity: Decimal | None = None
    unit: str | None = None
    material_id: UUID | None = None


class BOQItemOut(BOQItemIn, OrmModel):
    id: UUID
    tender_id: UUID
    quantity: DecimalOrNone
    review_status: str
    source: str
    page_ref: str | None
    material_name: str | None = None


class BOQReviewIn(BaseModel):
    review_status: str = Field(pattern="^(CONFIRMED|REJECTED)$")
    material_id: UUID | None = None
    quantity: Decimal | None = None


class EvidenceOut(OrmModel):
    id: UUID
    document_id: UUID
    page: int | None
    cell_ref: str | None
    field: str
    raw_value: str
    normalized_value: dict
    confidence: DecimalOrNone
    review_status: str
    warnings: dict
    created_at: datetime


class RequirementIn(BaseModel):
    material_id: UUID
    quantity: Decimal = Field(gt=0)
    unit: str = "MT"
    required_by: date | None = None
    source: str = "MANUAL"


class RequirementOut(RequirementIn, OrmModel):
    id: UUID
    project_id: UUID
    quantity: DecimalStr
    material_name: str | None = None


class TenderSupplierSelectionIn(BaseModel):
    supplier_quote_id: UUID
    selected_qty: Decimal = Field(gt=0)
    delivery_terms: str | None = Field(default=None, max_length=128)


class TenderSupplierSelectionCancelIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
