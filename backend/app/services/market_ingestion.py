from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.identity import Organization
from app.models.market import (MarketIngestionRun, MarketSource,
                               MarketSourceDocument, MarketSourceProviderConfig,
                               PriceObservation, PriceSource)
from app.services.market_providers import ProviderObservation

_CURRENCIES = {"INR", "USD", "EUR", "GBP"}
_UNITS = {"MT", "KG"}
_BASES = {"EX_WORKS", "DELIVERED", "FORWARD"}


def provider_classification(db: Session, observation: PriceObservation) -> str:
    """Display classification; a provider class never substitutes for provenance validation."""
    if observation.is_synthetic:
        return "DEMO"
    if observation.source_document_id is None:
        return "UNVERIFIED"
    document = db.get(MarketSourceDocument, observation.source_document_id)
    if document is None:
        return "UNVERIFIED"
    config = db.scalar(select(MarketSourceProviderConfig).where(
        MarketSourceProviderConfig.source_id == document.source_id))
    # The document itself is retained and attributable, but provider activation
    # is still pending. Do not overstate this as externally verified.
    if config is None or not (config.enabled and config.access_authorized and config.reuse_authorized):
        return "SOURCE_DOCUMENTED"
    from app.services.market_provider_registry import registered_provider
    registered = registered_provider(config.provider_id)
    return str(registered.provider_class) if registered else "AUTHORIZED_PROVIDER"

def _normalise(raw: ProviderObservation) -> dict:
    try: price = Decimal(str(raw.price_per_unit))
    except (InvalidOperation, ValueError): raise ValueError("price_per_unit must be a decimal")
    observed = raw.observed_on if isinstance(raw.observed_on, date) else date.fromisoformat(raw.observed_on)
    form, grade, region = raw.material_form.strip().upper(), raw.grade.strip().upper(), raw.region.strip()
    currency, unit, basis = raw.currency.strip().upper(), raw.unit.strip().upper(), raw.price_basis.strip().upper()
    if not all((form, grade, region, currency, unit, basis)): raise ValueError("material, grade, region, currency, unit and price_basis are required")
    if price <= 0: raise ValueError("price_per_unit must be positive")
    if currency not in _CURRENCIES: raise ValueError("unsupported currency")
    if unit == "TONNE": unit = "MT"
    if unit not in _UNITS: raise ValueError("unsupported unit")
    if basis not in _BASES: raise ValueError("unsupported price_basis")
    if observed > date.today(): raise ValueError("observed_on cannot be in the future")
    if raw.external_observation_id and raw.external_record_id and raw.external_observation_id != raw.external_record_id:
        raise ValueError("external observation identifiers disagree")
    return {"material_form": form, "grade": grade, "region": region, "price_per_unit": price,
            "currency": currency, "unit": unit, "price_basis": basis, "observed_on": observed,
            "dimension_note": raw.dimension_note,
            "external_observation_id": raw.external_record_id or raw.external_observation_id}


def _validate_document_provenance(db: Session, *, organization_id: UUID, price_source: PriceSource,
                                  source_document_id: UUID) -> MarketSourceDocument:
    """Validate the document/source relationship before any ingestion write occurs."""
    document = db.get(MarketSourceDocument, source_document_id)
    if document is None:
        raise ValueError("source document does not exist")
    market_source = db.get(MarketSource, document.source_id)
    if market_source is None or market_source.organization_id != organization_id:
        raise PermissionError("source document is not owned by organization")
    provider_config = db.scalar(select(MarketSourceProviderConfig).where(
        MarketSourceProviderConfig.source_id == market_source.id))
    if provider_config is None:
        raise PermissionError("source document has no provider configuration")
    if not (provider_config.enabled and provider_config.access_authorized and provider_config.reuse_authorized):
        raise PermissionError("source document provider is not activated and authorized")
    if price_source.source_type != "PROVIDER" or price_source.provider_key != provider_config.provider_id:
        raise PermissionError("price source does not match source document provider")
    # A fixture document is provenance-only test data and may never produce a
    # genuine observation through this path.
    if provider_config.provider_type == "FIXTURE_TEST" or market_source.provenance_classification == "FIXTURE_TEST":
        raise PermissionError("fixture source documents cannot publish genuine observations")
    return document

def ingest_observations(db: Session, *, organization_id: UUID, source_id: UUID, provider_key: str,
                        idempotency_key: str, observations: list[ProviderObservation], is_synthetic: bool = False,
                        source_document_id: UUID | None = None, commit: bool = True) -> MarketIngestionRun:
    existing = db.scalar(select(MarketIngestionRun).where(MarketIngestionRun.organization_id == organization_id,
        MarketIngestionRun.provider_key == provider_key, MarketIngestionRun.idempotency_key == idempotency_key))
    if existing: return existing
    source, org = db.get(PriceSource, source_id), db.get(Organization, organization_id)
    if source is None or source.organization_id != organization_id: raise PermissionError("source is not owned by organization")
    if org is None or (is_synthetic and not org.is_demo): raise PermissionError("synthetic ingestion is limited to demo organizations")
    if source.is_synthetic != is_synthetic: raise PermissionError("source provenance does not match ingestion provenance")
    if source_document_id is not None:
        _validate_document_provenance(db, organization_id=organization_id, price_source=source,
                                      source_document_id=source_document_id)
    run = MarketIngestionRun(organization_id=organization_id, source_id=source_id, provider_key=provider_key,
        idempotency_key=idempotency_key, status="RUNNING", started_at=datetime.now(timezone.utc))
    db.add(run); db.flush()
    inserted: list[PriceObservation] = []
    for raw in observations:
        try:
            item = _normalise(raw)
            duplicate = db.scalar(select(PriceObservation.id).where(PriceObservation.organization_id == organization_id,
                PriceObservation.source_id == source_id, PriceObservation.material_form == item["material_form"],
                PriceObservation.grade == item["grade"], PriceObservation.region == item["region"],
                PriceObservation.price_basis == item["price_basis"], PriceObservation.currency == item["currency"],
                PriceObservation.unit == item["unit"], PriceObservation.observed_on == item["observed_on"],
                PriceObservation.price_per_unit == item["price_per_unit"]))
            if duplicate: run.duplicate_count += 1; continue
            observation = PriceObservation(organization_id=organization_id, source_id=source_id,
                source_document_id=source_document_id, is_synthetic=is_synthetic, **item)
            db.add(observation); inserted.append(observation)
            run.inserted_count += 1
        except (ValueError, TypeError) as error:
            run.rejected_count += 1
            run.error_summary = str(error)[:2000]
    db.flush()
    # Alert events share this transaction: an observation and its notification
    # are committed together, and only genuinely inserted rows are evaluated.
    from app.services.market_alerts import evaluate_price_alerts
    for observation in inserted:
        evaluate_price_alerts(db, observation)
    run.completed_at = datetime.now(timezone.utc)
    run.status = "PARTIAL" if run.rejected_count and (run.inserted_count or run.duplicate_count) else ("FAILED" if run.rejected_count else "SUCCEEDED")
    if commit:
        db.commit()
    else:
        db.flush()
    return run
