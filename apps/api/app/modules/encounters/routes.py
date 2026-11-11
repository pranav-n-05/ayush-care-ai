import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schemas import ERROR_RESPONSES
from app.db.session import get_db
from app.modules.audit.service import add_audit
from app.modules.encounters import service
from app.modules.encounters.schemas import EncounterCreate, EncounterOut, EncounterStatusUpdate
from app.modules.identity.access import OrgContext, require
from app.modules.identity.permissions import P
from app.modules.patients.service import get_patient

router = APIRouter(prefix="/api/v1", tags=["encounters"], responses=ERROR_RESPONSES)


@router.post("/patients/{patient_id}/encounters", response_model=EncounterOut, status_code=201)
async def create(
    patient_id: uuid.UUID,
    body: EncounterCreate,
    ctx: OrgContext = Depends(require(P.ENCOUNTER_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> EncounterOut:
    return EncounterOut.model_validate(
        await service.create_encounter(db, ctx, patient_id, body.visit_reason, body.clinic_id)
    )


@router.get("/patients/{patient_id}/encounters", response_model=list[EncounterOut])
async def list_for_patient(
    patient_id: uuid.UUID,
    ctx: OrgContext = Depends(require(P.ENCOUNTER_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[EncounterOut]:
    await get_patient(db, ctx.organization_id, patient_id)
    return [
        EncounterOut.model_validate(e)
        for e in await service.list_for_patient(db, ctx.organization_id, patient_id)
    ]


@router.get("/encounters/{encounter_id}", response_model=EncounterOut)
async def get(
    encounter_id: uuid.UUID,
    ctx: OrgContext = Depends(require(P.ENCOUNTER_READ)),
    db: AsyncSession = Depends(get_db),
) -> EncounterOut:
    enc = await service.get_encounter(db, ctx.organization_id, encounter_id)
    add_audit(
        db,
        action="encounter.viewed",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
        entity_type="encounter",
        entity_id=enc.id,
    )
    await db.commit()
    return EncounterOut.model_validate(enc)


@router.put("/encounters/{encounter_id}/status", response_model=EncounterOut)
async def set_status(
    encounter_id: uuid.UUID,
    body: EncounterStatusUpdate,
    ctx: OrgContext = Depends(require(P.ENCOUNTER_UPDATE)),
    db: AsyncSession = Depends(get_db),
) -> EncounterOut:
    return EncounterOut.model_validate(await service.set_status(db, ctx, encounter_id, body.status))
