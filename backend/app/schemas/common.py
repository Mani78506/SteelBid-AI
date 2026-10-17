"""Shared schema types. Decimals serialize as strings to preserve precision."""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, PlainSerializer

DecimalStr = Annotated[Decimal, PlainSerializer(lambda v: str(v), return_type=str)]
DecimalOrNone = Annotated[Decimal | None, PlainSerializer(lambda v: None if v is None else str(v), return_type=str | None)]


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class OrganizationOut(OrmModel):
    id: UUID
    name: str
    business_profiles: list[str]
    currency_code: str
    timezone: str
    is_demo: bool


class MembershipOut(OrmModel):
    role: str
    organization: OrganizationOut


class UserOut(OrmModel):
    id: UUID
    email: str
    full_name: str
    is_demo: bool


class AuditEventOut(OrmModel):
    id: UUID
    created_at: datetime
    user_id: UUID | None
    action: str
    entity_type: str
    entity_id: UUID | None
    diff: dict
    request_id: str | None


class DateRangeParams(BaseModel):
    from_date: date | None = None
    to_date: date | None = None
