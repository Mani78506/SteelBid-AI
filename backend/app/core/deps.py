"""FastAPI dependencies: authenticated session, tenant context, permission guards."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import ApiError, forbidden
from app.core.permissions import role_can
from app.core.security import hash_token
from app.database import get_db
from app.models.identity import Membership, Organization, Session, User

settings = get_settings()


@dataclass
class TenantContext:
    db: OrmSession
    user: User
    organization: Organization
    membership: Membership
    session: Session
    request_id: str

    @property
    def org_id(self):
        return self.organization.id

    @property
    def user_id(self):
        return self.user.id

    @property
    def role(self) -> str:
        return self.membership.role


def _load_session(db: OrmSession, token: str | None) -> Session | None:
    if not token:
        return None
    sess = db.scalar(select(Session).where(Session.token_hash == hash_token(token)))
    if sess is None or sess.expires_at < datetime.now(timezone.utc):
        return None
    return sess


def get_current_session(request: Request, db: OrmSession = Depends(get_db)) -> Session:
    sess = _load_session(db, request.cookies.get(settings.session_cookie_name))
    if sess is None:
        raise ApiError(401, "UNAUTHENTICATED", "Authentication required")
    sess.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    return sess


def get_tenant(
    request: Request,
    db: OrmSession = Depends(get_db),
    sess: Session = Depends(get_current_session),
) -> TenantContext:
    """Resolve user + active organization and validate membership server-side on every request."""
    user = db.get(User, sess.user_id)
    if user is None or not user.is_active:
        raise ApiError(401, "UNAUTHENTICATED", "Account disabled")
    if sess.active_organization_id is None:
        raise ApiError(403, "NO_ORGANIZATION", "Select an organization first")
    org = db.get(Organization, sess.active_organization_id)
    if org is None or not org.is_active:
        raise ApiError(403, "ORGANIZATION_INACTIVE", "Organization is not active")
    membership = db.scalar(
        select(Membership).where(
            Membership.organization_id == org.id, Membership.user_id == user.id))
    if membership is None:
        # membership may have been revoked — clear and force re-selection
        sess.active_organization_id = None
        db.commit()
        raise ApiError(403, "NO_MEMBERSHIP", "You are not a member of this organization")
    return TenantContext(
        db=db, user=user, organization=org, membership=membership,
        session=sess, request_id=getattr(request.state, "request_id", ""))


def require(permission: str):
    def guard(ctx: TenantContext = Depends(get_tenant)) -> TenantContext:
        if not role_can(ctx.role, permission):
            raise forbidden(f"Role {ctx.role} lacks permission '{permission}'")
        return ctx
    return guard


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        settings.session_cookie_name, token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True, samesite="lax", secure=settings.secure_cookies, path="/")


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(settings.session_cookie_name, path="/")


def session_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=settings.session_ttl_hours)
