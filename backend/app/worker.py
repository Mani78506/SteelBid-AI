"""Celery app — Redis-backed in deployment, eager fallback locally.

Long-running AI extraction tasks run through the same service functions used by the
synchronous endpoints, so behavior is identical in both modes.
"""
from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery("steelbid", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_always_eager=settings.celery_always_eager,
    task_eager_propagates=False,
    timezone="UTC",
    beat_schedule={"market-source-dispatch": {"task": "steelbid.dispatch_due_market_sources", "schedule": 60.0}},
)


@celery_app.task(name="steelbid.ingest_market_observations", bind=True, autoretry_for=(ConnectionError,),
                 retry_backoff=True, retry_jitter=True, retry_kwargs={"max_retries": 3})
def ingest_market_observations_task(self, organization_id: str, source_id: str, provider_key: str,
                                    idempotency_key: str, observations: list[dict], is_synthetic: bool = False) -> dict:
    """Safe task entrypoint; schedulers must call this only for an authorized configured provider."""
    from uuid import UUID
    from app.database import SessionLocal
    from app.services.market_ingestion import ingest_observations
    from app.services.market_providers import ProviderObservation
    db = SessionLocal()
    try:
        rows = [ProviderObservation(**row) for row in observations]
        run = ingest_observations(db, organization_id=UUID(organization_id), source_id=UUID(source_id),
                                  provider_key=provider_key, idempotency_key=idempotency_key,
                                  observations=rows, is_synthetic=is_synthetic)
        return {"run_id": str(run.id), "status": run.status, "inserted": run.inserted_count,
                "duplicates": run.duplicate_count, "rejected": run.rejected_count}
    finally:
        db.close()


@celery_app.task(name="steelbid.refresh_market_source", bind=True, autoretry_for=(ConnectionError,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def refresh_market_source_task(self, source_id: str, claim_token: str) -> dict:
    """Fixture-only scheduled check. It persists provenance, never price observations."""
    import logging
    from uuid import UUID
    from app.database import SessionLocal
    from app.services.market_provider_registry import ProviderConfig, ProviderType, require_active
    from app.models.market import MarketSource, MarketSourceProviderConfig
    from app.services.market_document_parser import parse_fixture_csv
    from app.services.market_document_persistence import persist_fixture_extraction
    from app.services.market_source_claims import release_source_claim
    from app.models.market import MarketSourceClaim
    from sqlalchemy import select
    log = logging.getLogger(__name__); db = SessionLocal()
    try:
        cfg=db.scalar(__import__('sqlalchemy').select(MarketSourceProviderConfig).where(MarketSourceProviderConfig.source_id==UUID(source_id)))
        source=db.get(MarketSource, UUID(source_id))
        if not cfg or not source: raise ValueError("source configuration not found")
        config = ProviderConfig(cfg.provider_id, source.name, ProviderType(cfg.provider_type), cfg.endpoint_url or "", cfg.enabled, cfg.credential_reference, False, cfg.access_authorized, cfg.reuse_authorized, cfg.refresh_interval_seconds//60, cfg.parser_version)
        require_active(config, credential_available=False, publish_genuine=False)
        if config.provider_type is not ProviderType.FIXTURE_TEST or cfg.fixture_reference != "default":
            raise PermissionError("only controlled fixture retrieval is enabled")
        result = parse_fixture_csv(b"material_form,grade,region,price_per_unit,currency,unit,price_basis,observed_on\nHRC,E250,Fixture,50000,INR,MT,EX_WORKS,2026-01-01\n", parser_version=config.adapter_version)
        db.rollback()  # end read-only autobegin before the fenced write transaction
        # Fence the final write: claim, provenance, refresh state and completion
        # are one short transaction after parsing completes.
        with db.begin():
            claim=db.scalar(select(MarketSourceClaim).where(MarketSourceClaim.source_id==UUID(source_id)).with_for_update())
            from datetime import datetime, timezone
            if not claim or claim.claim_token != claim_token or claim.expires_at <= datetime.now(timezone.utc):
                return {"status": "skipped", "reason": "stale_or_expired_claim"}
            doc, extraction = persist_fixture_extraction(db, source_id=UUID(source_id), url=config.endpoint, publisher=config.name, title="Fixture market source", published_at=None, reporting_period=None, result=result, commit=False)
            db.delete(claim)
        log.info("market_source_refresh source_id=%s status=%s checksum=%s", source_id, result.status, result.checksum)
        return {"document_id":str(doc.id), "extraction_id":str(extraction.id), "status":result.status, "checksum":result.checksum}
    except Exception:
        release_source_claim(db, UUID(source_id), claim_token)
        raise
    finally:
        db.close()

@celery_app.task(name="steelbid.dispatch_due_market_sources")
def dispatch_due_market_sources() -> dict:
    from datetime import datetime, timezone
    from sqlalchemy import select
    from app.database import SessionLocal
    from app.models.market import MarketSourceProviderConfig, MarketSourceRefreshState, MarketSource
    from app.services.market_provider_registry import ProviderConfig, ProviderType, activation_error
    from app.services.market_source_claims import acquire_source_claim, release_source_claim
    db=SessionLocal(); dispatched=skipped=claimed=failed=0
    try:
        now=datetime.now(timezone.utc)
        for cfg in db.scalars(select(MarketSourceProviderConfig).where(MarketSourceProviderConfig.enabled.is_(True))).all():
            source=db.get(MarketSource,cfg.source_id)
            config=ProviderConfig(cfg.provider_id, source.name if source else cfg.provider_id, ProviderType(cfg.provider_type), cfg.endpoint_url or "", cfg.enabled, cfg.credential_reference, False, cfg.access_authorized, cfg.reuse_authorized, cfg.refresh_interval_seconds//60, cfg.parser_version)
            if not source or activation_error(config, credential_available=False, publish_genuine=False): skipped+=1; continue
            state=db.scalar(select(MarketSourceRefreshState).where(MarketSourceRefreshState.source_id==cfg.source_id))
            if state and state.last_checked_at and (now-state.last_checked_at).total_seconds()<cfg.refresh_interval_seconds: skipped+=1; continue
            token=acquire_source_claim(db,cfg.source_id,"celery-dispatcher")
            if not token: skipped+=1; continue
            claimed+=1
            try: refresh_market_source_task.delay(str(cfg.source_id),token); dispatched+=1
            except Exception: release_source_claim(db,cfg.source_id,token); failed+=1
        return {"dispatched":dispatched,"claimed":claimed,"skipped":skipped,"failed":failed}
    finally: db.close()


@celery_app.task(name="steelbid.extract_tender_document")
def extract_tender_document_task(tender_id: str, document_id: str) -> dict:
    """Worker entry point: delegates to the same extraction service as the API."""
    from uuid import UUID
    from app.database import SessionLocal
    from app.models.projects import TenderDocument
    from app.ai.extraction import extract_text_pages, parse_boq_lines
    db = SessionLocal()
    try:
        doc = db.get(TenderDocument, UUID(document_id))
        if doc is None:
            return {"status": "failed", "error": "document not found"}
        pages = extract_text_pages(doc.storage_key)
        candidates = sum(len(parse_boq_lines(text)) for _, text in pages)
        return {"status": "succeeded", "candidates": candidates}
    finally:
        db.close()
