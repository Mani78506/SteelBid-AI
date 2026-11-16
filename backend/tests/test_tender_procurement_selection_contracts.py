"""Tender shortage procurement: existing contracts, compatibility and audit safety."""
from datetime import date, timedelta

from tests.conftest import unique


def _prepared_tender(apex_client):
    material = apex_client.get("/api/v1/materials?search=ISMB%20200").json()["items"][0]
    tender = apex_client.post("/api/v1/tenders", json={
        "number": unique("TND-SEL"), "title": "Supplier selection contract", "project_type": "FABRICATION",
    }).json()
    boq = apex_client.post(f"/api/v1/tenders/{tender['id']}/boq", json={
        "line_no": "1", "raw_description": "ISMB 200 E250", "form": "BEAM", "grade": "E250",
        "quantity": "100", "unit": "MT", "material_id": material["id"],
    })
    assert boq.status_code == 201, boq.text
    assert apex_client.post(f"/api/v1/tenders/{tender['id']}/requirement-snapshots").status_code == 201
    assert apex_client.post(f"/api/v1/tenders/{tender['id']}/workflow/bom").status_code == 201
    snapshot = apex_client.get(f"/api/v1/tenders/{tender['id']}/requirement-snapshots").json()[0]
    return tender, material, snapshot


def test_supplier_selection_rejects_expired_or_overlapping_offers_and_audits_cancel(apex_client, metro_client, viewer_client):
    tender, material, snapshot = _prepared_tender(apex_client)
    supplier = apex_client.get("/api/v1/suppliers?page_size=1").json()["items"][0]
    valid = apex_client.post("/api/v1/procurement/supplier-quotes", json={
        "supplier_id": supplier["id"], "material_id": material["id"], "quantity": "100", "unit": "MT",
        "unit_price": "50000", "freight_per_unit": "500", "currency": "INR",
        "valid_until": str(date.today() + timedelta(days=10)),
    })
    assert valid.status_code == 201, valid.text
    expired = apex_client.post("/api/v1/procurement/supplier-quotes", json={
        "supplier_id": supplier["id"], "material_id": material["id"], "quantity": "100", "unit": "MT",
        "unit_price": "49000", "currency": "INR", "valid_until": str(date.today() - timedelta(days=1)),
    })
    assert expired.status_code == 201, expired.text

    offers = apex_client.get(f"/api/v1/tenders/{tender['id']}/requirement-snapshots/{snapshot['id']}/supplier-offers")
    assert offers.status_code == 200
    rows = {row["supplier_quote_id"]: row for row in offers.json()["items"]}
    assert rows[valid.json()["id"]]["comparison_status"] == "COMPATIBLE"
    assert rows[expired.json()["id"]]["comparison_status"] == "EXPIRED"
    assert rows[valid.json()["id"]]["currency"] == "INR"
    assert rows[valid.json()["id"]]["freight_per_unit"] == "500.0000"

    bad = apex_client.post(f"/api/v1/tenders/{tender['id']}/requirement-snapshots/{snapshot['id']}/supplier-selections", json={"supplier_quote_id": expired.json()["id"], "selected_qty": "1"})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "INCOMPATIBLE_SUPPLIER_OFFER"
    selected = apex_client.post(f"/api/v1/tenders/{tender['id']}/requirement-snapshots/{snapshot['id']}/supplier-selections", json={"supplier_quote_id": valid.json()["id"], "selected_qty": "60"})
    assert selected.status_code == 201, selected.text
    duplicate = apex_client.post(f"/api/v1/tenders/{tender['id']}/requirement-snapshots/{snapshot['id']}/supplier-selections", json={"supplier_quote_id": valid.json()["id"], "selected_qty": "1"})
    assert duplicate.status_code == 409
    assert apex_client.post(f"/api/v1/tenders/{tender['id']}/supplier-selections/{selected.json()['id']}/cancel", json={"reason": "Supplier revised delivery"}).status_code == 200
    history = apex_client.get(f"/api/v1/tenders/{tender['id']}/supplier-selections/history").json()
    assert history[0]["status"] == "CANCELLED" and history[0]["reason"] == "Supplier revised delivery"

    assert metro_client.get(f"/api/v1/tenders/{tender['id']}/supplier-selections").status_code == 404
    assert viewer_client.post(f"/api/v1/tenders/{tender['id']}/workflow/procurement-requirements").status_code == 403
