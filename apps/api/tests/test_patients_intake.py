import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.session import session_scope
from app.modules.encounters.models import Encounter
from app.modules.intake.models import IntakeAnswer
from app.modules.triage.models import TriageEvent, TriageRuleVersion
from tests.factories import (
    BASIC_ANSWERS,
    PATIENT,
    answer,
    create_encounter,
    create_patient,
    make_org,
    start_intake,
)


async def test_patient_create_with_age_and_duplicate_flags(login_as):
    org = await make_org()
    c = await login_as(org.users["receptionist"])
    await create_patient(c)
    r = await c.post("/api/v1/patients", json={**PATIENT, "given_name": "Other"})  # same phone
    assert r.status_code == 201
    assert r.json()["possible_duplicates"][0]["match_reasons"] == ["same_phone"]
    body = {k: v for k, v in PATIENT.items() if k != "birth_date"} | {
        "phone": None,
        "age_years": 40,
        "age_recorded_on": "2026-01-01",
    }
    r = await c.post("/api/v1/patients", json=body)
    assert (
        r.status_code == 201 and r.json()["patient"]["birth_date_precision"] == "estimated_from_age"
    )
    r = await c.post(
        "/api/v1/patients", json={k: v for k, v in PATIENT.items() if k != "birth_date"}
    )
    assert r.status_code == 422  # neither DOB nor age


async def test_search_pagination_and_sort_allowlist(login_as):
    org = await make_org()
    c = await login_as(org.users["receptionist"])
    p = await create_patient(c)
    await create_patient(c, given_name="Zubin", phone="+919100000009")
    r = (await c.get("/api/v1/patients", params={"q": "kav"})).json()
    assert r["total"] == 1 and r["items"][0]["id"] == p["id"]
    assert (await c.get("/api/v1/patients", params={"q": p["record_number"]})).json()["total"] == 1
    assert (await c.get("/api/v1/patients", params={"sort": "phone"})).status_code == 422
    assert (await c.get("/api/v1/patients", params={"limit": 1})).json()["total"] == 2


async def test_optimistic_locking_on_update(login_as):
    org = await make_org()
    c = await login_as(org.users["receptionist"])
    p = await create_patient(c)
    body = {**PATIENT, "city": "Chennai", "lock_version": p["lock_version"]}
    r1 = await c.put(f"/api/v1/patients/{p['id']}", json=body)
    assert r1.status_code == 200 and r1.json()["lock_version"] == p["lock_version"] + 1
    r2 = await c.put(f"/api/v1/patients/{p['id']}", json=body)  # stale
    assert r2.status_code == 409 and r2.json()["error"]["code"] == "stale_version"


async def test_consent_history_preserved(login_as):
    org = await make_org()
    c = await login_as(org.users["receptionist"])
    p = await create_patient(c, consents=[])
    for status in ("granted", "withdrawn"):
        await c.post(
            f"/api/v1/patients/{p['id']}/consents",
            json={"consent_type": "contact_reminders", "status": status, "method": "verbal"},
        )
    cur = (await c.get(f"/api/v1/patients/{p['id']}/consents")).json()
    assert cur == [cur[0]] and cur[0]["status"] == "withdrawn"
    hist = (await c.get(f"/api/v1/patients/{p['id']}/consent-history")).json()
    assert [h["status"] for h in hist] == ["granted", "withdrawn"]


async def test_identifier_uniqueness(login_as):
    org = await make_org()
    c = await login_as(org.users["receptionist"])
    a, b = await create_patient(c), await create_patient(c, phone="+919100000005")
    assert (
        await c.post(
            f"/api/v1/patients/{a['id']}/identifiers",
            json={"system": "abha-demo", "value": "91-0000"},
        )
    ).status_code == 201
    assert (
        await c.post(
            f"/api/v1/patients/{b['id']}/identifiers",
            json={"system": "abha-demo", "value": "91-0000"},
        )
    ).status_code == 409


async def test_tenant_isolation_across_resources(login_as):
    a, b = await make_org(), await make_org()
    ca, cb = await login_as(a.users["practitioner"]), await login_as(b.users["practitioner"])
    p = await create_patient(ca)
    enc = await create_encounter(ca, p["id"])
    s = await start_intake(ca, enc["id"], a.questionnaire_version_id)
    for url in [
        f"/api/v1/patients/{p['id']}",
        f"/api/v1/encounters/{enc['id']}",
        f"/api/v1/intake-sessions/{s['id']}",
        f"/api/v1/patients/{p['id']}/timeline",
        f"/api/v1/encounters/{enc['id']}/documents",
        f"/api/v1/patients/{p['id']}/fhir/Patient",
    ]:
        assert (await cb.get(url)).status_code == 404, url
    assert (await cb.get("/api/v1/patients")).json()["total"] == 0
    assert (await cb.post(f"/api/v1/patients/{p['id']}/encounters", json={})).status_code == 404
    assert (await answer(cb, s["id"], BASIC_ANSWERS)).status_code == 404
    # B cannot start a session in A's encounter with B's questionnaire, nor A's with B's version
    r = await ca.post(
        f"/api/v1/encounters/{enc['id']}/intake-sessions",
        json={"questionnaire_version_id": str(b.questionnaire_version_id)},
    )
    assert r.status_code == 404


async def test_database_blocks_cross_tenant_relationship(login_as):
    a, b = await make_org(), await make_org()
    ca = await login_as(a.users["practitioner"])
    p = await create_patient(ca)
    from app.core.timeutil import utcnow
    from app.modules.identity.models import User

    with pytest.raises(IntegrityError):
        async with session_scope() as db:
            user = await db.scalar(select(User).where(User.email == a.users["practitioner"]))
            db.add(
                Encounter(
                    organization_id=b.id,
                    patient_id=p["id"],
                    started_at=utcnow(),
                    created_by_user_id=user.id,
                )
            )


async def test_intake_branching_validation_and_revisions(login_as):
    org = await make_org()
    c = await login_as(org.users["clinical_assistant"])
    p = await create_patient(c)
    enc = await create_encounter(c, p["id"])
    s = await start_intake(c, enc["id"], org.questionnaire_version_id)
    states = {q["code"]: q["state"] for q in s["questions"]}
    assert states["allergy_details"] == "not_asked" and states["chief_complaint"] == "unanswered"

    r = await answer(
        c,
        s["id"],
        [{"question_code": "allergy_details", "answer_status": "answered", "value": "x"}],
    )
    assert r.status_code == 422  # hidden question
    r = await answer(
        c, s["id"], [{"question_code": "severity", "answer_status": "answered", "value": 11}]
    )
    assert r.status_code == 422
    r = await answer(
        c,
        s["id"],
        [{"question_code": "nadi_observation", "answer_status": "answered", "value": "x"}],
    )
    assert r.status_code == 422  # practitioner-only field

    r = await answer(
        c,
        s["id"],
        [
            {"question_code": "has_allergies", "answer_status": "answered", "value": True},
            {
                "question_code": "allergy_details",
                "answer_status": "answered",
                "value": "Synthetic pollen: sneezing",
            },
        ],
    )
    assert r.status_code == 200
    q = {x["code"]: x for x in r.json()["questions"]}
    assert q["allergy_details"]["visible"] and q["allergy_details"]["state"] == "answered"

    # explicit negative vs unknown are distinct
    r = await answer(c, s["id"], [{"question_code": "has_allergies", "answer_status": "unknown"}])
    q = {x["code"]: x for x in r.json()["questions"]}
    assert q["has_allergies"]["state"] == "unknown" and q["allergy_details"]["state"] == "not_asked"
    hist = (await c.get(f"/api/v1/intake-sessions/{s['id']}/answers/has_allergies/history")).json()
    assert [(h["revision"], h["answer_status"]) for h in hist] == [(1, "answered"), (2, "unknown")]

    r = await c.post(f"/api/v1/intake-sessions/{s['id']}/submit")
    assert r.status_code == 422 and "chief_complaint" in r.json()["error"]["details"]["missing"]
    await answer(c, s["id"], BASIC_ANSWERS)
    r = await c.post(f"/api/v1/intake-sessions/{s['id']}/submit")
    assert r.status_code == 200 and r.json()["status"] == "submitted"
    # after submission non-reviewers can't edit
    r = await answer(
        c,
        s["id"],
        [
            {
                "question_code": "chief_complaint",
                "answer_status": "answered",
                "value": "changed",
                "change_reason": "typo",
            }
        ],
    )
    assert r.status_code == 403


async def test_reviewer_edit_after_submit_requires_reason(login_as):
    org = await make_org()
    c = await login_as(org.users["practitioner"])
    p = await create_patient(c)
    enc = await create_encounter(c, p["id"])
    s = await start_intake(c, enc["id"], org.questionnaire_version_id)
    await answer(c, s["id"], BASIC_ANSWERS)
    await c.post(f"/api/v1/intake-sessions/{s['id']}/submit")
    edit = {
        "question_code": "chief_complaint",
        "answer_status": "answered",
        "value": "Morning joint stiffness, both knees",
    }
    assert (await answer(c, s["id"], [edit])).status_code == 422
    assert (
        await answer(c, s["id"], [{**edit, "change_reason": "Clarified with patient"}])
    ).status_code == 200
    r = await c.post(f"/api/v1/intake-sessions/{s['id']}/review")
    assert r.json()["status"] == "reviewed"
    assert (
        await answer(c, s["id"], [{**edit, "value": "x", "change_reason": "y"}])
    ).status_code == 409


async def test_non_english_free_text_marked_for_translation(login_as):
    org = await make_org()
    c = await login_as(org.users["practitioner"])
    p = await create_patient(c, preferred_language="ta")
    enc = await create_encounter(c, p["id"])
    s = await start_intake(c, enc["id"], org.questionnaire_version_id, language="ta")
    q = {x["code"]: x for x in s["questions"]}
    assert (
        q["chief_complaint"]["text"].startswith("இன்று")
        and not q["chief_complaint"]["text_is_fallback"]
    )
    assert q["nadi_observation"]["text_is_fallback"]
    r = await answer(
        c,
        s["id"],
        [
            {"question_code": "chief_complaint", "answer_status": "answered", "value": "மூட்டு வலி"},
            {
                "question_code": "prior_treatment",
                "answer_status": "answered",
                "value": "எண்ணெய்",
                "translated_text_en": "Oil application",
            },
        ],
    )
    q = {x["code"]: x["current_answer"] for x in r.json()["questions"]}
    assert q["chief_complaint"]["translation_status"] == "translation_pending"
    assert q["chief_complaint"]["original_text"] == "மூட்டு வலி"
    assert q["prior_treatment"]["translation_status"] == "draft_requires_review"


async def test_demo_red_flag_rules(login_as):
    org = await make_org()
    c = await login_as(org.users["practitioner"])
    p = await create_patient(c)
    enc = await create_encounter(c, p["id"])
    s = await start_intake(c, enc["id"], org.questionnaire_version_id)
    cov = {x["severity"]: x["outcome"] for x in s["red_flag_rule_coverage"]}
    assert set(cov.values()) == {"not_evaluable"}  # missing data never means "no risk"
    await answer(
        c,
        s["id"],
        [
            {"question_code": "chest_pain", "answer_status": "answered", "value": True},
            {"question_code": "chest_pain_breathless", "answer_status": "answered", "value": True},
        ],
    )
    await answer(
        c,
        s["id"],
        [{"question_code": "chest_pain_breathless", "answer_status": "answered", "value": True}],
    )  # no-op, idempotent
    events = (await c.get("/api/v1/triage/events", params={"encounter_id": enc["id"]})).json()
    assert (
        len(events) == 1
        and events[0]["is_demo_rule"]
        and events[0]["severity"] == "demo_urgent_review"
    )
    eid = events[0]["id"]
    assert (
        await c.post(f"/api/v1/triage/events/{eid}/transition", json={"action": "acknowledge"})
    ).json()["status"] == "acknowledged"
    assert (
        await c.post(f"/api/v1/triage/events/{eid}/transition", json={"action": "acknowledge"})
    ).status_code == 409
    assert (
        await c.post(f"/api/v1/triage/events/{eid}/transition", json={"action": "resolve"})
    ).status_code == 422
    r = await c.post(
        f"/api/v1/triage/events/{eid}/transition",
        json={"action": "resolve", "resolution_code": "addressed_in_consultation"},
    )
    assert r.json()["status"] == "resolved"
    async with session_scope() as db:
        ev = await db.scalar(select(TriageEvent))
        ans = await db.get(IntakeAnswer, ev.intake_answer_id)
        assert ans.revision == ev.answer_revision


async def test_demo_rules_cannot_be_enabled_clinically():
    org = await make_org(roles=())
    with pytest.raises(IntegrityError):
        async with session_scope() as db:
            rv = await db.scalar(
                select(TriageRuleVersion).where(TriageRuleVersion.organization_id == org.id)
            )
            rv.clinical_use_enabled = True


async def test_published_questionnaire_needs_valid_definition(login_as):
    org = await make_org()
    c = await login_as(org.users["practitioner"])
    v = (await c.get("/api/v1/questionnaires")).json()[0]
    assert v["clinical_review_status"] == "demo_unreviewed"
    bad = {
        "code": "general_ayurveda_intake",
        "title": {"en": "x"},
        "clinical_disclaimer": "d",
        "sections": [
            {
                "code": "s",
                "title": {"en": "s"},
                "questions": [
                    {
                        "code": "a",
                        "type": "boolean",
                        "text": {"en": "a"},
                        "show_if": {"question": "b", "op": "is_true"},
                    },
                    {
                        "code": "b",
                        "type": "boolean",
                        "text": {"en": "b"},
                        "show_if": {"question": "a", "op": "is_true"},
                    },
                ],
            }
        ],
    }
    r = await c.post(
        f"/api/v1/questionnaires/{v['template_id']}/versions", json={"definition": bad}
    )
    assert r.status_code == 422 and any("cyclic" in e for e in r.json()["error"]["details"])
    good = {
        **bad,
        "sections": [
            {
                "code": "s",
                "title": {"en": "s"},
                "questions": [{"code": "a", "type": "boolean", "text": {"en": "a"}}],
            }
        ],
    }
    d = (
        await c.post(
            f"/api/v1/questionnaires/{v['template_id']}/versions", json={"definition": good}
        )
    ).json()
    assert d["version_number"] == 2 and d["status"] == "draft"
    enc = await create_encounter(c, (await create_patient(c))["id"])
    r = await c.post(
        f"/api/v1/encounters/{enc['id']}/intake-sessions",
        json={"questionnaire_version_id": d["id"]},
    )
    assert r.status_code == 409  # drafts cannot be used
    assert (await c.post(f"/api/v1/questionnaire-versions/{d['id']}/publish")).json()[
        "status"
    ] == "published"
    assert (await c.post(f"/api/v1/questionnaire-versions/{d['id']}/publish")).status_code == 409
