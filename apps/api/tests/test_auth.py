from datetime import timedelta

from sqlalchemy import select, update

from app.core.security import hash_token
from app.core.timeutil import utcnow
from app.db.session import session_scope
from app.modules.audit.models import AuditEvent
from app.modules.identity.models import User, UserSession
from tests.conftest import PASSWORD
from tests.factories import make_org, make_user


async def test_login_sets_secure_cookie_attributes(anon):
    org = await make_org()
    r = await anon.post(
        "/api/v1/auth/login", json={"email": org.users["practitioner"], "password": PASSWORD}
    )
    assert r.status_code == 200
    cookies = r.headers.get_list("set-cookie")
    session_cookie = next(c for c in cookies if c.startswith("ayush_session="))
    assert "HttpOnly" in session_cookie and "SameSite=lax" in session_cookie
    csrf_cookie = next(c for c in cookies if c.startswith("ayush_csrf="))
    assert "HttpOnly" not in csrf_cookie
    assert r.json()["active_organization_id"] == str(org.id)


async def test_session_token_stored_only_as_hash(anon):
    org = await make_org()
    r = await anon.post(
        "/api/v1/auth/login", json={"email": org.users["practitioner"], "password": PASSWORD}
    )
    token = r.cookies["ayush_session"]
    async with session_scope() as db:
        s = await db.scalar(select(UserSession))
        assert s.token_hash == hash_token(token) and token not in (s.token_hash, s.csrf_token_hash)


async def test_wrong_password_and_unknown_email_are_indistinguishable(anon):
    org = await make_org()
    a = await anon.post(
        "/api/v1/auth/login",
        json={"email": org.users["practitioner"], "password": "wrong-password-123"},
    )
    b = await anon.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong-password-123"}
    )
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


async def test_lockout_after_repeated_failures(anon):
    email = await make_user(None, None)
    for _ in range(5):
        await anon.post(
            "/api/v1/auth/login", json={"email": email, "password": "wrong-password-123"}
        )
    r = await anon.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 401  # correct password rejected while locked
    async with session_scope() as db:
        assert (await db.scalar(select(User).where(User.email == email))).locked_until is not None
        failures = (
            await db.scalars(
                select(AuditEvent).where(
                    AuditEvent.action == "auth.login", AuditEvent.outcome == "failure"
                )
            )
        ).all()
        assert len(failures) == 6


async def test_me_and_logout_revokes_session(login_as):
    org = await make_org()
    c = await login_as(org.users["practitioner"])
    me = (await c.get("/api/v1/users/me")).json()
    assert me["active_organization_id"] == str(org.id)
    assert "summary.approve" in me["permissions"]
    token = c.cookies["ayush_session"]
    assert (await c.post("/api/v1/auth/logout")).status_code == 204
    c.cookies.set("ayush_session", token)
    r = await c.get("/api/v1/users/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "session_revoked"


async def test_unauthenticated_is_401(anon):
    r = await anon.get("/api/v1/patients")
    assert r.status_code == 401 and r.json()["error"]["code"] == "not_authenticated"


async def test_expired_and_idle_sessions_rejected(login_as):
    org = await make_org()
    c = await login_as(org.users["practitioner"])
    async with session_scope() as db:
        await db.execute(update(UserSession).values(last_seen_at=utcnow() - timedelta(hours=1)))
    r = await c.get("/api/v1/users/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "session_expired"
    c2 = await login_as(org.users["receptionist"])
    async with session_scope() as db:
        await db.execute(update(UserSession).values(expires_at=utcnow() - timedelta(seconds=1)))
    assert (await c2.get("/api/v1/users/me")).status_code == 401


async def test_csrf_required_for_unsafe_methods(login_as):
    org = await make_org()
    c = await login_as(org.users["receptionist"])
    csrf = c.headers.pop("X-CSRF-Token")
    r = await c.post("/api/v1/patients", json={})
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"
    r = await c.post("/api/v1/patients", json={}, headers={"X-CSRF-Token": "forged"})
    assert r.json()["error"]["code"] == "csrf_failed"
    r = await c.post(
        "/api/v1/patients",
        json={},
        headers={"X-CSRF-Token": csrf, "Origin": "https://evil.example"},
    )
    assert r.json()["error"]["code"] == "untrusted_origin"
    r = await c.post("/api/v1/patients", json={}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 422  # passes CSRF, fails validation


async def test_revoke_other_sessions(login_as):
    org = await make_org()
    email = org.users["practitioner"]
    c1 = await login_as(email)
    c2 = await login_as(email)
    r = await c1.post("/api/v1/auth/sessions/revoke-others")
    assert r.json() == {"revoked": 1}
    assert (await c2.get("/api/v1/users/me")).status_code == 401
    assert (await c1.get("/api/v1/users/me")).status_code == 200


async def test_deactivated_user_cannot_use_session(login_as):
    org = await make_org()
    c = await login_as(org.users["practitioner"])
    async with session_scope() as db:
        await db.execute(
            update(User).where(User.email == org.users["practitioner"]).values(is_active=False)
        )
    assert (await c.get("/api/v1/users/me")).status_code == 401
