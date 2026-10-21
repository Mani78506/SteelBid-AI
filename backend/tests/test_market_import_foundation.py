"""Persistence-only tests for reviewed market imports; no observations are published."""
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.models.market import MarketImportBatch, MarketImportStagedRow, MarketSource, PriceObservation


def test_reviewed_import_tables_and_constraints(db, seeded):
    inspector = inspect(db.bind)
    assert {"market_sources", "market_import_batches", "market_import_staged_rows"} <= set(inspector.get_table_names())
    assert any(c["name"] == "uq_market_import_batch_org_key" for c in inspector.get_unique_constraints("market_import_batches"))
    assert any(c["name"] == "uq_market_import_row" for c in inspector.get_unique_constraints("market_import_staged_rows"))


def test_staged_rows_are_scoped_and_do_not_publish_observations(db, seeded):
    # Use existing tenant/user ids without touching live price observations.
    org = db.execute(__import__("sqlalchemy").select(__import__("app.models.identity", fromlist=["Organization"]).Organization)).scalars().first()
    user = db.execute(__import__("sqlalchemy").select(__import__("app.models.identity", fromlist=["User"]).User)).scalars().first()
    before = db.query(PriceObservation).count()
    source = MarketSource(organization_id=org.id, name="Permission pending reference", provenance_classification="OFFICIAL_REFERENCE", attribution_text="Attribution retained", license_status="PENDING", visibility="OWNER_ONLY", redistribution_permitted=False)
    db.add(source); db.flush()
    batch = MarketImportBatch(organization_id=org.id, source_id=source.id, uploaded_by=user.id, import_key="fixture-import-1", status="DRAFT")
    db.add(batch); db.flush()
    db.add(MarketImportStagedRow(batch_id=batch.id, row_number=2, original_data={"price":"56000"}, normalized_data={}, validation_errors=["missing price_basis"], status="INVALID", dedupe_key="fixture-row"))
    db.commit()
    assert db.query(PriceObservation).count() == before

    db.add(MarketImportStagedRow(batch_id=batch.id, row_number=2, original_data={}, normalized_data={}, validation_errors=[], status="DRAFT"))
    try:
        db.commit()
        assert False, "duplicate row number must be rejected"
    except IntegrityError:
        db.rollback()
