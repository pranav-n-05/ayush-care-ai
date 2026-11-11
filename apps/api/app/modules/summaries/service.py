import hashlib
import json
import uuid
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.logging import get_logger
from app.core.timeutil import utcnow
from app.db.session import session_scope
from app.modules.audit.service import add_audit
from app.modules.encounters.models import Encounter
from app.modules.encounters.service import get_encounter
from app.modules.identity.access import OrgContext
from app.modules.identity.models import Organization
from app.modules.patients.service import consent_status
from app.modules.summaries.models import (
    ClinicalSummary,
    SummaryApproval,
    SummaryJob,
    SummaryVersion,
)
from app.modules.summaries.schema import SummaryContent
from app.modules.summaries.sources import SourceSet, collect_sources
from app.modules.summaries.validation import SummaryValidationError, validate_content
from app.providers.demo_summarizer import DemoExtractiveProvider
from app.providers.llm import (
    PROMPT_VERSION,
    LLMProvider,
    ProviderError,
    SummaryRequest,
    call_with_timeout,
)

log = get_logger("summaries")
RUNNING_TIMEOUT = timedelta(minutes=10)  # reclaim jobs orphaned by a crashed/stopped worker
ATTESTATION = (
    "I have reviewed this draft against its cited sources and approve this version for the record."
)

_provider: LLMProvider | None = None


def get_llm_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        _provider = DemoExtractiveProvider()
    return _provider


def set_llm_provider(p: LLMProvider | None) -> None:
    global _provider
    _provider = p


async def _require_ai_consent(db: AsyncSession, org_id: uuid.UUID, enc: Encounter) -> None:
    if await consent_status(db, org_id, enc.patient_id, "ai_assisted_documentation") != "granted":
        raise Conflict(
            "Patient has not granted consent for AI-assisted documentation", code="consent_required"
        )


async def request_generation(
    db: AsyncSession, ctx: OrgContext, encounter_id: uuid.UUID, key: str
) -> tuple[SummaryJob, bool]:
    if not 8 <= len(key) <= 100:
        raise ValidationFailed("Idempotency-Key header must be 8-100 characters")
    enc = await get_encounter(db, ctx.organization_id, encounter_id)
    await _require_ai_consent(db, ctx.organization_id, enc)
    existing = await db.scalar(
        select(SummaryJob).where(
            SummaryJob.organization_id == ctx.organization_id,
            SummaryJob.encounter_id == enc.id,
            SummaryJob.idempotency_key == key,
        )
    )
    if existing:
        return existing, False
    job = SummaryJob(
        organization_id=ctx.organization_id,
        encounter_id=enc.id,
        idempotency_key=key,
        requested_by_user_id=ctx.user_id,
        max_attempts=get_settings().llm_max_attempts,
    )
    db.add(job)
    await db.flush()
    add_audit(
        db,
        action="summary.generation_requested",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
        entity_type="summary_job",
        entity_id=job.id,
    )
    await db.commit()
    return job, True


def _request_from(sources: SourceSet, prompts: dict[str, str]) -> SummaryRequest:
    return SummaryRequest(
        sources=[
            {
                "kind": s.kind,
                "id": s.id,
                "revision": s.revision,
                "provenance": s.provenance,
                "label": s.label,
                "prompt_en": s.prompt_en,
                "section": s.section,
                "answer_status": s.answer_status,
                "value": s.value,
                "text_en": s.text_en,
                "translation_status": s.translation_status,
            }
            for s in sources.sources
        ],
        missing=[
            {"question_code": c, "state": st, "prompt_en": prompts.get(c, c)}
            for c, st in sources.unanswered_required
        ],
        output_schema=SummaryContent.model_json_schema(),
    )


async def _next_version(db: AsyncSession, summary: ClinicalSummary) -> int:
    summary.current_version_number += 1
    if summary.status == "approved":
        summary.status = "draft"  # a newer version always needs its own approval
    return summary.current_version_number


async def _get_or_create_summary(
    db: AsyncSession, org_id: uuid.UUID, encounter_id: uuid.UUID
) -> ClinicalSummary:
    summary = await db.scalar(
        select(ClinicalSummary)
        .where(
            ClinicalSummary.organization_id == org_id, ClinicalSummary.encounter_id == encounter_id
        )
        .with_for_update()
    )
    if summary is None:
        try:
            async with db.begin_nested():
                summary = ClinicalSummary(organization_id=org_id, encounter_id=encounter_id)
                db.add(summary)
                await db.flush()
        except IntegrityError:
            summary = await db.scalar(
                select(ClinicalSummary)
                .where(
                    ClinicalSummary.organization_id == org_id,
                    ClinicalSummary.encounter_id == encounter_id,
                )
                .with_for_update()
            )
    assert summary is not None
    return summary


async def run_summary_job(job_id: uuid.UUID) -> str:
    """Worker entry point (own sessions, IDs only). Failed provider calls or invalid output
    mark the job failed/retryable — they never produce a placeholder summary."""
    async with session_scope() as db:
        job = await db.scalar(
            select(SummaryJob).where(SummaryJob.id == job_id).with_for_update(skip_locked=True)
        )
        if job is None:
            return "missing"
        stuck = job.status == "running" and utcnow() - job.updated_at > RUNNING_TIMEOUT
        if job.status in ("succeeded", "failed") or (job.status == "running" and not stuck):
            return job.status
        job.status, job.attempts = "running", job.attempts + 1
        org_id, encounter_id = job.organization_id, job.encounter_id

    provider = get_llm_provider()
    outcome: str
    reason: str | None = None
    try:
        async with session_scope() as db:
            org = await db.get(Organization, org_id)
            enc = await db.get(Encounter, encounter_id)
            assert org is not None and enc is not None and enc.organization_id == org_id
            if provider.is_external and not org.external_ai_approved:
                raise PermissionError(
                    "External AI processing is not approved for this organization"
                )
            await _require_ai_consent(db, org_id, enc)
            sources = await collect_sources(db, org_id, encounter_id)
            if not sources.sources:
                raise ValueError(
                    "No submitted intake answers or verified document entities to summarize"
                )
            prompts = {s.label: s.prompt_en for s in sources.sources}
            request = _request_from(sources, prompts)
        result = await call_with_timeout(provider, request, get_settings().llm_timeout_seconds)
        content = validate_content(result.raw_output, sources, allow_practitioner_authored=False)
        async with session_scope() as db:
            # Sources may have changed while the model ran; re-collect and re-validate.
            fresh = await collect_sources(db, org_id, encounter_id)
            if fresh.snapshot_hash() != sources.snapshot_hash():
                raise ProviderError("Sources changed during generation")
            summary = await _get_or_create_summary(db, org_id, encounter_id)
            number = await _next_version(db, summary)
            job = await db.get(SummaryJob, job_id, with_for_update=True)
            assert job is not None
            db.add(
                SummaryVersion(
                    organization_id=org_id,
                    summary_id=summary.id,
                    version_number=number,
                    origin="ai_draft",
                    content=content.model_dump(mode="json"),
                    source_snapshot=sources.snapshot(),
                    source_snapshot_hash=sources.snapshot_hash(),
                    provider=provider.name,
                    model=provider.model,
                    prompt_version=PROMPT_VERSION,
                    created_by_user_id=job.requested_by_user_id,
                )
            )
            job.status, job.summary_id, job.summary_version_number = "succeeded", summary.id, number
            job.provider, job.model, job.prompt_version = (
                provider.name,
                provider.model,
                PROMPT_VERSION,
            )
            job.input_units, job.output_units = result.input_units, result.output_units
            job.estimated_cost_usd = Decimal(str(result.estimated_cost_usd))  # type: ignore[assignment]
            job.finished_at = utcnow()
            add_audit(
                db,
                action="summary.draft_created",
                organization_id=org_id,
                actor_user_id=None,
                entity_type="clinical_summary",
                entity_id=summary.id,
                details={"version": number},
            )
        return "succeeded"
    except (ProviderError, SummaryValidationError) as exc:
        outcome = "retry"
        reason = (
            "Model output failed validation"
            if isinstance(exc, SummaryValidationError)
            else "AI provider failure"
        )
        if isinstance(exc, SummaryValidationError):
            log.warning(
                "summary_validation_failed",
                job_id=str(job_id),
                error_count=len(exc.errors),
                errors=exc.errors[:5],
            )
    except (PermissionError, ValueError, Conflict) as exc:
        outcome, reason = "failed", (exc.message if isinstance(exc, Conflict) else str(exc))[:200]

    async with session_scope() as db:
        job = await db.get(SummaryJob, job_id, with_for_update=True)
        assert job is not None
        retry = outcome == "retry" and job.attempts < job.max_attempts
        job.status = "queued" if retry else "failed"
        job.failure_reason = None if retry else reason
        job.provider, job.model, job.prompt_version = provider.name, provider.model, PROMPT_VERSION
        job.finished_at = utcnow()
        add_audit(
            db,
            action="summary.generation_failed",
            organization_id=job.organization_id,
            actor_user_id=None,
            entity_type="summary_job",
            entity_id=job.id,
            outcome="failure",
            details={"retrying": retry},
        )
        return job.status


async def get_job(db: AsyncSession, org_id: uuid.UUID, job_id: uuid.UUID) -> SummaryJob:
    job = await db.scalar(
        select(SummaryJob).where(SummaryJob.id == job_id, SummaryJob.organization_id == org_id)
    )
    if job is None:
        raise NotFound("Job not found")
    return job


async def get_summary_for_encounter(
    db: AsyncSession, org_id: uuid.UUID, encounter_id: uuid.UUID
) -> ClinicalSummary:
    await get_encounter(db, org_id, encounter_id)
    s = await db.scalar(
        select(ClinicalSummary).where(
            ClinicalSummary.organization_id == org_id, ClinicalSummary.encounter_id == encounter_id
        )
    )
    if s is None:
        raise NotFound("No summary exists for this encounter")
    return s


async def get_summary(
    db: AsyncSession, org_id: uuid.UUID, summary_id: uuid.UUID, *, lock: bool = False
) -> ClinicalSummary:
    stmt = select(ClinicalSummary).where(
        ClinicalSummary.id == summary_id, ClinicalSummary.organization_id == org_id
    )
    if lock:
        stmt = stmt.with_for_update()
    s = await db.scalar(stmt)
    if s is None:
        raise NotFound("Summary not found")
    return s


async def list_versions(
    db: AsyncSession, org_id: uuid.UUID, summary_id: uuid.UUID
) -> list[SummaryVersion]:
    return list(
        (
            await db.scalars(
                select(SummaryVersion)
                .where(
                    SummaryVersion.organization_id == org_id,
                    SummaryVersion.summary_id == summary_id,
                )
                .order_by(SummaryVersion.version_number)
            )
        ).all()
    )


async def get_version(
    db: AsyncSession, org_id: uuid.UUID, summary_id: uuid.UUID, number: int
) -> SummaryVersion:
    v = await db.scalar(
        select(SummaryVersion).where(
            SummaryVersion.organization_id == org_id,
            SummaryVersion.summary_id == summary_id,
            SummaryVersion.version_number == number,
        )
    )
    if v is None:
        raise NotFound("Summary version not found")
    return v


async def approvals(
    db: AsyncSession, org_id: uuid.UUID, summary_id: uuid.UUID
) -> list[tuple[SummaryApproval, int]]:
    rows = await db.execute(
        select(SummaryApproval, SummaryVersion.version_number)
        .join(SummaryVersion, SummaryVersion.id == SummaryApproval.summary_version_id)
        .where(SummaryApproval.organization_id == org_id, SummaryVersion.summary_id == summary_id)
        .order_by(SummaryApproval.created_at)
    )
    return [(a, n) for a, n in rows.all()]


async def create_edit(
    db: AsyncSession,
    ctx: OrgContext,
    summary_id: uuid.UUID,
    base_version: int,
    content_raw: dict[str, object],
) -> SummaryVersion:
    summary = await get_summary(db, ctx.organization_id, summary_id, lock=True)
    if base_version != summary.current_version_number:
        raise Conflict("A newer version exists; reload before editing", code="stale_version")
    base = await get_version(db, ctx.organization_id, summary_id, base_version)
    sources = await collect_sources(db, ctx.organization_id, summary.encounter_id)
    try:
        content = validate_content(content_raw, sources, allow_practitioner_authored=True)
    except SummaryValidationError as exc:
        raise ValidationFailed("Edited summary failed validation", details=exc.errors) from exc
    number = await _next_version(db, summary)
    v = SummaryVersion(
        organization_id=ctx.organization_id,
        summary_id=summary.id,
        version_number=number,
        origin="practitioner_edit",
        content=content.model_dump(mode="json"),
        source_snapshot=sources.snapshot(),
        source_snapshot_hash=sources.snapshot_hash(),
        provider=base.provider,
        model=base.model,
        prompt_version=base.prompt_version,
        created_by_user_id=ctx.user_id,
    )
    db.add(v)
    add_audit(
        db,
        action="summary.edited",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
        entity_type="clinical_summary",
        entity_id=summary.id,
        details={"version": number, "base": base_version},
    )
    await db.commit()
    return v


async def approve(
    db: AsyncSession, ctx: OrgContext, summary_id: uuid.UUID, version_number: int
) -> SummaryApproval:
    summary = await get_summary(
        db, ctx.organization_id, summary_id, lock=True
    )  # serializes approvals
    if version_number != summary.current_version_number:
        raise Conflict("Only the latest version can be approved; reload", code="stale_version")
    if summary.approved_version_number == version_number:
        raise Conflict("This version is already approved", code="already_approved")
    version = await get_version(db, ctx.organization_id, summary_id, version_number)
    current = await collect_sources(db, ctx.organization_id, summary.encounter_id)
    if current.snapshot_hash() != version.source_snapshot_hash:
        raise Conflict(
            "Source records changed after this version was created; regenerate or edit before approving",
            code="sources_changed",
        )
    snapshot_hash = hashlib.sha256(
        (version.source_snapshot_hash + json.dumps(version.content, sort_keys=True)).encode()
    ).hexdigest()
    approval = SummaryApproval(
        organization_id=ctx.organization_id,
        summary_version_id=version.id,
        approved_by_membership_id=ctx.membership_id,
        approved_by_user_id=ctx.user_id,
        source_snapshot_hash=snapshot_hash,
        attestation=ATTESTATION,
    )
    db.add(approval)
    summary.status = "approved"
    summary.approved_version_number = version_number
    add_audit(
        db,
        action="summary.approved",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
        entity_type="clinical_summary",
        entity_id=summary.id,
        details={"version": version_number},
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise Conflict("This version is already approved", code="already_approved") from exc
    return approval
