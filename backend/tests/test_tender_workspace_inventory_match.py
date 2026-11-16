from decimal import Decimal

from sqlalchemy import select

from app.models.fabrication import BOMItem
from app.models.inventory import Reservation, StockLot
from app.models.materials import OrganizationMaterial
from app.models.projects import Tender, TenderInventoryAllocation, TenderWorkflow
from tests.conftest import unique


def _workspace_tender(apex_client, db):
    material = apex_client.get("/api/v1/materials?search=ISMB 200").json()["items"][0]
    tender = apex_client.post("/api/v1/tenders", json={"number": unique("WS-MATCH"), "title": "Workspace inventory match", "project_type": "FABRICATION"}).json()
    tender_id = tender["id"]
    boq = apex_client.post(f"/api/v1/tenders/{tender_id}/boq", json={"line_no": "1", "raw_description": "ISMB 200 E250", "form": "BEAM", "grade": "E250", "quantity": "190", "unit": "MT", "material_id": material["id"]}).json()
    assert apex_client.patch(f"/api/v1/tenders/{tender_id}/boq/{boq['id']}/review", json={"review_status": "CONFIRMED", "material_id": material["id"]}).status_code == 200
    assert apex_client.post(f"/api/v1/tenders/{tender_id}/requirement-snapshots").status_code == 201
    assert apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/bom").status_code == 201
    tender_row = db.get(Tender, tender_id)
    workflow = db.scalar(select(TenderWorkflow).where(TenderWorkflow.tender_id == tender_row.id))
    assert workflow is not None and workflow.bom_version_id is not None
    bom = db.scalar(select(BOMItem).where(BOMItem.bom_version_id == workflow.bom_version_id))
    assert bom is not None
    return tender, tender_row, bom


def test_inventory_match_distinguishes_available_reserved_held_and_allocated(apex_client, metro_client, db):
    tender, tender_row, bom = _workspace_tender(apex_client, db)
    warehouse_id = db.scalar(select(StockLot.warehouse_id).where(StockLot.organization_id == tender_row.organization_id))
    material = db.get(OrganizationMaterial, bom.material_id)
    available = StockLot(organization_id=tender_row.organization_id, material_id=material.id, warehouse_id=warehouse_id, lot_number=unique("AVAILABLE"), quality_status="OK", on_hand_qty=Decimal("100"), reserved_qty=Decimal("30"), unit="MT", unit_cost=Decimal("50000"))
    held = StockLot(organization_id=tender_row.organization_id, material_id=material.id, warehouse_id=warehouse_id, lot_number=unique("HELD"), quality_status="QUARANTINED", on_hand_qty=Decimal("20"), reserved_qty=Decimal("0"), unit="MT", unit_cost=Decimal("50000"))
    db.add_all([available, held]); db.flush()
    reservation = Reservation(organization_id=tender_row.organization_id, stock_lot_id=available.id, material_id=material.id, warehouse_id=warehouse_id, quantity=Decimal("10"), status="ACTIVE", context={})
    db.add(reservation); db.flush()
    db.add(TenderInventoryAllocation(organization_id=tender_row.organization_id, tender_id=tender_row.id, bom_version_id=bom.bom_version_id, bom_item_id=bom.id, stock_lot_id=available.id, reservation_id=reservation.id, quantity=Decimal("10"), unit="MT", valuation_rate=Decimal("50000"), currency="INR", valuation_source={"kind": "test"}, status="ACTIVE")); db.commit()

    response = apex_client.get(f"/api/v1/tenders/{tender['id']}/workspace/inventory-match")
    assert response.status_code == 200, response.text
    row = next(item for item in response.json()["items"] if item["bom_item_id"] == str(bom.id))
    assert row["unit"] == "MT"
    assert Decimal(row["eligible_stock_quantity"]) >= Decimal("100")
    assert Decimal(row["reserved_quantity"]) >= Decimal("30")
    assert Decimal(row["quality_held_quantity"]) >= Decimal("20")
    assert Decimal(row["available_quantity"]) >= Decimal("70")
    assert row["tender_allocated_quantity"] == "10.000000"
    assert Decimal(row["shortage_quantity"]) >= Decimal("10")
    assert metro_client.get(f"/api/v1/tenders/{tender['id']}/workspace/inventory-match").status_code == 404


def test_inventory_match_keeps_units_separate_and_blocks_mismatch(apex_client, db):
    tender, tender_row, bom = _workspace_tender(apex_client, db)
    bom.unit = "SQM"  # Deliberate mismatch: the approved material's base unit is MT.
    db.commit()
    response = apex_client.get(f"/api/v1/tenders/{tender['id']}/workspace/inventory-match")
    assert response.status_code == 200
    row = next(item for item in response.json()["items"] if item["bom_item_id"] == str(bom.id))
    assert row["unit"] == "SQM"
    assert row["matching_status"] == "BLOCKED"
    assert row["eligible_stock_quantity"] == "0.000000"
    assert row["shortage_quantity"] == "190.000000"
    assert any("unit mismatch" in reason for reason in row["reasons"])
