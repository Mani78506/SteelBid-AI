from datetime import date, timedelta
from sqlalchemy import select

from app.models.identity import Organization
from app.models.market import MarketPriceAlertEvent, PriceSource
from app.models.ops import Notification
from app.services.market_ingestion import ingest_observations
from app.services.market_providers import ProviderObservation


def _source(db, org_id):
    source = PriceSource(organization_id=org_id, name=f"alerts-{org_id}", source_type="MANUAL", is_synthetic=False)
    db.add(source); db.commit(); return source

def _row(price, day):
    return ProviderObservation(material_form="ALERT_TEST", grade="E250", region="West India", price_per_unit=str(price),
        currency="INR", unit="MT", price_basis="EX_WORKS", observed_on=day)

class TestMarketAlerts:
    def test_threshold_crossing_creates_one_linked_notification(self, db, apex_client):
        org = db.scalar(select(Organization).where(Organization.name.like("%Apex%"))); source = _source(db, org.id)
        alert = apex_client.post("/api/v1/market/alerts", json={"material_form":"ALERT_TEST","grade":"E250","region":"West India","currency":"INR","unit":"MT","price_basis":"EX_WORKS","source_id":str(source.id),"price_condition":"ABOVE","price_threshold":"55000"})
        assert alert.status_code == 201
        ingest_observations(db, organization_id=org.id, source_id=source.id, provider_key="TEST", idempotency_key="a1", observations=[_row(54000, date.today()-timedelta(days=2))])
        ingest_observations(db, organization_id=org.id, source_id=source.id, provider_key="TEST", idempotency_key="a2", observations=[_row(56000, date.today()-timedelta(days=1))])
        ingest_observations(db, organization_id=org.id, source_id=source.id, provider_key="TEST", idempotency_key="a3", observations=[_row(57000, date.today())])
        assert len(db.scalars(select(MarketPriceAlertEvent)).all()) == 1
        event = db.scalar(select(MarketPriceAlertEvent)); assert db.get(Notification, event.notification_id).link.startswith("/market?observation_id=")
        history = apex_client.get("/api/v1/market/alerts/history").json(); assert len(history["items"]) == 1

    def test_below_mismatch_and_stale_do_not_trigger(self, db, apex_client):
        org = db.scalar(select(Organization).where(Organization.name.like("%Apex%"))); source = _source(db, org.id)
        response = apex_client.post("/api/v1/market/alerts", json={"material_form":"ALERT_LOW","grade":"E250","region":"West India","currency":"INR","unit":"MT","price_basis":"EX_WORKS","price_condition":"BELOW","price_threshold":"50000"})
        assert response.status_code == 201
        before = len(db.scalars(select(MarketPriceAlertEvent)).all())
        wrong = ProviderObservation(material_form="ALERT_LOW", grade="E250", region="North India", price_per_unit="49000",currency="INR",unit="MT",price_basis="EX_WORKS",observed_on=date.today())
        stale = ProviderObservation(material_form="ALERT_LOW", grade="E250", region="West India", price_per_unit="49000",currency="INR",unit="MT",price_basis="EX_WORKS",observed_on=date.today()-timedelta(days=20))
        ingest_observations(db, organization_id=org.id, source_id=source.id, provider_key="TEST", idempotency_key="b1", observations=[wrong, stale])
        assert len(db.scalars(select(MarketPriceAlertEvent)).all()) == before

    def test_alert_api_is_tenant_scoped(self, db, apex_client, metro_client):
        org = db.scalar(select(Organization).where(Organization.name.like("%Apex%"))); source = _source(db, org.id)
        created = apex_client.post("/api/v1/market/alerts", json={"material_form":"ALERT_PRIVATE","grade":"E250","region":"West India","currency":"INR","unit":"MT","price_basis":"EX_WORKS","source_id":str(source.id),"price_condition":"ABOVE","price_threshold":"1"}).json()
        assert metro_client.get("/api/v1/market/alerts").json()["items"] == []
        assert metro_client.patch(f"/api/v1/market/alerts/{created['id']}", json={"is_active":False}).status_code == 404
