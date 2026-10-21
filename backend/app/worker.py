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
