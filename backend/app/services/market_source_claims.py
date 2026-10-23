"""PostgreSQL lease claims; all token mutations are fenced by source and token."""
from datetime import datetime, timedelta, timezone
import secrets
from sqlalchemy import text

def acquire_source_claim(db, source_id, owner:str, lease_seconds:int=300):
    token=secrets.token_urlsafe(32); now=datetime.now(timezone.utc); expiry=now+timedelta(seconds=lease_seconds)
    row=db.execute(text("""INSERT INTO market_source_claims (id,source_id,claim_token,claim_owner,claimed_at,expires_at,created_at,updated_at)
    VALUES (gen_random_uuid(),:source,:token,:owner,:now,:expiry,:now,:now)
    ON CONFLICT (source_id) DO UPDATE SET claim_token=:token,claim_owner=:owner,claimed_at=:now,expires_at=:expiry,updated_at=:now
    WHERE market_source_claims.expires_at <= :now RETURNING claim_token"""),dict(source=source_id,token=token,owner=owner,now=now,expiry=expiry)).scalar()
    db.commit(); return token if row==token else None

def validate_source_claim(db, source_id, token):
    return db.execute(text("SELECT 1 FROM market_source_claims WHERE source_id=:s AND claim_token=:t AND expires_at>:n"),dict(s=source_id,t=token,n=datetime.now(timezone.utc))).scalar() is not None

def renew_source_claim(db, source_id, token, lease_seconds=300):
    now=datetime.now(timezone.utc); result=db.execute(text("UPDATE market_source_claims SET expires_at=:e,updated_at=:n WHERE source_id=:s AND claim_token=:t AND expires_at>:n"),dict(s=source_id,t=token,n=now,e=now+timedelta(seconds=lease_seconds))); db.commit(); return result.rowcount==1

def release_source_claim(db, source_id, token):
    result=db.execute(text("DELETE FROM market_source_claims WHERE source_id=:s AND claim_token=:t"),dict(s=source_id,t=token)); db.commit(); return result.rowcount==1
complete_source_claim=release_source_claim
