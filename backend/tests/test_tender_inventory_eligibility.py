from decimal import Decimal

from sqlalchemy import func, select

from app.models.fabrication import BOMItem, BOMVersion
from app.models.projects import BOQItem, Tender, TenderRequirementSnapshot
from app.services.tender_inventory import analyze_bom_item_inventory
from tests.conftest import unique


def _training_requirement(db):
    tender = db.scalar(select(Tender).where(Tender.number == "DEMO-JRS-WH-001"))
    assert tender is not None
    boq = db.scalar(select(BOQItem).where(BOQItem.tender_id == tender.id, BOQItem.unit == "MT"))
    assert boq is not None and boq.material_id is not None
    version = (db.scalar(select(func.max(TenderRequirementSnapshot.version)).where(
        TenderRequirementSnapshot.tender_id == tender.id)) or 0) + 1
    snapshot = TenderRequirementSnapshot(organization_id=tender.organization_id, tender_id=tender.id,
        source_boq_item_id=boq.id, version=version, material_id=boq.material_id, form=boq.form,
        grade=boq.grade, specification=boq.specification, quantity=boq.quantity, unit=boq.unit,
        approved_at=boq.created_at)
    db.add(snapshot); db.flush()
    return tender, snapshot


def test_operational_tender_excludes_training_stock_but_training_tender_can_use_it(db):
    training_tender, snapshot = _training_requirement(db)
    bom = BOMVersion(organization_id=training_tender.organization_id, bom_code=unique("INV-BOM"),
                     product_name="Eligibility test", version_no=1, tender_id=training_tender.id)
    db.add(bom); db.flush()
    item = BOMItem(organization_id=training_tender.organization_id, bom_version_id=bom.id,
                   tender_requirement_snapshot_id=snapshot.id, material_id=snapshot.material_id,
                   quantity=Decimal("24"), unit="MT")
    db.add(item); db.flush()

    training = analyze_bom_item_inventory(db, training_tender.organization_id, training_tender, item)
    assert training["eligible_quantity"] > 0

    operational = Tender(organization_id=training_tender.organization_id, number=unique("OP-INV"),
                         title="Operational eligibility test", project_type="INDUSTRIAL",
                         data_classification="OPERATIONAL")
    db.add(operational); db.flush()
    operational_result = analyze_bom_item_inventory(db, operational.organization_id, operational, item)
    assert operational_result["eligible_quantity"] == Decimal("0")
    assert operational_result["shortage_quantity"] == Decimal("24")
    assert "training-only stock excluded" in operational_result["reasons"]


def test_incompatible_unit_is_blocked_without_implicit_conversion(db):
    tender, snapshot = _training_requirement(db)
    bom = BOMVersion(organization_id=tender.organization_id, bom_code=unique("UNIT-BOM"),
                     product_name="Unit test", version_no=1, tender_id=tender.id)
    db.add(bom); db.flush()
    item = BOMItem(organization_id=tender.organization_id, bom_version_id=bom.id,
                   tender_requirement_snapshot_id=snapshot.id, material_id=snapshot.material_id,
                   quantity=Decimal("24"), unit="SQM")
    db.add(item); db.flush()

    result = analyze_bom_item_inventory(db, tender.organization_id, tender, item)
    assert result["status"] == "BLOCKED"
    assert result["eligible_quantity"] == Decimal("0")
    assert any("unit mismatch" in reason for reason in result["reasons"])
