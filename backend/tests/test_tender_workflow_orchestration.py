"""Persisted tender workflow: approved BOQ -> traceable BOM -> estimate -> quotation."""
from decimal import Decimal as D

from tests.conftest import unique


def test_tender_workflow_is_traceable_idempotent_and_tenant_scoped(apex_client, railbuild_client):
    customer = apex_client.get("/api/v1/customers?search=Konkan").json()["items"][0]
    material = apex_client.get("/api/v1/materials?search=ISMB 200").json()["items"][0]
    tender = apex_client.post("/api/v1/tenders", json={
        "number": unique("TND-WF"), "title": "Workflow test steel supply",
        "project_type": "FABRICATION"}).json()
    tender_id = tender["id"]
    boq = apex_client.post(f"/api/v1/tenders/{tender_id}/boq", json={
        "line_no": "1", "raw_description": "ISMB 200 E250 / IS 2062",
        "form": "BEAM", "grade": "E250", "quantity": "100", "unit": "MT",
        "material_id": material["id"]})
    assert boq.status_code == 201, boq.text

    snapshot = apex_client.post(f"/api/v1/tenders/{tender_id}/requirement-snapshots")
    assert snapshot.status_code == 201, snapshot.text
    snapshots = apex_client.get(f"/api/v1/tenders/{tender_id}/requirement-snapshots").json()
    assert len(snapshots) == 1 and D(snapshots[0]["quantity"]) == D("100")

    bom = apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/bom")
    assert bom.status_code == 201, bom.text
    wf = bom.json()
    assert wf["bom_version_id"] and D(wf["shortages"][0]["required_quantity"]) == D("100")
    assert D(wf["shortages"][0]["shortage_quantity"]) == D("60")  # Apex has 40 allocatable MT
    # Repeated click reuses the persisted BOM rather than creating a duplicate.
    assert apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/bom").json()["bom_version_id"] == wf["bom_version_id"]

    # Current persisted shortage becomes one idempotent, internal-only draft requirement.
    procurement = apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/procurement-requirements")
    assert procurement.status_code == 201, procurement.text
    assert procurement.json()["status"] == "DRAFT" and procurement.json()["lines"] == 1
    assert apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/procurement-requirements").json()["id"] == procurement.json()["id"]
    requirements = apex_client.get(f"/api/v1/tenders/{tender_id}/workflow/procurement-requirements").json()
    assert D(requirements["items"][0]["quantity"]) == D("60")
    supplier = apex_client.get("/api/v1/suppliers?page_size=1").json()["items"][0]
    rfq = apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/draft-rfqs", json={"supplier_ids": [supplier["id"]]})
    assert rfq.status_code == 201, rfq.text
    assert rfq.json()["rfqs"][0]["status"] == "DRAFT"  # never issued or sent automatically

    assert apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/customer", json={
        "customer_id": customer["id"]}).status_code == 200
    estimate = apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/estimate", json={
        "demo_rates": [{"tender_requirement_snapshot_id": snapshots[0]["id"], "unit_rate": "56000"}],
        "processing_cost": "10000", "freight_cost": "5000", "testing_cost": "2000",
        "overhead_cost": "3000", "contingency_pct": "0.05"})
    assert estimate.status_code == 201, estimate.text
    wf = estimate.json()
    assert wf["use_demo_commercial_rates"] is True and wf["cost_estimate_id"]
    ce = apex_client.get(f"/api/v1/finance/cost-estimates/{wf['cost_estimate_id']}").json()
    assert D(ce["material_cost"]) == D("5600000.0000")
    assert D(ce["total_cost"]) == D("5901000.0000")

    quote = apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/quotation", json={"target_margin": "0.12"})
    assert quote.status_code == 201, quote.text
    quotation_id = quote.json()["quotation_id"]
    assert quotation_id
    exported = apex_client.get(f"/api/v1/quotations/{quotation_id}/export")
    assert exported.status_code == 200 and "Quotation" in exported.text and customer["name"] in exported.text
    for suffix in ("boq.xlsx", "bom.xlsx", "estimate.xlsx"):
        download = apex_client.get(f"/api/v1/tenders/{tender_id}/workflow/{suffix}")
        assert download.status_code == 200 and download.content[:2] == b"PK"  # valid XLSX zip container
    pdf = apex_client.get(f"/api/v1/tenders/{tender_id}/workflow/quotation.pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf" and pdf.content[:4] == b"%PDF"
    submitted = apex_client.post(f"/api/v1/tenders/{tender_id}/workflow/submission", json={
        "status": "MANUALLY_SUBMITTED", "external_submission_reference": "TEST-REF-001"})
    assert submitted.status_code == 200
    assert submitted.json()["submission_status"] == "MANUALLY_SUBMITTED"
    assert apex_client.get(f"/api/v1/tenders/{tender_id}/workflow").json()["external_submission_reference"] == "TEST-REF-001"
    assert railbuild_client.get(f"/api/v1/tenders/{tender_id}/workflow").status_code == 404
