from sqlalchemy import select

from app.models.identity import Membership, Organization, User
from app.models.inventory import StockLot
from app.models.materials import OrganizationMaterial
from app.models.projects import Tender
from app.models.procurement import Supplier
from app.models.sales import Quotation
from tests.conftest import login


def test_jayraj_is_a_separate_persisted_workspace_without_invented_operational_data(client, db):
    login(client, "admin@jayraj.demo")
    orgs = client.get("/api/v1/auth/organizations").json()
    assert len(orgs) == 1
    assert orgs[0]["name"] == "JAYRAJ STEEL PRIVATE LIMITED"
    jayraj_id = orgs[0]["id"]

    org = db.scalar(select(Organization).where(Organization.id == jayraj_id))
    admin = db.scalar(select(User).where(User.email == "admin@jayraj.demo"))
    assert org is not None and org.is_demo is False
    assert admin is not None
    assert db.scalar(select(Membership).where(Membership.organization_id == org.id, Membership.user_id == admin.id))

    # The scoped material master is real reference catalog data. Operational
    # records remain empty until authorised Jayraj users add verified inputs.
    assert db.scalar(select(OrganizationMaterial).where(OrganizationMaterial.organization_id == org.id))
    assert db.scalar(select(StockLot).where(StockLot.organization_id == org.id)) is None
    assert db.scalar(select(Tender).where(Tender.organization_id == org.id)) is None
    assert db.scalar(select(Supplier).where(Supplier.organization_id == org.id)) is None
    assert db.scalar(select(Quotation).where(Quotation.organization_id == org.id)) is None
