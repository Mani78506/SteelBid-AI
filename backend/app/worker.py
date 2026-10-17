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
