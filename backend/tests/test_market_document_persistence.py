from datetime import datetime, timezone
from sqlalchemy import func, select
from app.models.identity import Organization
from app.models.market import MarketSource, MarketSourceDocument, MarketSourceExtraction, MarketSourceRefreshState, PriceObservation
from app.services.market_document_parser import parse_fixture_csv
from app.services.market_document_persistence import persist_fixture_extraction

CSV=b"material_form,grade,region,price_per_unit,currency,unit,price_basis,observed_on\nHRC,E250,West,50000,INR,MT,EX_WORKS,2026-01-01\n"
def test_fixture_persistence_is_idempotent_and_non_publishing(db):
    apex_org = db.scalar(select(Organization).where(Organization.name.ilike("%Apex%")))
    assert apex_org is not None
    source=MarketSource(organization_id=apex_org.id,name="fixture persistence",provenance_classification="FIXTURE_TEST",attribution_text="test",license_status="APPROVED",visibility="OWNER_ONLY",redistribution_permitted=False); db.add(source); db.commit()
    result=parse_fixture_csv(CSV)
    first,_=persist_fixture_extraction(db,source_id=source.id,url="fixture://one",publisher="test",title="fixture",published_at=datetime.now(timezone.utc),reporting_period="2026-01",result=result)
    persist_fixture_extraction(db,source_id=source.id,url="fixture://one",publisher="test",title="fixture",published_at=datetime.now(timezone.utc),reporting_period="2026-01",result=result)
    assert db.scalar(select(func.count()).select_from(MarketSourceDocument).where(MarketSourceDocument.source_id==source.id))==1
    assert db.scalar(select(func.count()).select_from(MarketSourceExtraction).where(MarketSourceExtraction.source_document_id==first.id))==1
    assert db.scalar(select(func.count()).select_from(PriceObservation).where(PriceObservation.source_document_id==first.id))==0
    assert db.scalar(select(MarketSourceRefreshState).where(MarketSourceRefreshState.source_id==source.id)).latest_checksum==result.checksum
