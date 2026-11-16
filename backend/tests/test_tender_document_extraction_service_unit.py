"""Database-free contract tests for the shared persisted extraction service."""
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.services import tender_document_extraction as service


class FakeSession:
    def __init__(self): self.added=[]; self.commits=0
    def add(self, row): self.added.append(row)
    def flush(self): pass
    def commit(self): self.commits += 1
    def execute(self, _statement): pass
    def scalar(self, _statement): return None


def _document():
    return SimpleNamespace(id=uuid4(), storage_key="safe-key", file_name="source.pdf", status="UPLOADED",
        processing_status="PENDING", content_checksum=None, parser_version=None, processed_at=None)


def test_shared_service_persists_pending_boq_and_page_evidence(monkeypatch, tmp_path):
    document = _document(); tender_id=uuid4(); org_id=uuid4(); db=FakeSession()
    source=tmp_path / "source.pdf"; source.write_bytes(b"%PDF-test")
    monkeypatch.setattr(service, "_load", lambda *_args, **_kwargs: (SimpleNamespace(), document))
    monkeypatch.setattr(service, "_source_path", lambda _doc: str(source))
    monkeypatch.setattr(service, "_latest_job", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "extract_text_pages", lambda _path: [(3, "ISMB 200 E250 12 MT")])
    monkeypatch.setattr(service, "extract_boq_candidates", lambda _text: ([{"raw_description":"ISMB 200 E250 12 MT", "form":"BEAM", "grade":"E250", "specification":{}, "quantity":"12", "unit":"MT", "confidence":"0.65"}], "rule-based", []))
    # No tenant material was mapped: it must remain pending rather than auto-approved.
    result=service.extract_and_persist(db, organization_id=org_id, tender_id=tender_id, document_id=document.id)
    assert result["candidates"] == 1 and result["idempotent"] is False
    boq=[row for row in db.added if row.__class__.__name__ == "BOQItem"][0]
    evidence=[row for row in db.added if row.__class__.__name__ == "ExtractionEvidence"][0]
    assert boq.review_status == "PENDING" and boq.page_ref == "p.3"
    assert evidence.review_status == "PENDING" and evidence.normalized_value["parser_version"] == service.PARSER_VERSION
    assert document.processing_status == "COMPLETED"


def test_completed_document_is_idempotent_without_new_rows(monkeypatch, tmp_path):
    document=_document(); document.processing_status="COMPLETED"; document.parser_version=service.PARSER_VERSION
    source=tmp_path / "source.pdf"; source.write_bytes(b"%PDF-test")
    import hashlib
    document.content_checksum=hashlib.sha256(source.read_bytes()).hexdigest()
    db=FakeSession(); job=SimpleNamespace(id=uuid4())
    monkeypatch.setattr(service, "_load", lambda *_args, **_kwargs: (SimpleNamespace(), document))
    monkeypatch.setattr(service, "_source_path", lambda _doc: str(source))
    monkeypatch.setattr(service, "_latest_job", lambda *_args, **_kwargs: job)
    result=service.extract_and_persist(db, organization_id=uuid4(), tender_id=uuid4(), document_id=document.id)
    assert result["idempotent"] is True and result["candidates"] == 0 and not db.added
