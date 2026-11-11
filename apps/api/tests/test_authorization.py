import pytest
from sqlalchemy import select

from app.db.session import session_scope
from app.modules.audit.models import AuditEvent
from app.modules.identity.models import Invitation, Role
from app.modules.identity.permissions import MATRIX
from tests.conftest import PASSWORD, unique_email
from tests.factories import create_patient, make_org, make_user


async def test_database_roles_match_code_matrix():
    async with session_scope() as db:
        roles = {
            r.code: {p.code for p in r.permissions} for r in (await db.scalars(select(Role))).all()
        }
    assert roles == {r.value: {p.value for p in perms} for r, perms in MATRIX.items()}


async def test_hospital_admin_has_no_clinical_access(login_as):
    org = await make_org()
    admin = await login_as(org.users["hospital_admin"])
    r = await admin.get("/api/v1/patients")
    assert r.status_code == 403
    async with session_scope() as db:
        denied = await db.scalar(
            select(AuditEvent).where(AuditEvent.action == "authorization.denied")
        )
        assert denied is not None and denied.details["missing"] == ["patient.read"]


async def test_platform_admin_gets_no_clinical_access(login_as):
    org = await make_org()
    email = await make_user(None, None, platform_admin=True)
    pa = await login_as(email)
    assert (await pa.get("/api/v1/patients")).status_code == 403
    r = await pa.post("/api/v1/auth/active-organization", json={"organization_id": str(org.id)})
    assert r.status_code == 404  # not a member; cannot select the tenant


async def test_receptionist_cannot_read_intake_or_summaries(login_as):
    org = await make_org()
    rec = await login_as(org.users["receptionist"])
    p = await create_patient(rec)
    enc = (await rec.post(f"/api/v1/patients/{p['id']}/encounters", json={})).json()
    assert (await rec.get(f"/api/v1/encounters/{enc['id']}/intake-sessions")).status_code == 403
    assert (await rec.get(f"/api/v1/encounters/{enc['id']}/summary")).status_code == 403
    assert (await rec.get(f"/api/v1/encounters/{enc['id']}/documents")).status_code == 403


async def test_patient_role_only_sees_linked_record(login_as):
    org = await make_org()
    email = await make_user(org.id, "patient")
    pat = await login_as(email)
    assert (await pat.get("/api/v1/patients")).status_code == 403
    assert (await pat.get("/api/v1/me/patient-record")).status_code == 404  # not linked yet


async def test_platform_org_creation_and_invitation_flow(login_as, anon):
    pa = await login_as(await make_user(None, None, platform_admin=True))
    r = await pa.post(
        "/api/v1/platform/organizations",
        json={
            "name": "Synthetic Hospital",
            "slug": "synthetic-hospital",
            "admin_email": "first-admin@example.com",
            "admin_full_name": "First Admin",
        },
    )
    assert r.status_code == 201
    token = r.json()["admin_invitation_token"]
    async with session_scope() as db:
        inv = await db.scalar(select(Invitation))
        assert inv.token_hash != token
    r = await anon.post(
        "/api/v1/auth/invitations/accept", json={"token": token, "password": PASSWORD}
    )
    assert r.status_code == 201
    again = await anon.post(
        "/api/v1/auth/invitations/accept", json={"token": token, "password": PASSWORD}
    )
    assert again.status_code == 404  # single use
    admin = await login_as("first-admin@example.com")
    members = (await admin.get("/api/v1/organization/members")).json()
    assert [m["roles"] for m in members] == [["hospital_admin"]]

    r = await admin.post(
        "/api/v1/organization/invitations",
        json={"email": unique_email("doc"), "full_name": "Doc", "role_code": "practitioner"},
    )
    assert r.status_code == 201
    r = await admin.post(
        "/api/v1/organization/invitations",
        json={"email": unique_email("x"), "full_name": "X", "role_code": "patient"},
    )
    assert r.status_code == 422


async def test_non_platform_admin_cannot_create_org(login_as):
    org = await make_org()
    c = await login_as(org.users["hospital_admin"])
    r = await c.post(
        "/api/v1/platform/organizations",
        json={
            "name": "X org",
            "slug": "x-org",
            "admin_email": "a@example.com",
            "admin_full_name": "A",
        },
    )
    assert r.status_code == 403


async def test_admin_cannot_change_own_roles_or_deactivate_self(login_as):
    org = await make_org()
    admin = await login_as(org.users["hospital_admin"])
    members = (await admin.get("/api/v1/organization/members")).json()
    me = next(m for m in members if m["email"] == org.users["hospital_admin"])
    r = await admin.put(
        f"/api/v1/organization/members/{me['membership_id']}/roles",
        json={"role_codes": ["practitioner"]},
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "self_role_change"
    r = await admin.put(
        f"/api/v1/organization/members/{me['membership_id']}/active", json={"is_active": False}
    )
    assert r.status_code == 403


async def test_role_change_takes_effect_and_deactivation_revokes(login_as):
    org = await make_org()
    admin = await login_as(org.users["hospital_admin"])
    rec = await login_as(org.users["receptionist"])
    members = (await admin.get("/api/v1/organization/members")).json()
    target = next(m for m in members if m["email"] == org.users["receptionist"])
    assert (
        await rec.get(f"/api/v1/encounters/{target['membership_id']}/intake-sessions")
    ).status_code == 403
    r = await admin.put(
        f"/api/v1/organization/members/{target['membership_id']}/roles",
        json={"role_codes": ["clinical_assistant"]},
    )
    assert r.json()["roles"] == ["clinical_assistant"]
    assert "intake.read" in (await rec.get("/api/v1/users/me")).json()["permissions"]
    await admin.put(
        f"/api/v1/organization/members/{target['membership_id']}/active", json={"is_active": False}
    )
    assert (await rec.get("/api/v1/users/me")).status_code == 401


@pytest.mark.parametrize("role", ["platform_admin", "nonexistent"])
async def test_cannot_assign_non_staff_roles(login_as, role):
    org = await make_org()
    admin = await login_as(org.users["hospital_admin"])
    members = (await admin.get("/api/v1/organization/members")).json()
    target = next(m for m in members if m["email"] == org.users["receptionist"])
    r = await admin.put(
        f"/api/v1/organization/members/{target['membership_id']}/roles", json={"role_codes": [role]}
    )
    assert r.status_code == 422


async def test_multi_org_user_switches_context(login_as):
    a, b = await make_org(), await make_org()
    email = a.users["practitioner"]
    async with session_scope() as db:
        from app.modules.identity.models import OrganizationMembership, User

        user = await db.scalar(select(User).where(User.email == email))
        role = await db.scalar(select(Role).where(Role.code == "receptionist"))
        m = OrganizationMembership(organization_id=b.id, user_id=user.id)
        m.roles = [role]
        db.add(m)
    c = await login_as(email)
    me = (await c.get("/api/v1/users/me")).json()
    assert me["active_organization_id"] is None and len(me["memberships"]) == 2
    assert (await c.get("/api/v1/patients")).json()["error"]["code"] == "no_active_organization"
    r = await c.post("/api/v1/auth/active-organization", json={"organization_id": str(b.id)})
    assert r.json()["active_organization_id"] == str(b.id)
    assert "summary.approve" not in r.json()["permissions"]  # receptionist in org B
