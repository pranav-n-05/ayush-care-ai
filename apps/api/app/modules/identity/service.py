import re
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import Conflict, NotAuthenticated, NotFound, PermissionDenied, ValidationFailed
from app.core.security import hash_password, hash_token, needs_rehash, new_token, verify_password
from app.core.timeutil import utcnow
from app.modules.audit.service import add_audit, record_audit_independently
from app.modules.identity.models import (
    Invitation,
    Organization,
    OrganizationMembership,
    Role,
    User,
    UserSession,
)
from app.modules.identity.permissions import ASSIGNABLE_BY_ADMIN, R

GENERIC_LOGIN_ERROR = "Invalid email or password"
INVITATION_TTL = timedelta(days=3)
SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,60}[a-z0-9])$")


def normalize_email(email: str) -> str:
    return email.strip().lower()


@dataclass
class IssuedSession:
    session: UserSession
    token: str
    csrf_token: str


async def _issue_session(db: AsyncSession, user: User) -> IssuedSession:
    settings = get_settings()
    now = utcnow()
    memberships = (
        await db.scalars(
            select(OrganizationMembership).where(
                OrganizationMembership.user_id == user.id, OrganizationMembership.is_active
            )
        )
    ).all()
    active = [m for m in memberships if m.organization.is_active]
    token, csrf = new_token(), new_token()
    session = UserSession(
        user_id=user.id,
        token_hash=hash_token(token),
        csrf_token_hash=hash_token(csrf),
        active_membership_id=active[0].id if len(active) == 1 else None,
        last_seen_at=now,
        expires_at=now + timedelta(minutes=settings.session_absolute_ttl_minutes),
    )
    db.add(session)
    return IssuedSession(session=session, token=token, csrf_token=csrf)


async def login(db: AsyncSession, email: str, password: str) -> IssuedSession:
    settings = get_settings()
    now = utcnow()
    user = await db.scalar(select(User).where(User.email == normalize_email(email)))
    locked = user is not None and user.locked_until is not None and user.locked_until > now
    ok = verify_password(user.password_hash if user else None, password)  # always runs (timing)
    if user is None or not user.is_active or locked or not ok:
        if user is not None and not locked:
            user.failed_login_count += 1
            if user.failed_login_count >= settings.login_max_failures:
                user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
                user.failed_login_count = 0
            await db.commit()
        await record_audit_independently(
            action="auth.login",
            organization_id=None,
            actor_user_id=user.id if user else None,
            outcome="failure",
            details={"reason": "locked" if locked else "invalid_credentials"},
        )
        raise NotAuthenticated(GENERIC_LOGIN_ERROR, code="invalid_credentials")

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    if user.password_hash and needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    issued = await _issue_session(db, user)
    add_audit(db, action="auth.login", organization_id=None, actor_user_id=user.id)
    await db.commit()
    return issued


async def logout(db: AsyncSession, session: UserSession) -> None:
    session.revoked_at = utcnow()
    session.revoked_reason = "logout"
    add_audit(db, action="auth.logout", organization_id=None, actor_user_id=session.user_id)
    await db.commit()


async def revoke_other_sessions(db: AsyncSession, session: UserSession) -> int:
    result = await db.execute(
        update(UserSession)
        .where(
            UserSession.user_id == session.user_id,
            UserSession.id != session.id,
            UserSession.revoked_at.is_(None),
        )
        .values(revoked_at=utcnow(), revoked_reason="revoked_by_user")
    )
    count = int(result.rowcount)  # type: ignore[attr-defined]
    add_audit(
        db,
        action="auth.sessions_revoked",
        organization_id=None,
        actor_user_id=session.user_id,
        details={"count": count},
    )
    await db.commit()
    return count


async def switch_organization(
    db: AsyncSession, session: UserSession, organization_id: uuid.UUID
) -> OrganizationMembership:
    membership = await db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == session.user_id,
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.is_active,
        )
    )
    if membership is None or not membership.organization.is_active:
        # Same response whether the org does not exist or the user is not a member.
        raise NotFound("Organization not found")
    session.active_membership_id = membership.id
    add_audit(
        db,
        action="auth.switch_organization",
        organization_id=organization_id,
        actor_user_id=session.user_id,
    )
    await db.commit()
    return membership


async def list_memberships(db: AsyncSession, user_id: uuid.UUID) -> list[OrganizationMembership]:
    return list(
        (
            await db.scalars(
                select(OrganizationMembership).where(
                    OrganizationMembership.user_id == user_id, OrganizationMembership.is_active
                )
            )
        ).all()
    )


async def get_role(db: AsyncSession, code: str) -> Role:
    role = await db.scalar(select(Role).where(Role.code == code))
    if role is None:
        raise ValidationFailed(f"Unknown role: {code}")
    return role


# ---------- organizations (platform administration) ----------


async def create_organization(
    db: AsyncSession, *, actor: User, name: str, slug: str, admin_email: str, admin_full_name: str
) -> tuple[Organization, str]:
    if not SLUG_RE.match(slug):
        raise ValidationFailed("Slug must be 3-62 lowercase letters, digits or hyphens")
    if await db.scalar(select(Organization).where(Organization.slug == slug)):
        raise Conflict("An organization with this slug already exists")
    org = Organization(name=name, slug=slug)
    db.add(org)
    await db.flush()
    from app.modules.intake.seed import seed_demo_questionnaire
    from app.modules.triage.seed import seed_demo_rules

    await seed_demo_questionnaire(db, org.id)
    await seed_demo_rules(db, org.id)
    token = await _create_invitation(
        db,
        org_id=org.id,
        inviter=actor,
        email=admin_email,
        full_name=admin_full_name,
        role_code=R.HOSPITAL_ADMIN,
    )
    add_audit(
        db,
        action="platform.organization_created",
        organization_id=org.id,
        actor_user_id=actor.id,
        entity_type="organization",
        entity_id=org.id,
    )
    await db.commit()
    return org, token


# ---------- invitations ----------


async def _create_invitation(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    inviter: User,
    email: str,
    full_name: str,
    role_code: str,
) -> str:
    token = new_token()
    db.add(
        Invitation(
            organization_id=org_id,
            email=normalize_email(email),
            full_name=full_name,
            role_code=role_code,
            token_hash=hash_token(token),
            invited_by_user_id=inviter.id,
            expires_at=utcnow() + INVITATION_TTL,
        )
    )
    return token


async def invite_member(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    inviter: User,
    email: str,
    full_name: str,
    role_code: str,
) -> str:
    if role_code not in {r.value for r in ASSIGNABLE_BY_ADMIN}:
        raise ValidationFailed("This role cannot be assigned by invitation")
    existing = await db.scalar(
        select(OrganizationMembership)
        .join(User, User.id == OrganizationMembership.user_id)
        .where(
            OrganizationMembership.organization_id == org_id,
            User.email == normalize_email(email),
        )
    )
    if existing is not None:
        raise Conflict("This person is already a member")
    token = await _create_invitation(
        db, org_id=org_id, inviter=inviter, email=email, full_name=full_name, role_code=role_code
    )
    add_audit(
        db,
        action="org.member_invited",
        organization_id=org_id,
        actor_user_id=inviter.id,
        details={"role": role_code},
    )
    await db.commit()
    return token


async def accept_invitation(db: AsyncSession, token: str, password: str) -> User:
    now = utcnow()
    inv = await db.scalar(
        select(Invitation).where(Invitation.token_hash == hash_token(token)).with_for_update()
    )
    if inv is None or inv.accepted_at or inv.revoked_at or inv.expires_at <= now:
        raise NotFound("Invitation is invalid or has expired")
    user = await db.scalar(select(User).where(User.email == inv.email))
    if user is None:
        try:
            pw_hash = hash_password(password)
        except ValueError as exc:
            raise ValidationFailed(str(exc)) from exc
        user = User(email=inv.email, full_name=inv.full_name, password_hash=pw_hash)
        db.add(user)
        await db.flush()
    elif not verify_password(user.password_hash, password):
        inv.failed_attempts += 1
        if inv.failed_attempts >= 5:
            inv.revoked_at = now
        await db.commit()
        raise NotAuthenticated("Existing account password is required to accept")
    role = await get_role(db, inv.role_code)
    membership = OrganizationMembership(organization_id=inv.organization_id, user_id=user.id)
    membership.roles = [role]
    db.add(membership)
    inv.accepted_at = now
    add_audit(
        db,
        action="org.invitation_accepted",
        organization_id=inv.organization_id,
        actor_user_id=user.id,
        details={"role": inv.role_code},
    )
    await db.commit()
    return user


# ---------- member administration ----------


async def list_members(db: AsyncSession, org_id: uuid.UUID) -> list[OrganizationMembership]:
    return list(
        (
            await db.scalars(
                select(OrganizationMembership)
                .where(OrganizationMembership.organization_id == org_id)
                .order_by(OrganizationMembership.created_at)
            )
        ).all()
    )


async def _get_member(
    db: AsyncSession, org_id: uuid.UUID, membership_id: uuid.UUID
) -> OrganizationMembership:
    m = await db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.id == membership_id,
            OrganizationMembership.organization_id == org_id,
        )
    )
    if m is None:
        raise NotFound("Member not found")
    return m


async def set_member_roles(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    actor_membership_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    membership_id: uuid.UUID,
    role_codes: list[str],
) -> OrganizationMembership:
    if membership_id == actor_membership_id:
        raise PermissionDenied("You cannot change your own roles", code="self_role_change")
    allowed = {r.value for r in ASSIGNABLE_BY_ADMIN}
    if not role_codes or any(c not in allowed for c in role_codes):
        raise ValidationFailed("Roles must be a non-empty subset of assignable staff roles")
    m = await _get_member(db, org_id, membership_id)
    m.roles = [await get_role(db, c) for c in sorted(set(role_codes))]
    add_audit(
        db,
        action="org.member_roles_changed",
        organization_id=org_id,
        actor_user_id=actor_user_id,
        entity_type="membership",
        entity_id=m.id,
        details={"roles": sorted(set(role_codes))},
    )
    await db.commit()
    return m


async def set_member_active(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    actor_membership_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    membership_id: uuid.UUID,
    active: bool,
) -> OrganizationMembership:
    if membership_id == actor_membership_id:
        raise PermissionDenied("You cannot deactivate yourself", code="self_deactivation")
    m = await _get_member(db, org_id, membership_id)
    m.is_active = active
    if not active:
        await db.execute(
            update(UserSession)
            .where(UserSession.active_membership_id == m.id, UserSession.revoked_at.is_(None))
            .values(revoked_at=utcnow(), revoked_reason="membership_deactivated")
        )
    add_audit(
        db,
        action="org.member_activation_changed",
        organization_id=org_id,
        actor_user_id=actor_user_id,
        entity_type="membership",
        entity_id=m.id,
        details={"active": active},
    )
    await db.commit()
    return m
