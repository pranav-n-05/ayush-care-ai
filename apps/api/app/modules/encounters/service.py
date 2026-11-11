import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, NotFound
from app.core.timeutil import utcnow
from app.modules.audit.service import add_audit
from app.modules.encounters.models import Encounter
from app.modules.identity.access import OrgContext
from app.modules.identity.models import Clinic
from app.modules.patients.service import get_patient

_ALLOWED = {"open": {"in_review", "closed"}, "in_review": {"open", "closed"}, "closed": set()}


async def create_encounter(
    db: AsyncSession,
    ctx: OrgContext,
    patient_id: uuid.UUID,
    visit_reason: str | None,
    clinic_id: uuid.UUID | None,
) -> Encounter:
    patient = await get_patient(db, ctx.organization_id, patient_id)
    if not patient.is_active:
        raise Conflict("Patient record is inactive")
    if clinic_id is not None:
        clinic = await db.scalar(
            select(Clinic).where(
                Clinic.id == clinic_id, Clinic.organization_id == ctx.organization_id
            )
        )
        if clinic is None:
            raise NotFound("Clinic not found")
    enc = Encounter(
        organization_id=ctx.organization_id,
        patient_id=patient.id,
        clinic_id=clinic_id,
        visit_reason=visit_reason,
        started_at=utcnow(),
        created_by_user_id=ctx.user_id,
        practitioner_membership_id=ctx.membership_id if "practitioner" in ctx.role_codes else None,
    )
    db.add(enc)
    await db.flush()
    add_audit(
        db,
        action="encounter.created",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
        entity_type="encounter",
        entity_id=enc.id,
    )
    await db.commit()
    return enc


async def get_encounter(db: AsyncSession, org_id: uuid.UUID, encounter_id: uuid.UUID) -> Encounter:
    enc = await db.scalar(
        select(Encounter).where(Encounter.id == encounter_id, Encounter.organization_id == org_id)
    )
    if enc is None:
        raise NotFound("Encounter not found")
    return enc


async def list_for_patient(
    db: AsyncSession, org_id: uuid.UUID, patient_id: uuid.UUID
) -> list[Encounter]:
    return list(
        (
            await db.scalars(
                select(Encounter)
                .where(Encounter.organization_id == org_id, Encounter.patient_id == patient_id)
                .order_by(Encounter.started_at.desc())
            )
        ).all()
    )


async def set_status(
    db: AsyncSession, ctx: OrgContext, encounter_id: uuid.UUID, status: str
) -> Encounter:
    enc = await get_encounter(db, ctx.organization_id, encounter_id)
    if status == enc.status:
        return enc
    if status not in _ALLOWED[enc.status]:
        raise Conflict(f"Cannot move encounter from {enc.status} to {status}")
    enc.status = status
    enc.closed_at = utcnow() if status == "closed" else None
    add_audit(
        db,
        action="encounter.status_changed",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
        entity_type="encounter",
        entity_id=enc.id,
        details={"status": status},
    )
    await db.commit()
    return enc
