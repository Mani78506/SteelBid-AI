"""Internal validation for the reviewed Tender Source Registry.

This module has no creation or activation API.  It centralizes the checks used
when an internal, separately-authorized ingestion path associates discovered
tender provenance with a reviewed source.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.market import MarketSource, MarketSourceProviderConfig, TenderSourceProfile


CLASSIFICATIONS = {"AUTHENTIC", "DEMO", "FIXTURE_TEST"}
SOURCE_CATEGORIES = {"CPPP", "IREPS", "GEM", "STATE_EPROCUREMENT", "MANUAL_UPLOAD", "OTHER"}
INGESTION_METHODS = {"MANUAL_UPLOAD", "OFFICIAL_API", "LICENSED_FEED", "OFFICIAL_DOCUMENT", "FIXTURE_TEST"}


class TenderSourceRegistryError(ValueError):
    pass


@dataclass(frozen=True)
class RegistrySource:
    profile: TenderSourceProfile
    source: MarketSource
    provider_config: MarketSourceProviderConfig | None


def validate_profile_values(*, source_category: str, permitted_ingestion_method: str,
                            data_classification: str, enabled_for_tender_ingestion: bool,
                            authorization_evidence_reference: str | None) -> None:
    """Validate profile policy without enabling discovery or making any writes."""
    category = source_category.upper()
    method = permitted_ingestion_method.upper()
    classification = data_classification.upper()
    if category not in SOURCE_CATEGORIES:
        raise TenderSourceRegistryError("Unsupported tender source category")
    if method not in INGESTION_METHODS:
        raise TenderSourceRegistryError("Unsupported tender ingestion method")
    if classification not in CLASSIFICATIONS:
        raise TenderSourceRegistryError("Unsupported tender source classification")
    if classification == "AUTHENTIC" and not authorization_evidence_reference:
        raise TenderSourceRegistryError("AUTHENTIC sources require authorization evidence")
    if classification == "FIXTURE_TEST" and method != "FIXTURE_TEST":
        raise TenderSourceRegistryError("FIXTURE_TEST sources must use the FIXTURE_TEST ingestion method")
    # Disabled is the safe default.  Enabling is deliberately not exposed here;
    # future internal activation must additionally pass provider/legal checks.
    if enabled_for_tender_ingestion and classification == "FIXTURE_TEST":
        raise TenderSourceRegistryError("FIXTURE_TEST sources cannot be enabled for tender discovery")


def _visible(source: MarketSource, organization_id: UUID) -> bool:
    if source.organization_id == organization_id:
        return True
    # No entitlement table exists yet.  Deny OWNER_ONLY and ENTITLED sources
    # rather than assuming a global record is available to every tenant.
    return source.organization_id is None and source.visibility == "GLOBAL" and source.redistribution_permitted


def load_visible_registry_source(db: Session, *, organization_id: UUID, registry_source_id: UUID) -> RegistrySource:
    row = db.execute(select(TenderSourceProfile, MarketSource).join(
        MarketSource, MarketSource.id == TenderSourceProfile.source_id
    ).where(TenderSourceProfile.source_id == registry_source_id)).first()
    if row is None:
        raise TenderSourceRegistryError("Tender source registry profile was not found")
    profile, source = row
    if not _visible(source, organization_id):
        raise TenderSourceRegistryError("Tender source registry profile is not visible to this organization")
    config = db.scalar(select(MarketSourceProviderConfig).where(
        MarketSourceProviderConfig.source_id == source.id))
    return RegistrySource(profile=profile, source=source, provider_config=config)


def validate_provenance_registry_source(registry: RegistrySource, *, data_classification: str,
                                        authorization_status: str, official_source_url: str | None,
                                        source_type: str) -> None:
    """Enforce legal/authorization rules before internal provenance persistence."""
    profile, source, config = registry.profile, registry.source, registry.provider_config
    validate_profile_values(
        source_category=profile.source_category,
        permitted_ingestion_method=profile.permitted_ingestion_method,
        data_classification=profile.default_data_classification,
        enabled_for_tender_ingestion=profile.enabled_for_tender_ingestion,
        authorization_evidence_reference=profile.authorization_evidence_reference,
    )
    classification = data_classification.upper()
    if classification != profile.default_data_classification:
        raise TenderSourceRegistryError("Provenance classification must match the registered source classification")
    if source_type.upper() != profile.permitted_ingestion_method:
        raise TenderSourceRegistryError("Provenance ingestion method does not match the registered source policy")
    if classification in {"DEMO", "FIXTURE_TEST"}:
        # Classification matching above is deliberate: a demo/fixture profile
        # cannot be used to write AUTHENTIC provenance regardless of any
        # transport-level authorization status.
        return
    if source.license_status != "APPROVED":
        raise TenderSourceRegistryError("AUTHENTIC sources require approved legal status")
    if not official_source_url:
        raise TenderSourceRegistryError("AUTHENTIC sources require an official source URL")
    if profile.permitted_ingestion_method != "MANUAL_UPLOAD" and not source.reference_url:
        raise TenderSourceRegistryError("AUTHENTIC automated sources require a registered official source URL")
    if authorization_status.upper() != "AUTHORIZED":
        raise TenderSourceRegistryError("AUTHENTIC sources require AUTHORIZED status")
    if not profile.authorization_evidence_reference:
        raise TenderSourceRegistryError("AUTHENTIC sources require authorization evidence")
    if config is None or not (config.access_authorized and config.reuse_authorized):
        raise TenderSourceRegistryError("AUTHENTIC sources require authorized access and reuse")
    if config.provider_type == "FIXTURE_TEST":
        raise TenderSourceRegistryError("FIXTURE_TEST providers cannot be represented as AUTHENTIC")
