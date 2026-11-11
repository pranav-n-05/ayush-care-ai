import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schemas import ERROR_RESPONSES, APIModel
from app.db.session import get_db
from app.modules.audit.service import add_audit
from app.modules.identity.access import OrgContext, require
from app.modules.identity.permissions import P
from app.modules.summaries import service
from app.modules.summaries.models import SummaryVersion
from app.workers.dispatch import get_dispatcher

router = APIRouter(prefix="/api/v1", tags=["summaries"], responses=ERROR_RESPONSES)


class SummaryJobOut(APIModel):
    id: uuid.UUID
    encounter_id: uuid.UUID
    status: str
    attempts: int
    max_attempts: int
    failure_reason: str | None
    summary_id: uuid.UUID | None
    summary_version_number: int | None
    provider: str | None
    model: str | None
    prompt_version: str | None
    input_units: int | None
    output_units: int | None
    estimated_cost_usd: float | None
    created_at: datetime
    finished_at: datetime | None


class VersionOut(APIModel):
    version_number: int
    origin: str
    content: dict[str, Any]
    source_snapshot: list[dict[str, Any]]
    provider: str | None
    model: str | None
    prompt_version: str | None
    created_by_user_id: uuid.UUID
    created_at: datetime


class ApprovalOut(APIModel):
    version_number: int
    approved_by_user_id: uuid.UUID
    approved_at: datetime
    attestation: str


class SummaryOut(APIModel):
    id: uuid.UUID
    encounter_id: uuid.UUID
    status: Literal["draft", "approved"]
    current_version_number: int
    approved_version_number: int | None
    current_version: VersionOut | None
    versions: list[int]
    approvals: list[ApprovalOut]


class EditIn(APIModel):
    base_version_number: int
    content: dict[str, Any]


class ApproveIn(APIModel):
    version_number: int
    attestation_confirmed: Literal[True] = Field(description=service.ATTESTATION)


def _v(v: SummaryVersion) -> VersionOut:
    return VersionOut.model_validate(v)


async def _summary_out(db: AsyncSession, ctx: OrgContext, summary_id: uuid.UUID) -> SummaryOut:
    s = await service.get_summary(db, ctx.organization_id, summary_id)
    versions = await service.list_versions(db, ctx.organization_id, s.id)
    current = next((v for v in versions if v.version_number == s.current_version_number), None)
    apps = await service.approvals(db, ctx.organization_id, s.id)
    add_audit(
        db,
        action="summary.viewed",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
        entity_type="clinical_summary",
        entity_id=s.id,
    )
    await db.commit()
    return SummaryOut(
        id=s.id,
        encounter_id=s.encounter_id,
        status=s.status,
        current_version_number=s.current_version_number,
        approved_version_number=s.approved_version_number,
        current_version=_v(current) if current else None,
        versions=[v.version_number for v in versions],
        approvals=[
            ApprovalOut(
                version_number=n,
                approved_by_user_id=a.approved_by_user_id,
                approved_at=a.created_at,
                attestation=a.attestation,
            )
            for a, n in apps
        ],
    )


@router.post(
    "/encounters/{encounter_id}/summaries/generate", response_model=SummaryJobOut, status_code=202
)
async def generate(
    encounter_id: uuid.UUID,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ctx: OrgContext = Depends(require(P.SUMMARY_GENERATE)),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    job, created = await service.request_generation(db, ctx, encounter_id, idempotency_key)
    if created:
        get_dispatcher().enqueue("summary", job.id)
    return JSONResponse(
        status_code=202 if created else 200,
        content=SummaryJobOut.model_validate(job).model_dump(mode="json"),
    )


@router.get("/summary-jobs/{job_id}", response_model=SummaryJobOut)
async def job(
    job_id: uuid.UUID,
    ctx: OrgContext = Depends(require(P.SUMMARY_READ)),
    db: AsyncSession = Depends(get_db),
) -> SummaryJobOut:
    return SummaryJobOut.model_validate(await service.get_job(db, ctx.organization_id, job_id))


@router.get("/encounters/{encounter_id}/summary", response_model=SummaryOut)
async def for_encounter(
    encounter_id: uuid.UUID,
    ctx: OrgContext = Depends(require(P.SUMMARY_READ)),
    db: AsyncSession = Depends(get_db),
) -> SummaryOut:
    s = await service.get_summary_for_encounter(db, ctx.organization_id, encounter_id)
    return await _summary_out(db, ctx, s.id)


@router.get("/summaries/{summary_id}/versions/{number}", response_model=VersionOut)
async def version(
    summary_id: uuid.UUID,
    number: int,
    ctx: OrgContext = Depends(require(P.SUMMARY_READ)),
    db: AsyncSession = Depends(get_db),
) -> VersionOut:
    return _v(await service.get_version(db, ctx.organization_id, summary_id, number))


@router.post("/summaries/{summary_id}/versions", response_model=SummaryOut, status_code=201)
async def edit(
    summary_id: uuid.UUID,
    body: EditIn,
    ctx: OrgContext = Depends(require(P.SUMMARY_EDIT)),
    db: AsyncSession = Depends(get_db),
) -> SummaryOut:
    await service.create_edit(db, ctx, summary_id, body.base_version_number, body.content)
    return await _summary_out(db, ctx, summary_id)


@router.post("/summaries/{summary_id}/approve", response_model=SummaryOut)
async def approve(
    summary_id: uuid.UUID,
    body: ApproveIn,
    ctx: OrgContext = Depends(require(P.SUMMARY_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> SummaryOut:
    await service.approve(db, ctx, summary_id, body.version_number)
    return await _summary_out(db, ctx, summary_id)
