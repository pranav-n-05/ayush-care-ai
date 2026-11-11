import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schemas import ERROR_RESPONSES, Page
from app.db.session import get_db
from app.modules.audit.service import add_audit
from app.modules.identity.access import OrgContext, require
from app.modules.identity.permissions import P
from app.modules.patients import service
from app.modules.patients.schemas import (
    ConsentEventOut,
    ConsentInput,
    ConsentOut,
    DuplicateCandidate,
    IdentifierIn,
    IdentifierOut,
    PatientCreate,
    PatientCreated,
    PatientListItem,
    PatientOut,
    PatientUpdate,
)

router = APIRouter(prefix="/api/v1/patients", tags=["patients"], responses=ERROR_RESPONSES)


@router.get("", response_model=Page[PatientListItem])
async def list_patients(
    q: str | None = Query(
        None, max_length=100, description="Name fragment, record number or phone"
    ),
    sort: str = Query("-created_at"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    ctx: OrgContext = Depends(require(P.PATIENT_READ)),
    db: AsyncSession = Depends(get_db),
) -> Page[PatientListItem]:
    rows, total = await service.search_patients(db, ctx.organization_id, q, sort, limit, offset)
    add_audit(
        db,
        action="patient.searched",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
        details={"results": len(rows), "has_query": bool(q)},
    )
    await db.commit()
    return Page(
        items=[PatientListItem.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=PatientCreated, status_code=201)
async def create_patient(
    body: PatientCreate,
    ctx: OrgContext = Depends(require(P.PATIENT_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> PatientCreated:
    patient, dups = await service.create_patient(db, ctx, body)
    return PatientCreated(
        patient=PatientOut.model_validate(patient),
        possible_duplicates=[
            DuplicateCandidate(id=p.id, record_number=p.record_number, match_reasons=r)
            for p, r in dups
        ],
    )


@router.get("/{patient_id}", response_model=PatientOut)
async def get_patient(
    patient_id: uuid.UUID,
    ctx: OrgContext = Depends(require(P.PATIENT_READ)),
    db: AsyncSession = Depends(get_db),
) -> PatientOut:
    patient = await service.get_patient(db, ctx.organization_id, patient_id)
    add_audit(
        db,
        action="patient.viewed",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
        entity_type="patient",
        entity_id=patient.id,
    )
    await db.commit()
    return PatientOut.model_validate(patient)


@router.put("/{patient_id}", response_model=PatientOut)
async def update_patient(
    patient_id: uuid.UUID,
    body: PatientUpdate,
    ctx: OrgContext = Depends(require(P.PATIENT_UPDATE)),
    db: AsyncSession = Depends(get_db),
) -> PatientOut:
    return PatientOut.model_validate(await service.update_patient(db, ctx, patient_id, body))


@router.get("/{patient_id}/possible-duplicates", response_model=list[DuplicateCandidate])
async def possible_duplicates(
    patient_id: uuid.UUID,
    ctx: OrgContext = Depends(require(P.PATIENT_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[DuplicateCandidate]:
    p = await service.get_patient(db, ctx.organization_id, patient_id)
    data = {
        "given_name": p.given_name,
        "family_name": p.family_name,
        "birth_date": p.birth_date,
        "phone": p.phone,
    }
    dups = await service.find_possible_duplicates(db, ctx.organization_id, data, exclude=p.id)
    return [
        DuplicateCandidate(id=d.id, record_number=d.record_number, match_reasons=r) for d, r in dups
    ]


@router.get("/{patient_id}/consents", response_model=list[ConsentOut])
async def consents(
    patient_id: uuid.UUID,
    ctx: OrgContext = Depends(require(P.PATIENT_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[ConsentOut]:
    await service.get_patient(db, ctx.organization_id, patient_id)
    return [
        ConsentOut.model_validate(c)
        for c in await service.list_consents(db, ctx.organization_id, patient_id)
    ]


@router.post("/{patient_id}/consents", response_model=ConsentOut, status_code=201)
async def record_consent(
    patient_id: uuid.UUID,
    body: ConsentInput,
    ctx: OrgContext = Depends(require(P.CONSENT_RECORD)),
    db: AsyncSession = Depends(get_db),
) -> ConsentOut:
    return ConsentOut.model_validate(await service.record_consent(db, ctx, patient_id, body))


@router.get("/{patient_id}/consent-history", response_model=list[ConsentEventOut])
async def consent_history(
    patient_id: uuid.UUID,
    ctx: OrgContext = Depends(require(P.PATIENT_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[ConsentEventOut]:
    await service.get_patient(db, ctx.organization_id, patient_id)
    return [
        ConsentEventOut(
            consent_type=t,
            status=e.status,
            method=e.method,
            recorded_by_user_id=e.recorded_by_user_id,
            created_at=e.created_at,
        )
        for e, t in await service.consent_history(db, ctx.organization_id, patient_id)
    ]


@router.post("/{patient_id}/identifiers", response_model=IdentifierOut, status_code=201)
async def add_identifier(
    patient_id: uuid.UUID,
    body: IdentifierIn,
    ctx: OrgContext = Depends(require(P.PATIENT_UPDATE)),
    db: AsyncSession = Depends(get_db),
) -> IdentifierOut:
    ident = await service.add_identifier(db, ctx, patient_id, body.system, body.value)
    return IdentifierOut(id=ident.id, system=ident.system, value=ident.value)
