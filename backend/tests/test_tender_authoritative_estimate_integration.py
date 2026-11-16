"""Endpoint integration coverage for allocation-backed authoritative tender costing.

The shared fixture asserts/reset only the disposable steelbid_test database.
"""
from decimal import Decimal as D

from sqlalchemy import select

from app.models.inventory import Reservation, StockLot
from app.models.ops import CostEstimate, CostLine
from app.models.projects import TenderInventoryAllocation
from tests.conftest import unique


def _workflow(client, db):
    material = client.get("/api/v1/materials?search=ISMB 200").json()["items"][0]
    tender = client.post("/api/v1/tenders", json={"number": unique("AUTH"), "title": "Authoritative allocation test", "project_type": "FABRICATION"}).json()
    tender_id = tender["id"]
    boq = client.post(f"/api/v1/tenders/{tender_id}/boq", json={"line_no":"1", "raw_description":"ISMB 200 E250 IS 2062", "form":"BEAM", "grade":"E250", "quantity":"10", "unit":"MT", "material_id":material["id"]})
    assert boq.status_code == 201, boq.text
    assert client.post(f"/api/v1/tenders/{tender_id}/requirement-snapshots").status_code == 201
    workflow = client.post(f"/api/v1/tenders/{tender_id}/workflow/bom").json()
    lot = db.scalar(select(StockLot).where(StockLot.material_id == material["id"]))
    assert lot is not None
    bom_item_id = workflow["shortages"][0]["bom_item_id"]
    return tender_id, bom_item_id, {"id": str(lot.id), "reserved_qty": str(lot.reserved_qty)}


def test_allocation_reservation_release_and_authoritative_revision(apex_client, db):
    tender_id, bom_item_id, lot = _workflow(apex_client, db)
    before = D(lot["reserved_qty"])
    payload = {"bom_item_id":bom_item_id, "stock_lot_id":lot["id"], "quantity":"10", "valuation_rate":"50000", "currency":"INR", "valuation_source":{"kind":"lot_unit_cost","reference":"test"}}
    allocated = apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/inventory-allocations", json=payload)
    assert allocated.status_code == 201, allocated.text
    allocation = db.get(TenderInventoryAllocation, allocated.json()["id"])
    reservation = db.get(Reservation, allocation.reservation_id)
    assert allocation.quantity == reservation.quantity == D("10")
    assert apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/inventory-allocations", json=payload).status_code == 409

    first = apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/authoritative-estimates", json={"markup":"0.2"})
    assert first.status_code == 201, first.text
    estimate = db.get(CostEstimate, first.json()["id"])
    lines = db.scalars(select(CostLine).where(CostLine.cost_estimate_id == estimate.id)).all()
    assert estimate.total_cost == D("500000.0000")
    assert any(line.source.get("inventory_allocation_id") == str(allocation.id) for line in lines)
    second = apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/authoritative-estimates", json={"markup":"0.2"})
    assert second.status_code == 201, second.text
    revision = db.get(CostEstimate, second.json()["id"])
    assert revision.parent_estimate_id == estimate.id and revision.version == estimate.version + 1

    estimate.status = "APPROVED"; db.commit()
    locked = apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/inventory-allocations/{allocation.id}/release", json={"reason":"test"})
    assert locked.status_code == 409 and locked.json()["error"]["code"] == "ALLOCATION_LOCKED_BY_ESTIMATE"
    estimate.status = "DRAFT"; db.commit()
    released = apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/inventory-allocations/{allocation.id}/release", json={"reason":"test"})
    assert released.status_code == 200 and released.json()["status"] == "CANCELLED"
    assert apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/inventory-allocations/{allocation.id}/release", json={"reason":"again"}).json()["idempotent"] is True
    db.refresh(reservation)
    assert reservation.status == "CANCELLED"


def test_authoritative_estimate_rejects_incomplete_coverage(apex_client, db):
    tender_id, _, _ = _workflow(apex_client, db)
    response = apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/authoritative-estimates", json={"markup":"0.2"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ESTIMATE_NOT_READY"
