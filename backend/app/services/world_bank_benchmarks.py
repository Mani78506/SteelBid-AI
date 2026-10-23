"""World Bank Pink Sheet benchmark adapter.

This adapter intentionally handles only global commodity benchmarks.  It never
returns ``ProviderObservation`` and therefore cannot publish into
``price_observations`` or Indian steel-market analytics.
"""
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
from io import BytesIO

from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.market import (GlobalCommodityBenchmark, MarketSource,
    MarketSourceDocument, MarketSourceExtraction, MarketSourceProviderConfig,
    MarketSourceRefreshState)
from app.services.market_provider_registry import ProviderClass, registered_provider

WORLD_BANK_PROVIDER_ID = "WORLD_BANK_PINK_SHEET"
WORLD_BANK_MONTHLY_URL = "https://thedocs.worldbank.org/en/doc/18675f1d1639c7a34d463f59263ba0a2-0050012025/related/CMO-Historical-Data-Monthly.xlsx"
WORLD_BANK_ATTRIBUTION = "World Bank Commodity Markets, The Pink Sheet (CC BY 4.0)."
# These are globally quoted steelmaking/procurement inputs, not Indian steel prices.
ELIGIBLE_BENCHMARKS = {"Iron ore, cfr spot", "Aluminum", "Copper", "Nickel", "Zinc"}


@dataclass(frozen=True)
class BenchmarkPoint:
    commodity_name: str
    original_unit: str
    currency: str
    price_value: Decimal
    observed_on: date
    external_record_id: str


@dataclass(frozen=True)
class WorldBankWorkbook:
    checksum: str
    published_at: datetime | None
    points: list[BenchmarkPoint]
    errors: list[str]


def parse_world_bank_monthly_workbook(content: bytes) -> WorldBankWorkbook:
    """Read actual Pink Sheet layout without normalising its global units."""
    checksum = sha256(content).hexdigest()
    try:
        book = load_workbook(BytesIO(content), read_only=True, data_only=True)
        sheet = book["Monthly Prices"]
    except Exception as exc:
        return WorldBankWorkbook(checksum, None, [], [f"unsupported workbook: {exc}"])
    header_rows = list(sheet.iter_rows(min_row=4, max_row=6, values_only=True))
    updated, names, units = header_rows
    targets = {name: (index + 1, str(units[index] or "")) for index, name in enumerate(names) if name in ELIGIBLE_BENCHMARKS}
    if set(targets) != ELIGIBLE_BENCHMARKS:
        return WorldBankWorkbook(checksum, None, [], ["expected benchmark columns are missing"])
    published_at = None
    updated = updated[0]
    if isinstance(updated, str) and updated.startswith("Updated on "):
        try:
            published_at = datetime.strptime(updated.removeprefix("Updated on "), "%B %d, %Y").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    points: list[BenchmarkPoint] = []
    errors: list[str] = []
    for row_values in sheet.iter_rows(min_row=7, values_only=True):
        period = row_values[0] if row_values else None
        if not isinstance(period, str) or len(period) != 7 or period[4] != "M":
            continue
        try:
            observed_on = date(int(period[:4]), int(period[5:]), 1)
        except ValueError:
            errors.append(f"invalid period {period}"); continue
        for name, (column, unit) in targets.items():
            value = row_values[column - 1] if len(row_values) >= column else None
            if value in (None, "…", ".."):
                continue
            try:
                amount = Decimal(str(value))
                if amount <= 0:
                    raise ValueError
            except Exception:
                errors.append(f"invalid {name} value for {period}"); continue
            points.append(BenchmarkPoint(name, unit, "USD", amount, observed_on, f"{name}|{period}"))
    return WorldBankWorkbook(checksum, published_at, points, errors)


def persist_world_bank_benchmarks(db: Session, *, organization_id, source_id, content: bytes,
                                  source_url: str = WORLD_BANK_MONTHLY_URL, commit: bool = True):
    """Persist provenance and global points idempotently; never touches PriceObservation."""
    source = db.get(MarketSource, source_id)
    config = db.scalar(select(MarketSourceProviderConfig).where(MarketSourceProviderConfig.source_id == source_id))
    provider = registered_provider(WORLD_BANK_PROVIDER_ID)
    if not source or source.organization_id != organization_id:
        raise PermissionError("benchmark source is not owned by organization")
    if not config or config.provider_id != WORLD_BANK_PROVIDER_ID:
        raise PermissionError("benchmark source provider is not World Bank")
    if not (config.enabled and config.access_authorized and config.reuse_authorized):
        raise PermissionError("benchmark provider is disabled or unauthorized")
    if provider is None or provider.provider_class is not ProviderClass.FREE_PUBLIC:
        raise PermissionError("provider is not an approved free public benchmark source")
    parsed = parse_world_bank_monthly_workbook(content)
    if not parsed.points:
        raise ValueError("workbook contains no eligible benchmark observations")
    now = datetime.now(timezone.utc)
    document = db.scalar(select(MarketSourceDocument).where(MarketSourceDocument.source_id == source_id,
        MarketSourceDocument.sha256_checksum == parsed.checksum))
    if document is None:
        document = MarketSourceDocument(source_id=source_id, original_document_url=source_url,
            publisher="World Bank", document_title="Commodity Markets Price Data (The Pink Sheet)",
            published_at=parsed.published_at, reporting_period="monthly", retrieved_at=now,
            sha256_checksum=parsed.checksum, parser_version="world-bank-pink-sheet-v1",
            reuse_basis="CC BY 4.0; attribution required", extraction_status="VALID")
        db.add(document); db.flush()
    extraction = db.scalar(select(MarketSourceExtraction).where(MarketSourceExtraction.source_document_id == document.id,
        MarketSourceExtraction.parser_version == "world-bank-pink-sheet-v1"))
    inserted = 0
    if extraction is None:
        rows = [{"organization_id": organization_id, "source_document_id": document.id,
                 "commodity_name": point.commodity_name, "original_unit": point.original_unit,
                 "currency": point.currency, "price_value": point.price_value,
                 "observed_on": point.observed_on, "external_record_id": point.external_record_id}
                for point in parsed.points]
        statement = pg_insert(GlobalCommodityBenchmark).values(rows).on_conflict_do_nothing(
            constraint="uq_global_benchmark_document_point").returning(GlobalCommodityBenchmark.id)
        inserted = len(db.execute(statement).scalars().all())
        extraction = MarketSourceExtraction(source_document_id=document.id, parser_version="world-bank-pink-sheet-v1",
            status="VALID", extracted_at=now, error_summary="; ".join(parsed.errors)[:2000] or None,
            records_found=len(parsed.points), records_accepted=len(parsed.points))
        db.add(extraction)
    state = db.scalar(select(MarketSourceRefreshState).where(MarketSourceRefreshState.source_id == source_id))
    if state is None:
        state = MarketSourceRefreshState(source_id=source_id); db.add(state)
    state.last_checked_at = now; state.last_success_at = now; state.latest_document_id = document.id
    state.latest_checksum = parsed.checksum; state.error_state = None
    if commit: db.commit()
    else: db.flush()
    return document, extraction, inserted
