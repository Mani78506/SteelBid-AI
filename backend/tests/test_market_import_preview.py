import io
import uuid
from sqlalchemy import select

from app.models.identity import Organization, User
from app.models.market import MarketImportBatch, MarketImportStagedRow, MarketSource, PriceObservation


def _approved_source(db):
    org = db.scalars(select(Organization).where(Organization.name.contains("Apex"))).first()
    source = MarketSource(organization_id=org.id, name=f"Approved fixture {uuid.uuid4()}",
                          provenance_classification="OFFICIAL_REFERENCE", attribution_text="Fixture attribution",
                          license_status="APPROVED", visibility="OWNER_ONLY", redistribution_permitted=False)
    db.add(source); db.commit()
    return source


def test_preview_persists_rows_without_publishing_observations(apex_client, db):
    source = _approved_source(db)
    before = len(db.scalars(select(PriceObservation)).all())
    csv = b"material_form,grade,region,price_per_unit,currency,unit,price_basis,observed_on\nHRC,E250,West India,56000,INR,MT,EX_WORKS,2026-10-21\nCRC,,North India,0,INR,MT,,bad-date\n"
    response = apex_client.post(f"/api/v1/market/imports/preview?source_id={source.id}",
                                headers={"Idempotency-Key": "preview-fixture-1"},
                                files={"file": ("prices.csv", io.BytesIO(csv), "text/csv")})
    assert response.status_code == 201, response.text
    data = response.json()
    assert (data["total_rows"], data["valid_rows"], data["invalid_rows"]) == (2, 1, 1)
    assert data["rows"][1]["errors"]
    batch = db.get(MarketImportBatch, data["batch_id"])
    assert batch.organization_id == source.organization_id
    assert len(db.scalars(select(MarketImportStagedRow).where(MarketImportStagedRow.batch_id == batch.id)).all()) == 2
    assert len(db.scalars(select(PriceObservation)).all()) == before


def test_preview_idempotency_and_tenant_source_isolation(apex_client, metro_client, db):
    source = _approved_source(db)
    csv = b"material_form,grade,region,price_per_unit,currency,unit,price_basis,observed_on\nHRC,E250,West India,56000,INR,MT,EX_WORKS,2026-10-21\n"
    url = f"/api/v1/market/imports/preview?source_id={source.id}"
    first = apex_client.post(url, headers={"Idempotency-Key": "preview-fixture-2"}, files={"file": ("prices.csv", io.BytesIO(csv), "text/csv")})
    replay = apex_client.post(url, headers={"Idempotency-Key": "preview-fixture-2"}, files={"file": ("prices.csv", io.BytesIO(csv), "text/csv")})
    assert first.status_code == replay.status_code == 201
    assert replay.json()["idempotent_replay"] is True
    forbidden = metro_client.post(url, headers={"Idempotency-Key": "metro-preview"}, files={"file": ("prices.csv", io.BytesIO(csv), "text/csv")})
    assert forbidden.status_code == 404
