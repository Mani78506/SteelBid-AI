from datetime import datetime, timezone
from io import BytesIO
from uuid import uuid4
from openpyxl import Workbook
from sqlalchemy import func, select

from app.models.identity import Organization
from app.models.market import (GlobalCommodityBenchmark, MarketSource,
    MarketSourceDocument, MarketSourceProviderConfig, PriceObservation)
from app.services.world_bank_benchmarks import (ELIGIBLE_BENCHMARKS,
    parse_world_bank_monthly_workbook, persist_world_bank_benchmarks)


def _workbook():
    book = Workbook(); sheet = book.active; sheet.title = "Monthly Prices"
    sheet.cell(4, 1, "Updated on January 06, 2025")
    names = [None, "Aluminum", "Iron ore, cfr spot", "Copper", "Nickel", "Zinc"]
    units = [None, "($/mt)", "($/dmtu)", "($/mt)", "($/mt)", "($/mt)"]
    for column, value in enumerate(names, 1): sheet.cell(5, column, value)
    for column, value in enumerate(units, 1): sheet.cell(6, column, value)
    sheet.append(["2024M01", 2200, 120, 8500, 16000, 2500])
    sheet.append(["2024M02", 2250, 125, 8600, 16100, 2550])
    content = BytesIO(); book.save(content); return content.getvalue()


def _configured_source(db, org):
    source = MarketSource(organization_id=org.id, name=f"World Bank {uuid4().hex}", provenance_classification="PROVIDER",
        attribution_text="World Bank Commodity Markets, The Pink Sheet", license_status="APPROVED",
        visibility="OWNER_ONLY", redistribution_permitted=True)
    db.add(source); db.flush()
    db.add(MarketSourceProviderConfig(source_id=source.id, provider_id="WORLD_BANK_PINK_SHEET",
        provider_type="OFFICIAL_DOCUMENT", enabled=True, access_authorized=True, reuse_authorized=True,
        parser_id="world-bank-pink-sheet", parser_version="world-bank-pink-sheet-v1", refresh_interval_seconds=86400))
    db.commit(); return source


def test_world_bank_workbook_parser_preserves_original_units_and_dates():
    parsed = parse_world_bank_monthly_workbook(_workbook())
    assert not parsed.errors and len(parsed.points) == 10
    iron = next(point for point in parsed.points if point.commodity_name == "Iron ore, cfr spot")
    assert iron.original_unit == "($/dmtu)" and iron.currency == "USD"
    assert iron.observed_on.isoformat() == "2024-01-01" and len(parsed.checksum) == 64


def test_benchmark_persistence_is_idempotent_and_isolated(db):
    apex = db.scalar(select(Organization).where(Organization.name.ilike("%Apex%")))
    source = _configured_source(db, apex)
    before_prices = db.scalar(select(func.count()).select_from(PriceObservation))
    document, extraction, inserted = persist_world_bank_benchmarks(db, organization_id=apex.id, source_id=source.id, content=_workbook())
    assert inserted == 10 and extraction.records_accepted == 10
    assert document.publisher == "World Bank" and document.reuse_basis.startswith("CC BY 4.0")
    _, _, repeat = persist_world_bank_benchmarks(db, organization_id=apex.id, source_id=source.id, content=_workbook())
    assert repeat == 0
    assert db.scalar(select(func.count()).select_from(GlobalCommodityBenchmark).where(GlobalCommodityBenchmark.organization_id == apex.id)) == 10
    assert db.scalar(select(func.count()).select_from(PriceObservation)) == before_prices


def test_benchmark_provider_authorization_and_tenant_isolation(db):
    apex = db.scalar(select(Organization).where(Organization.name.ilike("%Apex%")))
    metro = db.scalar(select(Organization).where(Organization.name.ilike("%Metro%")))
    source = _configured_source(db, apex)
    try:
        persist_world_bank_benchmarks(db, organization_id=metro.id, source_id=source.id, content=_workbook())
        assert False, "cross-tenant source must fail"
    except PermissionError: pass


def test_benchmark_api_is_tenant_scoped_and_never_returns_price_observations(db, apex_client, metro_client):
    apex = db.scalar(select(Organization).where(Organization.name.ilike("%Apex%")))
    source = _configured_source(db, apex)
    persist_world_bank_benchmarks(db, organization_id=apex.id, source_id=source.id, content=_workbook())
    response = apex_client.get("/api/v1/market/benchmarks")
    assert response.status_code == 200
    payload = response.json()
    assert payload["classification"] == "GLOBAL_COMMODITY_BENCHMARKS_NOT_INDIAN_STEEL_PRICES"
    assert {item["commodity_name"] for item in payload["items"]} == ELIGIBLE_BENCHMARKS
    assert all(item["currency"] == "USD" for item in payload["items"])
    assert metro_client.get("/api/v1/market/benchmarks").json()["items"] == []
    db.rollback()
    config = db.scalar(select(MarketSourceProviderConfig).where(MarketSourceProviderConfig.source_id == source.id)); config.enabled = False; db.commit()
    try:
        persist_world_bank_benchmarks(db, organization_id=apex.id, source_id=source.id, content=_workbook())
        assert False, "disabled provider must fail"
    except PermissionError: pass
