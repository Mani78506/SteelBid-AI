from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import select

from app.models.identity import Organization
from app.models.market import (MarketIngestionRun, MarketSource,
                               MarketSourceDocument, MarketSourceProviderConfig,
                               PriceObservation, PriceSource)
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


def _provenanced_source(db, org_id, *, provider_id="AUTHORIZED_TEST", source_org_id=None, provider_type="PUBLIC_DATA_API"):
    test_id = uuid4().hex
    market_source = MarketSource(organization_id=source_org_id or org_id, name=f"market-source-{provider_id}-{test_id}",
        provenance_classification="PROVIDER", attribution_text="Authorized test provider",
        license_status="APPROVED", visibility="OWNER_ONLY", redistribution_permitted=True)
    db.add(market_source); db.flush()
    db.add(MarketSourceProviderConfig(source_id=market_source.id, provider_id=provider_id,
        provider_type=provider_type, enabled=True, access_authorized=True, reuse_authorized=True,
        parser_id="contract-test", parser_version="v1", refresh_interval_seconds=3600))
    document = MarketSourceDocument(source_id=market_source.id, original_document_url="https://provider.example/record",
        publisher="Authorized test provider", document_title="Test record", sha256_checksum="a" * 64,
        retrieved_at=datetime.now(timezone.utc), extraction_status="VALID")
    price_source = PriceSource(organization_id=org_id, name=f"provider-price-{provider_id}-{test_id}",
        source_type="PROVIDER", provider_key=provider_id, is_synthetic=False)
    db.add_all([document, price_source]); db.commit()
    return price_source, document


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

    def test_document_provenance_is_atomic_and_idempotent(self, db):
        org = db.scalar(select(Organization).where(Organization.name.like("%Apex%")))
        source, document = _provenanced_source(db, org.id)
        run = ingest_observations(db, organization_id=org.id, source_id=source.id, provider_key="AUTHORIZED_TEST",
            idempotency_key="document-one", source_document_id=document.id,
            observations=[_obs(external_record_id="provider-row-1")])
        stored = db.scalar(select(PriceObservation).where(PriceObservation.source_id == source.id))
        assert run.inserted_count == 1 and stored.source_document_id == document.id
        assert stored.external_observation_id == "provider-row-1"
        repeat = ingest_observations(db, organization_id=org.id, source_id=source.id, provider_key="AUTHORIZED_TEST",
            idempotency_key="document-two", source_document_id=document.id,
            observations=[_obs(external_record_id="provider-row-1")])
        assert repeat.duplicate_count == 1 and repeat.inserted_count == 0

    def test_document_provenance_rejects_missing_mismatched_and_fixture_sources(self, db):
        apex = db.scalar(select(Organization).where(Organization.name.like("%Apex%")))
        metro = db.scalar(select(Organization).where(Organization.name.like("%Metro%")))
        source, document = _provenanced_source(db, apex.id)
        try:
            ingest_observations(db, organization_id=apex.id, source_id=source.id, provider_key="AUTHORIZED_TEST",
                idempotency_key="missing-document", source_document_id=uuid4(), observations=[_obs()])
            assert False, "unknown document must fail"
        except ValueError: pass
        db.rollback()
        other_source, other_document = _provenanced_source(db, metro.id, provider_id="METRO_PROVIDER")
        try:
            ingest_observations(db, organization_id=apex.id, source_id=source.id, provider_key="AUTHORIZED_TEST",
                idempotency_key="wrong-org", source_document_id=other_document.id, observations=[_obs()])
            assert False, "cross-tenant document must fail"
        except PermissionError: pass
        db.rollback()
        fixture_source, fixture_document = _provenanced_source(db, apex.id, provider_id="FIXTURE_PROVIDER", provider_type="FIXTURE_TEST")
        try:
            ingest_observations(db, organization_id=apex.id, source_id=fixture_source.id, provider_key="FIXTURE_PROVIDER",
                idempotency_key="fixture", source_document_id=fixture_document.id, observations=[_obs()])
            assert False, "fixture document must not publish genuine prices"
        except PermissionError: pass

    def test_document_provenance_rolls_back_with_caller_transaction(self, db):
        org = db.scalar(select(Organization).where(Organization.name.like("%Apex%")))
        source, document = _provenanced_source(db, org.id)
        db.rollback()
        try:
            with db.begin():
                ingest_observations(db, organization_id=org.id, source_id=source.id, provider_key="AUTHORIZED_TEST",
                    idempotency_key="rollback-document", source_document_id=document.id,
                    observations=[_obs()], commit=False)
                raise RuntimeError("force transaction rollback")
        except RuntimeError: pass
        assert db.scalar(select(PriceObservation).where(PriceObservation.source_id == source.id)) is None
        assert db.scalar(select(MarketIngestionRun).where(MarketIngestionRun.provider_key == "AUTHORIZED_TEST",
            MarketIngestionRun.idempotency_key == "rollback-document")) is None

    def test_provider_contracts_are_safe_when_unconfigured(self):
        assert DemoProvider().report_ingestion_status()["configured"] is True
        assert CsvProvider().report_ingestion_status()["publishes"] is False
        try:
            ExternalApiProvider().fetch_observations()
            assert False, "external provider must remain disabled"
        except RuntimeError: pass
