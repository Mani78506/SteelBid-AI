"""Auditable persistence for non-publishable parser executions."""
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models.market import MarketSource, MarketSourceDocument, MarketSourceExtraction, MarketSourceRefreshState
from app.services.market_document_parser import ParseResult

def persist_fixture_extraction(db:Session, *, source_id, url:str, publisher:str, title:str, published_at, reporting_period:str|None, result:ParseResult, commit: bool = True):
    source=db.get(MarketSource, source_id)
    if source is None: raise ValueError("market source not found")
    document=db.scalar(select(MarketSourceDocument).where(MarketSourceDocument.source_id==source_id, MarketSourceDocument.sha256_checksum==result.checksum))
    now=datetime.now(timezone.utc)
    if document is None:
        document=MarketSourceDocument(source_id=source_id, original_document_url=url, publisher=publisher, document_title=title, published_at=published_at, reporting_period=reporting_period, retrieved_at=now, sha256_checksum=result.checksum, parser_version=result.parser_version, reuse_basis="FIXTURE_TEST_ONLY", extraction_status=result.status)
        db.add(document); db.flush()
    extraction=db.scalar(select(MarketSourceExtraction).where(MarketSourceExtraction.source_document_id==document.id, MarketSourceExtraction.parser_version==result.parser_version))
    if extraction is None:
        extraction=MarketSourceExtraction(source_document_id=document.id, parser_version=result.parser_version, status=result.status, extracted_at=now, error_summary="; ".join(result.errors)[:2000] or None, records_found=len(result.candidates)+len(result.errors), records_accepted=len(result.candidates))
        db.add(extraction)
    state=db.scalar(select(MarketSourceRefreshState).where(MarketSourceRefreshState.source_id==source_id))
    if state is None: state=MarketSourceRefreshState(source_id=source_id); db.add(state)
    state.last_checked_at=now
    if result.status=="VALID": state.last_success_at=now; state.latest_document_id=document.id; state.latest_checksum=result.checksum; state.error_state=None
    else: state.error_state=extraction.error_summary
    if commit: db.commit()
    else: db.flush()
    return document, extraction
