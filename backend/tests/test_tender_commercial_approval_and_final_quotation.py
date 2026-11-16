"""Isolated endpoint coverage for authoritative approval and final quotation gating."""
from decimal import Decimal as D

from sqlalchemy import select

from app.models.ops import CostEstimate, CostLine
from app.models.projects import TenderInventoryAllocation
from app.models.sales import QuotationVersion
from app.models.inventory import StockLot
from tests.conftest import login, unique


def _ready_estimate(client, db):
    material = client.get("/api/v1/materials?search=ISMB 200").json()["items"][0]
    tender = client.post("/api/v1/tenders", json={"number": unique("APPROVAL"), "title": "Approval test", "project_type": "FABRICATION"}).json()
    tid = tender["id"]
    assert client.post(f"/api/v1/tenders/{tid}/boq", json={"line_no":"1", "raw_description":"ISMB 200 E250", "form":"BEAM", "grade":"E250", "quantity":"10", "unit":"MT", "material_id":material["id"]}).status_code == 201
    assert client.post(f"/api/v1/tenders/{tid}/requirement-snapshots").status_code == 201
    workflow = client.post(f"/api/v1/tenders/{tid}/workflow/bom").json()
    lot = db.scalar(select(StockLot).where(StockLot.material_id == material["id"]))
    allocation = client.post(f"/api/v1/tenders/{tid}/workflow/inventory-allocations", json={
        "bom_item_id": workflow["shortages"][0]["bom_item_id"], "stock_lot_id": str(lot.id), "quantity":"10",
        "valuation_rate":"50000", "currency":"INR", "valuation_source":{"kind":"test","reference":"approval"}})
    assert allocation.status_code == 201, allocation.text
    estimate = client.post(f"/api/v1/tenders/{tid}/workflow/authoritative-estimates", json={"markup":"0.2"})
    assert estimate.status_code == 201, estimate.text
    return tid, estimate.json()["id"], allocation.json()["id"]


def test_authoritative_approval_lifecycle_and_history(apex_client, client, db):
    tender_id, estimate_id, _ = _ready_estimate(apex_client, db)
    submitted = apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/authoritative-estimates/{estimate_id}/submit-review", json={"remarks":"ready"})
    assert submitted.status_code == 200
    assert apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/authoritative-estimates/{estimate_id}/submit-review", json={}).status_code == 409
    assert apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/authoritative-estimates/{estimate_id}/approve", json={}).status_code == 409
    login(client, "finance@apex.demo")
    approved = client.post(f"/api/v1/tenders/{tender_id}/workflow/authoritative-estimates/{estimate_id}/approve", json={"remarks":"approved"})
    assert approved.status_code == 200, approved.text
    history = client.get(f"/api/v1/tenders/{tender_id}/workflow/authoritative-estimates/{estimate_id}/approvals").json()["items"]
    assert len(history) == 1 and history[0]["status"] == "APPROVED" and history[0]["remarks"] == "approved"
    assert client.post(f"/api/v1/tenders/{tender_id}/workflow/authoritative-estimates/{estimate_id}/approve", json={}).status_code == 409


def test_revalidation_and_final_quotation_are_approval_gated(apex_client, metro_client, client, db):
    tender_id, estimate_id, allocation_id = _ready_estimate(apex_client, db)
    assert metro_client.get(f"/api/v1/tenders/{tender_id}/workflow/authoritative-estimates/{estimate_id}/approvals").status_code == 404
    assert apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/authoritative-estimates/{estimate_id}/submit-review", json={}).status_code == 200
    assert apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/inventory-allocations/{allocation_id}/release", json={"reason":"invalidate source"}).status_code == 200
    login(client, "finance@apex.demo")
    blocked = client.post(f"/api/v1/tenders/{tender_id}/workflow/authoritative-estimates/{estimate_id}/approve", json={})
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "REVALIDATION_REQUIRED"

    tender_id, estimate_id, _ = _ready_estimate(apex_client, db)
    assert apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/authoritative-estimates/{estimate_id}/submit-review", json={}).status_code == 200
    assert client.post(f"/api/v1/tenders/{tender_id}/workflow/authoritative-estimates/{estimate_id}/approve", json={}).status_code == 200
    customer = apex_client.get("/api/v1/customers?page_size=1").json()["items"][0]
    assert apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/customer", json={"customer_id":customer["id"]}).status_code == 200
    created = apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/final-quotation", json={})
    assert created.status_code == 201, created.text
    version = db.scalar(select(QuotationVersion).where(QuotationVersion.cost_estimate_id == estimate_id))
    assert version is not None and version.total_estimated_cost == D("500000.0000") and version.status == "DRAFT"
    assert db.get(CostEstimate, estimate_id).status == "APPROVED"
    assert db.scalars(select(CostLine).where(CostLine.cost_estimate_id == estimate_id)).all()


def test_reject_return_and_unauthorized_decisions(apex_client, viewer_client, client, db):
    tender_id, estimate_id, _ = _ready_estimate(apex_client, db)
    assert apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/authoritative-estimates/{estimate_id}/submit-review", json={}).status_code == 200
    assert viewer_client.post(f"/api/v1/tenders/{tender_id}/workflow/authoritative-estimates/{estimate_id}/approve", json={}).status_code == 403
    login(client, "finance@apex.demo")
    assert client.post(f"/api/v1/tenders/{tender_id}/workflow/authoritative-estimates/{estimate_id}/reject", json={}).status_code == 400
    rejected = client.post(f"/api/v1/tenders/{tender_id}/workflow/authoritative-estimates/{estimate_id}/reject", json={"remarks":"commercial risk"})
    assert rejected.status_code == 200 and rejected.json()["status"] == "REJECTED"

    tender_id, estimate_id, _ = _ready_estimate(apex_client, db)
    assert apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/authoritative-estimates/{estimate_id}/submit-review", json={}).status_code == 200
    assert client.post(f"/api/v1/tenders/{tender_id}/workflow/authoritative-estimates/{estimate_id}/return-for-revision", json={}).status_code == 400
    returned = client.post(f"/api/v1/tenders/{tender_id}/workflow/authoritative-estimates/{estimate_id}/return-for-revision", json={"remarks":"update freight evidence"})
    assert returned.status_code == 200 and returned.json()["status"] == "RETURNED"
