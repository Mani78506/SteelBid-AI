"""Read-only Tender Source Registry views.

Source creation, approval, activation and ingestion are intentionally internal
operations; this router exposes only tenant-safe policy and health summaries.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from uuid import UUID

from app.core.deps import TenantContext, require
from app.models.market import MarketSource, MarketSourceRefreshState, TenderSourceProfile
from app.schemas.market import TenderSourceRegistryOut

router = APIRouter(prefix="/tender-sources", tags=["tender-sources"])


def _visible_clause(ctx: TenantContext):
    return ((MarketSource.organization_id == ctx.org_id) |
            ((MarketSource.organization_id.is_(None)) &
             (MarketSource.visibility == "GLOBAL") &
             (MarketSource.redistribution_permitted.is_(True))))


def _out(profile: TenderSourceProfile, source: MarketSource,
         state: MarketSourceRefreshState | None) -> TenderSourceRegistryOut:
    if state and state.error_state:
        health = "FAILED"
    elif state and state.last_success_at:
        health = "HEALTHY"
    else:
        health = "NOT_YET_SYNCED"
    return TenderSourceRegistryOut(
        id=source.id, name=source.name, source_category=profile.source_category,
        permitted_ingestion_method=profile.permitted_ingestion_method,
        data_classification=profile.default_data_classification,
        enabled_for_tender_ingestion=profile.enabled_for_tender_ingestion,
        supports_discovery=profile.supports_discovery,
        supports_document_retrieval=profile.supports_document_retrieval,
        supports_revision_tracking=profile.supports_revision_tracking,
        reference_url=source.reference_url, attribution_text=source.attribution_text,
        license_status=source.license_status, usage_restrictions=source.usage_restrictions,
        publication_frequency=source.publication_frequency, visibility=source.visibility,
        redistribution_permitted=source.redistribution_permitted,
        last_success_at=state.last_success_at if state else None,
        last_checked_at=state.last_checked_at if state else None, health_status=health,
    )


@router.get("", response_model=list[TenderSourceRegistryOut])
def list_tender_sources(ctx: TenantContext = Depends(require("read"))):
    rows = ctx.db.execute(select(TenderSourceProfile, MarketSource, MarketSourceRefreshState).join(
        MarketSource, MarketSource.id == TenderSourceProfile.source_id
    ).outerjoin(MarketSourceRefreshState, MarketSourceRefreshState.source_id == MarketSource.id).where(
        _visible_clause(ctx)
    ).order_by(MarketSource.name)).all()
    return [_out(profile, source, state) for profile, source, state in rows]


@router.get("/{source_id}", response_model=TenderSourceRegistryOut)
def get_tender_source(source_id: UUID, ctx: TenantContext = Depends(require("read"))):
    rows = ctx.db.execute(select(TenderSourceProfile, MarketSource, MarketSourceRefreshState).join(
        MarketSource, MarketSource.id == TenderSourceProfile.source_id
    ).outerjoin(MarketSourceRefreshState, MarketSourceRefreshState.source_id == MarketSource.id).where(
        MarketSource.id == source_id, _visible_clause(ctx)
    )).first()
    from app.core.errors import not_found
    if rows is None:
        raise not_found("Tender source")
    return _out(*rows)
