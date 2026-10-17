from uuid import UUID
from pydantic import BaseModel, EmailStr, Field


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class SwitchOrgIn(BaseModel):
    organization_id: UUID


class MeOut(BaseModel):
    user: "common.UserOut"
    active_organization: "common.OrganizationOut | None"
    role: str | None
    memberships: list["common.MembershipOut"]


from app.schemas import common  # noqa: E402

MeOut.model_rebuild()
