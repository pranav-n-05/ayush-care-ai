"""Synthetic test data builders that go through services, not raw SQL."""

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import session_scope
from app.modules.identity.models import Organization, OrganizationMembership, Role, User
from app.modules.intake.models import QuestionnaireVersion
from app.modules.intake.seed import seed_demo_questionnaire
from app.modules.triage.seed import seed_demo_rules
from tests.conftest import PASSWORD, unique_email


@dataclass
class Org:
    id: uuid.UUID
    questionnaire_version_id: uuid.UUID
    users: dict[str, str] = field(default_factory=dict)  # role -> email


async def make_org(
    slug: str | None = None,
    roles: tuple[str, ...] = (
        "hospital_admin",
        "practitioner",
        "clinical_assistant",
        "receptionist",
    ),
) -> Org:
    async with session_scope() as db:
        org = Organization(
            name=f"Synthetic Org {slug or ''}".strip(), slug=slug or f"org-{uuid.uuid4().hex[:8]}"
        )
        db.add(org)
        await db.flush()
        vid = await seed_demo_questionnaire(db, org.id)
        await seed_demo_rules(db, org.id)
        result = Org(id=org.id, questionnaire_version_id=vid)
    for role in roles:
        result.users[role] = await make_user(result.id, role)
    return result


async def make_user(
    org_id: uuid.UUID | None,
    role: str | None,
    *,
    email: str | None = None,
    platform_admin: bool = False,
) -> str:
    email = email or unique_email(role or "user")
    async with session_scope() as db:
        user = User(
            email=email,
            full_name="Synthetic Person",
            password_hash=hash_password(PASSWORD),
            is_platform_admin=platform_admin,
        )
        db.add(user)
        await db.flush()
        if org_id and role:
            role_row = await db.scalar(select(Role).where(Role.code == role))
            m = OrganizationMembership(organization_id=org_id, user_id=user.id)
            m.roles = [role_row]
            db.add(m)
    return email


async def published_version(org_id: uuid.UUID) -> QuestionnaireVersion:
    async with session_scope() as db:
        v = await db.scalar(
            select(QuestionnaireVersion).where(QuestionnaireVersion.organization_id == org_id)
        )
        assert v is not None
        return v


PATIENT = {
    "given_name": "Kavya",
    "family_name": "Synthetic",
    "birth_date": "1990-01-15",
    "sex_for_clinical_use": "female",
    "phone": "+919100000000",
    "preferred_language": "en",
}

ALL_CONSENTS = [
    {"consent_type": t, "status": "granted", "method": "written"}
    for t in ("data_processing", "ai_assisted_documentation", "contact_reminders")
]


async def create_patient(client, **overrides):  # type: ignore[no-untyped-def]
    body = {**PATIENT, "consents": ALL_CONSENTS, **overrides}
    r = await client.post("/api/v1/patients", json=body)
    assert r.status_code == 201, r.text
    return r.json()["patient"]


async def create_encounter(client, patient_id):  # type: ignore[no-untyped-def]
    r = await client.post(
        f"/api/v1/patients/{patient_id}/encounters", json={"visit_reason": "Synthetic visit"}
    )
    assert r.status_code == 201, r.text
    return r.json()


async def start_intake(client, encounter_id, version_id, language="en"):  # type: ignore[no-untyped-def]
    r = await client.post(
        f"/api/v1/encounters/{encounter_id}/intake-sessions",
        json={"questionnaire_version_id": str(version_id), "language": language},
    )
    assert r.status_code == 201, r.text
    return r.json()


BASIC_ANSWERS = [
    {
        "question_code": "chief_complaint",
        "answer_status": "answered",
        "value": "Joint stiffness in the mornings",
    },
    {
        "question_code": "complaint_duration",
        "answer_status": "answered",
        "value": {"amount": 3, "unit": "months"},
    },
    {"question_code": "chest_pain", "answer_status": "answered", "value": False},
    {"question_code": "current_medications", "answer_status": "answered", "value": "None"},
    {"question_code": "has_allergies", "answer_status": "answered", "value": False},
]


async def answer(client, session_id, answers):  # type: ignore[no-untyped-def]
    return await client.post(
        f"/api/v1/intake-sessions/{session_id}/answers", json={"answers": answers}
    )
