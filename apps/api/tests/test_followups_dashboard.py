import asyncio
from datetime import timedelta

from alembic import command
from sqlalchemy import select

from app.core.timeutil import utcnow
from app.db.session import session_scope
from app.modules.audit.models import AuditEvent
from app.modules.followups.models import Notification
from app.modules.followups.service import dispatch_due_reminders
from tests.conftest import TEST_URL, _recreate_db, alembic_config
from tests.factories import create_encounter, create_patient, make_org


async def test_reminders_idempotent_and_consent_aware(login_as):
    org = await make_org()
    c = await login_as(org.users["receptionist"])
    consenting = await create_patient(c)
    refusing = await create_patient(c, phone="+919100000077", consents=[])
    due = (utcnow() - timedelta(minutes=1)).isoformat()
    for p in (consenting, refusing):
        r = await c.post(
            "/api/v1/follow-ups", json={"patient_id": p["id"], "due_at": due, "channel": "sms"}
        )
        assert r.status_code == 201
    first = await dispatch_due_reminders()
    second = await dispatch_due_reminders()
    assert first["sent"] == 1 and first["skipped_no_consent"] == 1
    assert second["already_handled"] == 2 and second.get("sent", 0) == 0
    async with session_scope() as db:
        notes = (await db.scalars(select(Notification))).all()
        assert len(notes) == 2 and {n.template_code for n in notes} == {"follow_up_reminder_v1"}
    r = await c.post(
        "/api/v1/follow-ups",
        json={"patient_id": consenting["id"], "due_at": "2026-12-01T10:00:00", "channel": "sms"},
    )
    assert r.status_code == 422  # naive datetime rejected


async def test_followup_encounter_must_match_patient(login_as):
    org = await make_org()
    c = await login_as(org.users["receptionist"])
    a, b = await create_patient(c), await create_patient(c, phone="+919100000088")
    enc = await create_encounter(c, a["id"])
    r = await c.post(
        "/api/v1/follow-ups",
        json={
            "patient_id": b["id"],
            "encounter_id": enc["id"],
            "due_at": utcnow().isoformat(),
            "channel": "sms",
        },
    )
    assert r.status_code == 422


async def test_dashboard_and_analytics(login_as):
    org = await make_org()
    c = await login_as(org.users["practitioner"])
    p = await create_patient(c)
    await create_encounter(c, p["id"])
    m = {x["key"]: x for x in (await c.get("/api/v1/dashboard/overview")).json()["metrics"]}
    assert m["open_encounters"]["value"] == 1 and m["open_encounters"]["definition"]
    admin = await login_as(org.users["hospital_admin"])
    today = utcnow().date().isoformat()
    a = (await admin.get("/api/v1/analytics/summary", params={"start": today, "end": today})).json()
    assert {x["key"]: x["value"] for x in a["metrics"]}["patient_registrations"] == 1
    assert a["rates"]["intake_completion"] is None  # no denominator -> no fabricated rate
    assert (
        await admin.get("/api/v1/analytics/summary", params={"start": today, "end": "2020-01-01"})
    ).status_code == 422
    audit = (await admin.get("/api/v1/audit-events", params={"action": "patient.created"})).json()
    assert audit["total"] == 1


async def test_audit_events_carry_no_clinical_payload(login_as):
    org = await make_org()
    c = await login_as(org.users["practitioner"])
    await create_patient(c, given_name="UniqueSyntheticName")
    async with session_scope() as db:
        events = (await db.scalars(select(AuditEvent))).all()
    blob = " ".join(str(e.details) for e in events)
    assert "UniqueSyntheticName" not in blob and "+9191" not in blob
    assert all(e.correlation_id for e in events if e.actor_user_id)


async def test_fhir_patient_export(login_as):
    org = await make_org()
    c = await login_as(org.users["practitioner"])
    p = await create_patient(c)
    r = (await c.get(f"/api/v1/patients/{p['id']}/fhir/Patient")).json()
    assert (
        r["resourceType"] == "Patient"
        and r["gender"] == "female"
        and r["birthDate"] == "1990-01-15"
    )
    assert r["identifier"][0]["value"] == p["record_number"]
    rec = await login_as(org.users["receptionist"])
    assert (await rec.get(f"/api/v1/patients/{p['id']}/fhir/Patient")).status_code == 403


async def test_migrations_downgrade_and_upgrade_roundtrip():
    name = "ayushcare_migration_test"
    await _recreate_db(name)
    url = TEST_URL.rsplit("/", 1)[0] + f"/{name}"
    cfg = alembic_config(url)
    await asyncio.to_thread(command.upgrade, cfg, "head")
    await asyncio.to_thread(command.downgrade, cfg, "base")
    await asyncio.to_thread(command.upgrade, cfg, "head")
    await asyncio.to_thread(command.check, cfg)  # models and migrations agree
