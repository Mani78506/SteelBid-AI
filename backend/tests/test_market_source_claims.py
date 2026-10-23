from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Thread
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from app.models.identity import Organization
from app.models.market import MarketSource, MarketSourceClaim
from app.models.market import MarketSourceDocument, MarketSourceExtraction
from app.services.market_document_parser import parse_fixture_csv
from app.services.market_document_persistence import persist_fixture_extraction
from app.services.market_source_claims import acquire_source_claim, renew_source_claim, release_source_claim, validate_source_claim
from app.database import SessionLocal

def test_claim_is_fenced_and_reclaimable(db):
    org=db.scalar(select(Organization).where(Organization.name.ilike("%Apex%")))
    source=MarketSource(organization_id=org.id,name="claim-fixture",provenance_classification="FIXTURE_TEST",attribution_text="test",license_status="APPROVED",visibility="OWNER_ONLY",redistribution_permitted=False); db.add(source); db.commit()
    first=acquire_source_claim(db,source.id,"one",60); assert first
    assert acquire_source_claim(db,source.id,"two",60) is None
    claim=db.scalar(select(MarketSourceClaim).where(MarketSourceClaim.source_id==source.id)); claim.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1); db.commit()
    second=acquire_source_claim(db,source.id,"two",60); assert second and second!=first
    assert not renew_source_claim(db,source.id,first)
    assert not release_source_claim(db,source.id,first)
    assert validate_source_claim(db,source.id,second)
    assert release_source_claim(db,source.id,second)

def test_independent_postgres_sessions_allow_one_claim(db):
    org=db.scalar(select(Organization).where(Organization.name.ilike("%Apex%")))
    source=MarketSource(organization_id=org.id,name="concurrent-claim-fixture",provenance_classification="FIXTURE_TEST",attribution_text="test",license_status="APPROVED",visibility="OWNER_ONLY",redistribution_permitted=False); db.add(source); db.commit()
    def attempt(owner):
        session=SessionLocal()
        try:
            session.execute(text("SET LOCAL lock_timeout = '2000ms'"))
            return acquire_source_claim(session,source.id,owner,60)
        except OperationalError:
            session.rollback(); return None
        finally: session.close()
    with ThreadPoolExecutor(max_workers=2) as pool: tokens=list(pool.map(attempt,["one","two"]))
    assert sum(token is not None for token in tokens)==1


def test_claim_row_lock_serializes_reclamation(db):
    """A second PostgreSQL transaction cannot reclaim while the claim row is locked."""
    org=db.scalar(select(Organization).where(Organization.name.ilike("%Apex%")))
    source=MarketSource(organization_id=org.id,name="row-lock-claim-fixture",provenance_classification="FIXTURE_TEST",attribution_text="test",license_status="APPROVED",visibility="OWNER_ONLY",redistribution_permitted=False); db.add(source); db.commit()
    token=acquire_source_claim(db,source.id,"first",60); assert token

    locked=Event(); release=Event(); contender_done=Event(); outcome={}

    def hold_lock():
        session=SessionLocal()
        try:
            with session.begin():
                claim=session.scalar(select(MarketSourceClaim).where(MarketSourceClaim.source_id==source.id).with_for_update())
                assert claim and claim.claim_token == token
                locked.set()
                assert release.wait(5)
        finally:
            session.close()

    def reclaim():
        session=SessionLocal()
        try:
            # This is session-scoped deliberately: acquire_source_claim commits its
            # short transaction, so SET LOCAL would be cleared before the upsert.
            session.execute(text("SET lock_timeout = '1500ms'"))
            outcome["token"]=acquire_source_claim(session,source.id,"second",60)
        except OperationalError:
            session.rollback(); outcome["token"]=None
        finally:
            try: session.execute(text("SET lock_timeout = DEFAULT")); session.commit()
            except Exception: session.rollback()
            session.close(); contender_done.set()

    holder=Thread(target=hold_lock); holder.start(); assert locked.wait(5)
    contender=Thread(target=reclaim); contender.start()
    # The contender either waits for the held row lock or times out; it cannot win.
    assert not contender_done.wait(0.25)
    release.set(); holder.join(5); contender.join(5)
    assert not holder.is_alive() and not contender.is_alive()
    assert outcome["token"] is None

def test_expired_or_reclaimed_token_cannot_persist(db):
    org=db.scalar(select(Organization).where(Organization.name.ilike("%Apex%")))
    source=MarketSource(organization_id=org.id,name="stale-fence-fixture",provenance_classification="FIXTURE_TEST",attribution_text="test",license_status="APPROVED",visibility="OWNER_ONLY",redistribution_permitted=False); db.add(source); db.commit()
    old=acquire_source_claim(db,source.id,"a",60)
    claim=db.scalar(select(MarketSourceClaim).where(MarketSourceClaim.source_id==source.id)); claim.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1); db.commit()
    new=acquire_source_claim(db,source.id,"b",60); assert new and new != old
    db.expire_all()
    claim=db.scalar(select(MarketSourceClaim).where(MarketSourceClaim.source_id==source.id))
    assert claim.claim_token != old
    assert db.scalar(select(MarketSourceDocument).where(MarketSourceDocument.source_id==source.id)) is None

def test_persistence_flush_rolls_back_with_transaction(db):
    org=db.scalar(select(Organization).where(Organization.name.ilike("%Apex%")))
    source=MarketSource(organization_id=org.id,name="rollback-fence-fixture",provenance_classification="FIXTURE_TEST",attribution_text="test",license_status="APPROVED",visibility="OWNER_ONLY",redistribution_permitted=False); db.add(source); db.commit()
    result=parse_fixture_csv(b"material_form,grade,region,price_per_unit,currency,unit,price_basis,observed_on\nHRC,E250,West,50000,INR,MT,EX_WORKS,2026-01-01\n")
    db.rollback()
    try:
        with db.begin():
            persist_fixture_extraction(db,source_id=source.id,url="fixture://rollback",publisher="test",title="rollback",published_at=None,reporting_period=None,result=result,commit=False)
            raise RuntimeError("forced rollback")
    except RuntimeError: pass
    assert db.scalar(select(MarketSourceDocument).where(MarketSourceDocument.source_id==source.id)) is None
