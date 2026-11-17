"""Database-free contract for automatic tender document extraction dispatch."""
import sys
from types import SimpleNamespace
from uuid import uuid4

from app.api import tenders


def test_upload_dispatches_shared_extraction_task(monkeypatch):
    calls: list[tuple[str, str]] = []

    class Task:
        @staticmethod
        def delay(tender_id: str, document_id: str):
            calls.append((tender_id, document_id))

    monkeypatch.setitem(sys.modules, "app.worker", SimpleNamespace(extract_tender_document_task=Task()))
    tender_id, document_id = uuid4(), uuid4()

    tenders._queue_document_extraction(tender_id=tender_id, document_id=document_id)

    assert calls == [(str(tender_id), str(document_id))]
