import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.errors import NotFound, ValidationFailed
from app.core.schemas import ERROR_RESPONSES, APIModel, Page
from app.core.timeutil import utcnow
from app.db.session import get_db
from app.modules.audit.models import AuditEvent
from app.modules.audit.service import add_audit
from app.modules.documents.models import Document
from app.modules.encounters.models import Encounter
from app.modules.followups.models import FollowUpTask
from app.modules.identity.access import OrgContext, require
from app.modules.identity.models import PatientUserLink
from app.modules.identity.permissions import P
from app.modules.intake.models import IntakeSession
from app.modules.ocr.models import ExtractedEntity, OCRJob
from app.modules.patients.models import Patient
from app.modules.patients.service import get_patient
from app.modules.summaries.models import ClinicalSummary, SummaryApproval, SummaryVersion
from app.modules.triage.models import TriageEvent

router = APIRouter(prefix="/api/v1", responses=ERROR_RESPONSES)


class Metric(APIModel):
    key: str
    value: int
    definition: str


class Overview(APIModel):
    generated_at: datetime
    metrics: list[Metric]
    open_red_flags_from_demo_rules: int


async def _count(db: AsyncSession, stmt: Select[Any]) -> int:
    return int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)


@router.get("/dashboard/overview", response_model=Overview, tags=["dashboard"])
async def overview(
    ctx: OrgContext = Depends(require(P.DASHBOARD_READ)), db: AsyncSession = Depends(get_db)
) -> Overview:
    org = ctx.organization_id
    now = utcnow()
    specs = [
        (
            "open_encounters",
            select(Encounter.id).where(
                Encounter.organization_id == org, Encounter.status.in_(("open", "in_review"))
            ),
            "Encounters with status open or in_review.",
        ),
        (
            "intake_in_progress",
            select(IntakeSession.id).where(
                IntakeSession.organization_id == org, IntakeSession.status == "in_progress"
            ),
            "Intake sessions started but not submitted.",
        ),
        (
            "intake_awaiting_review",
            select(IntakeSession.id).where(
                IntakeSession.organization_id == org, IntakeSession.status == "submitted"
            ),
            "Submitted intake sessions not yet marked reviewed by a practitioner.",
        ),
        (
            "unverified_extracted_entities",
            select(ExtractedEntity.id).where(
                ExtractedEntity.organization_id == org,
                ExtractedEntity.is_current,
                ExtractedEntity.verification_status == "unverified",
            ),
            "Current OCR-extracted entities awaiting reviewer verification.",
        ),
        (
            "ocr_jobs_pending_or_failed",
            select(OCRJob.id).where(
                OCRJob.organization_id == org, OCRJob.status.in_(("queued", "running", "failed"))
            ),
            "OCR jobs queued, running or failed.",
        ),
        (
            "summaries_pending_approval",
            select(ClinicalSummary.id).where(
                ClinicalSummary.organization_id == org,
                ClinicalSummary.status == "draft",
                ClinicalSummary.current_version_number > 0,
            ),
            "Summaries whose latest version has not been approved.",
        ),
        (
            "open_red_flags",
            select(TriageEvent.id).where(
                TriageEvent.organization_id == org, TriageEvent.status.in_(("open", "escalated"))
            ),
            "Red-flag events that are open or escalated (includes demo-rule events).",
        ),
        (
            "follow_ups_due_24h",
            select(FollowUpTask.id).where(
                FollowUpTask.organization_id == org,
                FollowUpTask.status == "scheduled",
                FollowUpTask.due_at <= now + timedelta(days=1),
            ),
            "Scheduled follow-ups due within 24 hours or overdue.",
        ),
    ]
    metrics = [Metric(key=k, value=await _count(db, s), definition=d) for k, s, d in specs]
    demo = await _count(
        db,
        select(TriageEvent.id).where(
            TriageEvent.organization_id == org,
            TriageEvent.status.in_(("open", "escalated")),
            TriageEvent.is_demo_rule,
        ),
    )
    return Overview(generated_at=now, metrics=metrics, open_red_flags_from_demo_rules=demo)


class Analytics(APIModel):
    period_start: date
    period_end: date
    metrics: list[Metric]
    rates: dict[str, float | None]
    rate_definitions: dict[str, str]


@router.get("/analytics/summary", response_model=Analytics, tags=["analytics"])
async def analytics(
    start: date = Query(...),
    end: date = Query(...),
    ctx: OrgContext = Depends(require(P.ANALYTICS_READ)),
    db: AsyncSession = Depends(get_db),
) -> Analytics:
    if end < start or (end - start).days > 366:
        raise ValidationFailed(
            "Period (UTC days, inclusive) must be at most 366 days with end >= start"
        )
    org = ctx.organization_id
    lo = datetime.combine(start, time.min, tzinfo=UTC)
    hi = datetime.combine(end + timedelta(days=1), time.min, tzinfo=UTC)

    def in_period(col: InstrumentedAttribute[datetime]) -> ColumnElement[bool]:
        return (col >= lo) & (col < hi)

    registrations = await _count(
        db, select(Patient.id).where(Patient.organization_id == org, in_period(Patient.created_at))
    )
    encounters = await _count(
        db,
        select(Encounter.id).where(
            Encounter.organization_id == org, in_period(Encounter.started_at)
        ),
    )
    sessions = await _count(
        db,
        select(IntakeSession.id).where(
            IntakeSession.organization_id == org, in_period(IntakeSession.created_at)
        ),
    )
    completed = await _count(
        db,
        select(IntakeSession.id).where(
            IntakeSession.organization_id == org,
            in_period(IntakeSession.created_at),
            IntakeSession.status.in_(("submitted", "reviewed")),
        ),
    )
    approvals = await _count(
        db,
        select(SummaryApproval.id).where(
            SummaryApproval.organization_id == org, in_period(SummaryApproval.created_at)
        ),
    )
    edited_approvals = await _count(
        db,
        select(SummaryApproval.id)
        .join(SummaryVersion, SummaryVersion.id == SummaryApproval.summary_version_id)
        .where(
            SummaryApproval.organization_id == org,
            in_period(SummaryApproval.created_at),
            SummaryVersion.origin == "practitioner_edit",
        ),
    )
    flags = await _count(
        db,
        select(TriageEvent.id).where(
            TriageEvent.organization_id == org, in_period(TriageEvent.evaluated_at)
        ),
    )
    ocr_ok = await _count(
        db,
        select(OCRJob.id).where(
            OCRJob.organization_id == org,
            in_period(OCRJob.created_at),
            OCRJob.status == "succeeded",
        ),
    )
    ocr_failed = await _count(
        db,
        select(OCRJob.id).where(
            OCRJob.organization_id == org, in_period(OCRJob.created_at), OCRJob.status == "failed"
        ),
    )
    fu_done = await _count(
        db,
        select(FollowUpTask.id).where(
            FollowUpTask.organization_id == org,
            in_period(FollowUpTask.due_at),
            FollowUpTask.status == "completed",
        ),
    )
    fu_due = await _count(
        db,
        select(FollowUpTask.id).where(
            FollowUpTask.organization_id == org,
            in_period(FollowUpTask.due_at),
            FollowUpTask.due_at <= utcnow(),
        ),
    )

    def rate(n: int, d: int) -> float | None:
        return round(n / d, 4) if d else None

    return Analytics(
        period_start=start,
        period_end=end,
        metrics=[
            Metric(
                key="patient_registrations",
                value=registrations,
                definition="Patients created in period.",
            ),
            Metric(key="encounters", value=encounters, definition="Encounters started in period."),
            Metric(
                key="intake_sessions_started",
                value=sessions,
                definition="Intake sessions created in period.",
            ),
            Metric(
                key="summary_approvals",
                value=approvals,
                definition="Summary versions approved in period.",
            ),
            Metric(
                key="red_flag_events",
                value=flags,
                definition="Red-flag events evaluated in period (demo rules included).",
            ),
            Metric(
                key="ocr_jobs_succeeded",
                value=ocr_ok,
                definition="OCR jobs created in period that succeeded.",
            ),
            Metric(
                key="ocr_jobs_failed",
                value=ocr_failed,
                definition="OCR jobs created in period that failed.",
            ),
        ],
        rates={
            "intake_completion": rate(completed, sessions),
            "approved_after_practitioner_edit": rate(edited_approvals, approvals),
            "follow_up_completion": rate(fu_done, fu_due),
        },
        rate_definitions={
            "intake_completion": "Sessions created in period now submitted/reviewed ÷ sessions created in period.",
            "approved_after_practitioner_edit": "Approvals in period of practitioner-edited versions ÷ all approvals in period.",
            "follow_up_completion": "Completed follow-ups due in period ÷ follow-ups due in period up to now.",
        },
    )


class TimelineItem(APIModel):
    encounter_id: uuid.UUID
    started_at: datetime
    status: str
    visit_reason: str | None
    intake_sessions: int
    documents: int
    summary_status: str | None
    approved_version: int | None
    open_red_flags: int


@router.get("/patients/{patient_id}/timeline", response_model=list[TimelineItem], tags=["patients"])
async def timeline(
    patient_id: uuid.UUID,
    ctx: OrgContext = Depends(require(P.ENCOUNTER_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[TimelineItem]:
    org = ctx.organization_id
    await get_patient(db, org, patient_id)
    encs = (
        await db.scalars(
            select(Encounter)
            .where(Encounter.organization_id == org, Encounter.patient_id == patient_id)
            .order_by(Encounter.started_at.desc())
        )
    ).all()
    out = []
    for e in encs:
        summary = await db.scalar(
            select(ClinicalSummary).where(
                ClinicalSummary.organization_id == org, ClinicalSummary.encounter_id == e.id
            )
        )
        out.append(
            TimelineItem(
                encounter_id=e.id,
                started_at=e.started_at,
                status=e.status,
                visit_reason=e.visit_reason,
                intake_sessions=await _count(
                    db,
                    select(IntakeSession.id).where(
                        IntakeSession.organization_id == org, IntakeSession.encounter_id == e.id
                    ),
                ),
                documents=await _count(
                    db,
                    select(Document.id).where(
                        Document.organization_id == org, Document.encounter_id == e.id
                    ),
                ),
                summary_status=summary.status if summary else None,
                approved_version=summary.approved_version_number if summary else None,
                open_red_flags=await _count(
                    db,
                    select(TriageEvent.id).where(
                        TriageEvent.organization_id == org,
                        TriageEvent.encounter_id == e.id,
                        TriageEvent.status.in_(("open", "escalated")),
                    ),
                ),
            )
        )
    return out


class AuditOut(APIModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    action: str
    entity_type: str | None
    entity_id: uuid.UUID | None
    outcome: str
    correlation_id: str | None
    details: dict[str, object]
    created_at: datetime


@router.get("/audit-events", response_model=Page[AuditOut], tags=["audit"])
async def audit_events(
    action: str | None = Query(None, max_length=80),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: OrgContext = Depends(require(P.AUDIT_READ)),
    db: AsyncSession = Depends(get_db),
) -> Page[AuditOut]:
    stmt = select(AuditEvent).where(AuditEvent.organization_id == ctx.organization_id)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    total = await _count(db, stmt)
    rows = (
        await db.scalars(stmt.order_by(AuditEvent.created_at.desc()).limit(limit).offset(offset))
    ).all()
    return Page(
        items=[AuditOut.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )


class SelfRecord(APIModel):
    record_number: str
    given_name: str
    family_name: str
    preferred_language: str
    encounter_dates: list[datetime]


@router.get("/me/patient-record", response_model=SelfRecord, tags=["patient self-access"])
async def own_record(
    ctx: OrgContext = Depends(require(P.SELF_READ_OWN_RECORD)), db: AsyncSession = Depends(get_db)
) -> SelfRecord:
    link = await db.scalar(
        select(PatientUserLink).where(
            PatientUserLink.organization_id == ctx.organization_id,
            PatientUserLink.user_id == ctx.user_id,
        )
    )
    if link is None:
        raise NotFound("No patient record is linked to this account")
    p = await get_patient(db, ctx.organization_id, link.patient_id)
    dates = (
        await db.scalars(
            select(Encounter.started_at)
            .where(Encounter.organization_id == ctx.organization_id, Encounter.patient_id == p.id)
            .order_by(Encounter.started_at)
        )
    ).all()
    add_audit(
        db,
        action="patient.self_viewed",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
        entity_type="patient",
        entity_id=p.id,
    )
    await db.commit()
    return SelfRecord(
        record_number=p.record_number,
        given_name=p.given_name,
        family_name=p.family_name,
        preferred_language=p.preferred_language,
        encounter_dates=list(dates),
    )
