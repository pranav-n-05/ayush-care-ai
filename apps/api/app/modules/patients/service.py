import secrets
import uuid
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.modules.audit.service import add_audit
from app.modules.identity.access import OrgContext
from app.modules.patients.models import ConsentEvent, ConsentRecord, Patient, PatientIdentifier
from app.modules.patients.schemas import ConsentInput, PatientCreate, PatientUpdate

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I ambiguity
SORTABLE = {"created_at": Patient.created_at, "family_name": Patient.family_name}


def _record_number() -> str:
    return "AYU-" + "".join(secrets.choice(_ALPHABET) for _ in range(8))


async def get_patient(db: AsyncSession, org_id: uuid.UUID, patient_id: uuid.UUID) -> Patient:
    p = await db.scalar(
        select(Patient).where(Patient.id == patient_id, Patient.organization_id == org_id)
    )
    if p is None:
        raise NotFound("Patient not found")
    return p


async def find_possible_duplicates(
    db: AsyncSession, org_id: uuid.UUID, data: dict[str, Any], exclude: uuid.UUID | None = None
) -> list[tuple[Patient, list[str]]]:
    """Heuristic flags for human review. Name alone or phone alone never triggers a merge;
    nothing here merges anything."""
    clauses = []
    if data.get("phone"):
        clauses.append(Patient.phone == data["phone"])
    name_match = (func.lower(Patient.given_name) == data["given_name"].lower()) & (
        func.lower(Patient.family_name) == (data.get("family_name") or "").lower()
    )
    if data.get("birth_date"):
        clauses.append(name_match & (Patient.birth_date == data["birth_date"]))
    else:
        clauses.append(name_match & Patient.birth_date.is_(None))
    stmt = select(Patient).where(Patient.organization_id == org_id, or_(*clauses)).limit(10)
    if exclude:
        stmt = stmt.where(Patient.id != exclude)
    out = []
    for p in (await db.scalars(stmt)).all():
        reasons = []
        if data.get("phone") and p.phone == data["phone"]:
            reasons.append("same_phone")
        if (
            p.given_name.lower() == data["given_name"].lower()
            and p.family_name.lower() == (data.get("family_name") or "").lower()
        ):
            reasons.append("same_name")
            if data.get("birth_date") and p.birth_date == data["birth_date"]:
                reasons.append("same_birth_date")
        out.append((p, reasons))
    return out


async def _apply_consent(
    db: AsyncSession, ctx: OrgContext, patient_id: uuid.UUID, c: ConsentInput
) -> ConsentRecord:
    rec = await db.scalar(
        select(ConsentRecord)
        .where(
            ConsentRecord.organization_id == ctx.organization_id,
            ConsentRecord.patient_id == patient_id,
            ConsentRecord.consent_type == c.consent_type,
        )
        .with_for_update()
    )
    if rec is None:
        rec = ConsentRecord(
            organization_id=ctx.organization_id,
            patient_id=patient_id,
            consent_type=c.consent_type,
            status=c.status,
        )
        db.add(rec)
        await db.flush()
    else:
        rec.status = c.status
    db.add(
        ConsentEvent(
            organization_id=ctx.organization_id,
            consent_record_id=rec.id,
            status=c.status,
            method=c.method,
            recorded_by_user_id=ctx.user_id,
        )
    )
    add_audit(
        db,
        action="consent.recorded",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
        entity_type="patient",
        entity_id=patient_id,
        details={"type": c.consent_type, "status": c.status},
    )
    return rec


async def create_patient(
    db: AsyncSession, ctx: OrgContext, body: PatientCreate
) -> tuple[Patient, list[tuple[Patient, list[str]]]]:
    data = body.model_dump(exclude={"consents"})
    dups = await find_possible_duplicates(db, ctx.organization_id, data)
    for _attempt in range(5):
        patient = Patient(
            organization_id=ctx.organization_id,
            record_number=_record_number(),
            created_by_user_id=ctx.user_id,
            **data,
        )
        try:
            async with db.begin_nested():
                db.add(patient)
                await db.flush()
            break
        except IntegrityError:
            continue
    else:
        raise Conflict("Could not allocate a record number; retry")
    for c in body.consents:
        await _apply_consent(db, ctx, patient.id, c)
    add_audit(
        db,
        action="patient.created",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
        entity_type="patient",
        entity_id=patient.id,
        details={"possible_duplicates": len(dups)},
    )
    await db.commit()
    return patient, dups


async def update_patient(
    db: AsyncSession, ctx: OrgContext, patient_id: uuid.UUID, body: PatientUpdate
) -> Patient:
    patient = await get_patient(db, ctx.organization_id, patient_id)
    if patient.lock_version != body.lock_version:
        raise Conflict(
            "Patient was modified by someone else; reload and retry", code="stale_version"
        )
    for k, v in body.model_dump(exclude={"lock_version"}).items():
        setattr(patient, k, v)
    add_audit(
        db,
        action="patient.updated",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
        entity_type="patient",
        entity_id=patient.id,
    )
    try:
        await db.commit()
    except StaleDataError as exc:
        await db.rollback()
        raise Conflict(
            "Patient was modified by someone else; reload and retry", code="stale_version"
        ) from exc
    return patient


def search_stmt(org_id: uuid.UUID, q: str | None) -> Select[Patient]:
    stmt = select(Patient).where(Patient.organization_id == org_id, Patient.is_active)
    if q:
        q = q.strip()
        like = f"%{q.replace('%', r'\%').replace('_', r'\_')}%"
        stmt = stmt.where(
            or_(
                Patient.record_number == q.upper(),
                Patient.phone == q,
                Patient.given_name.ilike(like),
                Patient.family_name.ilike(like),
            )
        )
    return stmt


async def search_patients(
    db: AsyncSession, org_id: uuid.UUID, q: str | None, sort: str, limit: int, offset: int
) -> tuple[list[Patient], int]:
    if sort.lstrip("-") not in SORTABLE:
        raise ValidationFailed(f"sort must be one of {sorted(SORTABLE)} (prefix - for descending)")
    col = SORTABLE[sort.lstrip("-")]
    stmt = search_stmt(org_id, q)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await db.scalars(
        stmt.order_by(col.desc() if sort.startswith("-") else col.asc(), Patient.id)
        .limit(limit)
        .offset(offset)
    )
    return list(rows.all()), total


async def record_consent(
    db: AsyncSession, ctx: OrgContext, patient_id: uuid.UUID, c: ConsentInput
) -> ConsentRecord:
    await get_patient(db, ctx.organization_id, patient_id)
    rec = await _apply_consent(db, ctx, patient_id, c)
    await db.commit()
    await db.refresh(rec)
    return rec


async def consent_status(
    db: AsyncSession, org_id: uuid.UUID, patient_id: uuid.UUID, consent_type: str
) -> str | None:
    return await db.scalar(
        select(ConsentRecord.status).where(
            ConsentRecord.organization_id == org_id,
            ConsentRecord.patient_id == patient_id,
            ConsentRecord.consent_type == consent_type,
        )
    )


async def list_consents(
    db: AsyncSession, org_id: uuid.UUID, patient_id: uuid.UUID
) -> list[ConsentRecord]:
    return list(
        (
            await db.scalars(
                select(ConsentRecord).where(
                    ConsentRecord.organization_id == org_id, ConsentRecord.patient_id == patient_id
                )
            )
        ).all()
    )


async def consent_history(
    db: AsyncSession, org_id: uuid.UUID, patient_id: uuid.UUID
) -> list[tuple[ConsentEvent, str]]:
    rows = await db.execute(
        select(ConsentEvent, ConsentRecord.consent_type)
        .join(ConsentRecord, ConsentRecord.id == ConsentEvent.consent_record_id)
        .where(ConsentRecord.organization_id == org_id, ConsentRecord.patient_id == patient_id)
        .order_by(ConsentEvent.created_at)
    )
    return [(e, t) for e, t in rows.all()]


async def add_identifier(
    db: AsyncSession, ctx: OrgContext, patient_id: uuid.UUID, system: str, value: str
) -> PatientIdentifier:
    await get_patient(db, ctx.organization_id, patient_id)
    ident = PatientIdentifier(
        organization_id=ctx.organization_id, patient_id=patient_id, system=system, value=value
    )
    db.add(ident)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise Conflict("This identifier is already assigned to a patient") from exc
    add_audit(
        db,
        action="patient.identifier_added",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
        entity_type="patient",
        entity_id=patient_id,
        details={"system": system},
    )
    await db.commit()
    return ident
