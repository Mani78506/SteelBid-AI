from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy import select

from app.models.identity import Organization
from app.models.market import MarketIngestionRun, PriceObservation, PriceSource
from app.services.market_ingestion import ingest_observations
from app.services.market_providers import CsvProvider, DemoProvider, ExternalApiProvider, ProviderObservation


def _source(db, org_id, *, synthetic=False):
    source = PriceSource(organization_id=org_id, name=f"ingestion-{synthetic}-{org_id}",
                         source_type="SYNTHETIC" if synthetic else "MANUAL", is_synthetic=synthetic)
    db.add(source); db.commit(); return source


def _obs(price="56000.1234", **overrides):
    values = {"material_form": "HRC", "grade": "E250", "region": "West India",
        "price_per_unit": price, "currency": "INR", "unit": "MT", "price_basis": "EX_WORKS",
        "observed_on": date.today() - timedelta(days=1)}
    values.update(overrides)
    return ProviderObservation(**values)


class TestMarketIngestion:
    def test_normalises_decimal_persists_run_and_deduplicates(self, db):
        org = db.scalar(select(Organization).where(Organization.name.like("%Apex%")))
        source = _source(db, org.id)
        run = ingest_observations(db, organization_id=org.id, source_id=source.id, provider_key="TEST",
                                  idempotency_key="one", observations=[_obs()])
        assert run.status == "SUCCEEDED" and run.inserted_count == 1
        stored = db.scalar(select(PriceObservation).where(PriceObservation.source_id == source.id))
        assert stored.price_per_unit == Decimal("56000.1234")
        repeat = ingest_observations(db, organization_id=org.id, source_id=source.id, provider_key="TEST",
                                     idempotency_key="one", observations=[_obs()])
        assert repeat.id == run.id and repeat.inserted_count == 1
        second = ingest_observations(db, organization_id=org.id, source_id=source.id, provider_key="TEST",
                                     idempotency_key="two", observations=[_obs()])
        assert second.duplicate_count == 1 and second.inserted_count == 0
        assert db.scalar(select(MarketIngestionRun).where(MarketIngestionRun.id == run.id))

    def test_rejects_invalid_and_preserves_valid_rows(self, db):
        org = db.scalar(select(Organization).where(Organization.name.like("%Apex%")))
        source = _source(db, org.id)
        run = ingest_observations(db, organization_id=org.id, source_id=source.id, provider_key="TEST",
            idempotency_key="partial", observations=[_obs(), _obs(price="bad", region="North India")])
        assert run.status == "PARTIAL" and run.inserted_count == 1 and run.rejected_count == 1

    def test_source_and_demo_isolation(self, db):
        apex = db.scalar(select(Organization).where(Organization.name.like("%Apex%")))
        metro = db.scalar(select(Organization).where(Organization.name.like("%Metro%")))
        source = _source(db, apex.id)
        try:
            ingest_observations(db, organization_id=metro.id, source_id=source.id, provider_key="TEST", idempotency_key="bad", observations=[_obs()])
            assert False, "cross tenant source must fail"
        except PermissionError: pass
        try:
            ingest_observations(db, organization_id=apex.id, source_id=source.id, provider_key="TEST", idempotency_key="synthetic", observations=[_obs()], is_synthetic=True)
            assert False, "synthetic provenance mismatch must fail"
        except PermissionError: pass

    def test_provider_contracts_are_safe_when_unconfigured(self):
        assert DemoProvider().report_ingestion_status()["configured"] is True
        assert CsvProvider().report_ingestion_status()["publishes"] is False
        try:
            ExternalApiProvider().fetch_observations()
            assert False, "external provider must remain disabled"
        except RuntimeError: pass
