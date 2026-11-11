"""Authentication and authorization dependencies.

Every protected route depends on `require(...)`. Organization context comes ONLY from the
authenticated session's active membership; request bodies/headers can never select a tenant.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import NotAuthenticated, PermissionDenied
from app.core.security import hash_token, tokens_equal
from app.core.timeutil import utcnow
from app.db.session import get_db
from app.modules.audit.service import record_audit_independently
from app.modules.identity.models import OrganizationMembership, User, UserSession
from app.modules.identity.permissions import P

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_HEADER = "x-csrf-token"


@dataclass(frozen=True)
class Principal:
    user: User
    session: UserSession


@dataclass(frozen=True)
class OrgContext:
    user_id: uuid.UUID
    organization_id: uuid.UUID
    membership_id: uuid.UUID
    role_codes: frozenset[str]
    permissions: frozenset[str]

    def has(self, perm: P) -> bool:
        return perm.value in self.permissions


def _check_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin is not None and origin not in get_settings().trusted_origins:
        raise PermissionDenied("Untrusted request origin", code="untrusted_origin")


async def get_principal(request: Request, db: AsyncSession = Depends(get_db)) -> Principal:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise NotAuthenticated("Authentication required")
    now = utcnow()
    row = (
        await db.execute(
            select(UserSession, User)
            .join(User, User.id == UserSession.user_id)
            .where(UserSession.token_hash == hash_token(token))
        )
    ).first()
    if row is None:
        raise NotAuthenticated("Session is invalid")
    session, user = row
    idle_limit = timedelta(minutes=settings.session_idle_ttl_minutes)
    if session.revoked_at is not None:
        raise NotAuthenticated("Session has been revoked", code="session_revoked")
    if session.expires_at <= now or now - session.last_seen_at > idle_limit:
        raise NotAuthenticated("Session has expired", code="session_expired")
    if not user.is_active:
        raise NotAuthenticated("Account is inactive")

    if request.method in UNSAFE_METHODS:
        _check_origin(request)
        supplied = request.headers.get(CSRF_HEADER, "")
        if not supplied or not tokens_equal(hash_token(supplied), session.csrf_token_hash):
            raise PermissionDenied("Missing or invalid CSRF token", code="csrf_failed")

    if now - session.last_seen_at > timedelta(seconds=60):
        session.last_seen_at = now
        await db.commit()
    return Principal(user=user, session=session)


async def load_org_context(db: AsyncSession, principal: Principal) -> OrgContext:
    membership_id = principal.session.active_membership_id
    if membership_id is None:
        raise PermissionDenied("No active organization selected", code="no_active_organization")
    membership = await db.get(OrganizationMembership, membership_id)
    if (
        membership is None
        or membership.user_id != principal.user.id
        or not membership.is_active
        or not membership.organization.is_active
    ):
        raise PermissionDenied("Organization membership is not active", code="membership_inactive")
    perms = frozenset(p.code for role in membership.roles for p in role.permissions)
    return OrgContext(
        user_id=principal.user.id,
        organization_id=membership.organization_id,
        membership_id=membership.id,
        role_codes=frozenset(r.code for r in membership.roles),
        permissions=perms,
    )


def require(*needed: P) -> Callable[..., Awaitable[OrgContext]]:
    async def _dep(
        request: Request,
        principal: Principal = Depends(get_principal),
        db: AsyncSession = Depends(get_db),
    ) -> OrgContext:
        ctx = await load_org_context(db, principal)
        missing = [p.value for p in needed if p.value not in ctx.permissions]
        if missing:
            await record_audit_independently(
                action="authorization.denied",
                organization_id=ctx.organization_id,
                actor_user_id=ctx.user_id,
                outcome="denied",
                details={"missing": missing, "route": request.url.path[:200]},
            )
            raise PermissionDenied("You do not have permission for this action")
        return ctx

    return _dep


async def require_platform_admin(principal: Principal = Depends(get_principal)) -> Principal:
    if not principal.user.is_platform_admin:
        raise PermissionDenied("Platform administrator required")
    return principal
