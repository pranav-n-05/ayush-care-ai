import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schemas import ERROR_RESPONSES
from app.db.session import get_db
from app.modules.audit.service import add_audit
from app.modules.encounters.service import get_encounter
from app.modules.identity.access import OrgContext, require
from app.modules.identity.permissions import P
from app.modules.intake import service
from app.modules.intake.models import IntakeAnswer, IntakeSession, QuestionnaireVersion
from app.modules.intake.schemas import (
    AnswerOut,
    AnswersSubmit,
    DraftCreate,
    QuestionnaireVersionOut,
    RenderedQuestion,
    SessionOut,
    StartSession,
)
from app.modules.triage.service import rule_coverage

router = APIRouter(prefix="/api/v1", tags=["intake"], responses=ERROR_RESPONSES)


def _version_out(v: QuestionnaireVersion) -> QuestionnaireVersionOut:
    return QuestionnaireVersionOut(
        id=v.id,
        template_id=v.template_id,
        version_number=v.version_number,
        status=v.status,
        clinical_review_status=v.clinical_review_status,
        title=v.definition["title"]["en"],
        published_at=v.published_at,
    )


def _answer_out(a: IntakeAnswer, code: str) -> AnswerOut:
    return AnswerOut(
        id=a.id,
        question_code=code,
        revision=a.revision,
        answer_status=a.answer_status,
        value=a.value,
        source=a.source,
        original_language=a.original_language,
        original_text=a.original_text,
        translated_text_en=a.translated_text_en,
        translation_status=a.translation_status,
        entered_by_user_id=a.entered_by_user_id,
        change_reason=a.change_reason,
        created_at=a.created_at,
    )


@router.get("/questionnaires", response_model=list[QuestionnaireVersionOut])
async def published(
    ctx: OrgContext = Depends(require(P.INTAKE_READ)), db: AsyncSession = Depends(get_db)
) -> list[QuestionnaireVersionOut]:
    return [_version_out(v) for v in await service.list_published_versions(db, ctx.organization_id)]


@router.post(
    "/questionnaires/{template_id}/versions",
    response_model=QuestionnaireVersionOut,
    status_code=201,
)
async def create_draft(
    template_id: uuid.UUID,
    body: DraftCreate,
    ctx: OrgContext = Depends(require(P.QUESTIONNAIRE_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> QuestionnaireVersionOut:
    return _version_out(await service.create_draft_version(db, ctx, template_id, body.definition))


@router.post("/questionnaire-versions/{version_id}/publish", response_model=QuestionnaireVersionOut)
async def publish(
    version_id: uuid.UUID,
    ctx: OrgContext = Depends(require(P.QUESTIONNAIRE_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> QuestionnaireVersionOut:
    return _version_out(await service.publish_version(db, ctx, version_id))


@router.post(
    "/encounters/{encounter_id}/intake-sessions", response_model=SessionOut, status_code=201
)
async def start(
    encounter_id: uuid.UUID,
    body: StartSession,
    ctx: OrgContext = Depends(require(P.INTAKE_ANSWER)),
    db: AsyncSession = Depends(get_db),
) -> SessionOut:
    session = await service.start_session(
        db, ctx, encounter_id, body.questionnaire_version_id, body.language
    )
    return await _render(db, ctx, session.id)


@router.get("/encounters/{encounter_id}/intake-sessions", response_model=list[uuid.UUID])
async def list_sessions(
    encounter_id: uuid.UUID,
    ctx: OrgContext = Depends(require(P.INTAKE_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[uuid.UUID]:
    await get_encounter(db, ctx.organization_id, encounter_id)
    rows = await db.scalars(
        select(IntakeSession.id)
        .where(
            IntakeSession.organization_id == ctx.organization_id,
            IntakeSession.encounter_id == encounter_id,
        )
        .order_by(IntakeSession.created_at)
    )
    return list(rows.all())


async def _render(db: AsyncSession, ctx: OrgContext, session_id: uuid.UUID) -> SessionOut:
    loaded = await service.load_session(db, ctx.organization_id, session_id)
    lang = loaded.session.language
    states = {s["code"]: s for s in service.question_states(loaded)}
    rendered = []
    for section, q in loaded.definition.questions():
        text, fallback = q.text.render(lang)
        row = loaded.questions[q.code]
        current = loaded.current.get(row.id)
        rendered.append(
            RenderedQuestion(
                code=q.code,
                section=section.code,
                type=q.type,
                respondent=q.respondent,
                required=q.required,
                text=text,
                text_is_fallback=fallback,
                help=q.help.render(lang)[0] if q.help else None,
                options=[{"code": o.code, "label": o.label.render(lang)[0]} for o in q.options]
                if q.options
                else None,
                min=q.min,
                max=q.max,
                unit=q.unit,
                visible=states[q.code]["visible"],
                state=states[q.code]["state"],
                current_answer=_answer_out(current, q.code) if current else None,
            )
        )
    add_audit(
        db,
        action="intake.session_viewed",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
        entity_type="intake_session",
        entity_id=loaded.session.id,
    )
    coverage = await rule_coverage(db, loaded)
    await db.commit()
    return SessionOut(
        id=loaded.session.id,
        encounter_id=loaded.session.encounter_id,
        questionnaire_version_id=loaded.version.id,
        questionnaire_clinical_review_status=loaded.version.clinical_review_status,
        clinical_disclaimer=loaded.definition.clinical_disclaimer,
        status=loaded.session.status,
        language=lang,
        submitted_at=loaded.session.submitted_at,
        reviewed_at=loaded.session.reviewed_at,
        questions=rendered,
        missing_required=service.missing_required(loaded),
        red_flag_rule_coverage=coverage,
    )


@router.get("/intake-sessions/{session_id}", response_model=SessionOut)
async def get_session(
    session_id: uuid.UUID,
    ctx: OrgContext = Depends(require(P.INTAKE_READ)),
    db: AsyncSession = Depends(get_db),
) -> SessionOut:
    return await _render(db, ctx, session_id)


@router.post("/intake-sessions/{session_id}/answers", response_model=SessionOut)
async def submit_answers(
    session_id: uuid.UUID,
    body: AnswersSubmit,
    ctx: OrgContext = Depends(require(P.INTAKE_ANSWER)),
    db: AsyncSession = Depends(get_db),
) -> SessionOut:
    inputs = [service.AnswerInput(**a.model_dump()) for a in body.answers]
    await service.submit_answers(db, ctx, session_id, inputs)
    return await _render(db, ctx, session_id)


@router.post("/intake-sessions/{session_id}/submit", response_model=SessionOut)
async def submit(
    session_id: uuid.UUID,
    ctx: OrgContext = Depends(require(P.INTAKE_ANSWER)),
    db: AsyncSession = Depends(get_db),
) -> SessionOut:
    await service.submit_session(db, ctx, session_id)
    return await _render(db, ctx, session_id)


@router.post("/intake-sessions/{session_id}/review", response_model=SessionOut)
async def review(
    session_id: uuid.UUID,
    ctx: OrgContext = Depends(require(P.INTAKE_REVIEW)),
    db: AsyncSession = Depends(get_db),
) -> SessionOut:
    await service.review_session(db, ctx, session_id)
    return await _render(db, ctx, session_id)


@router.get(
    "/intake-sessions/{session_id}/answers/{question_code}/history", response_model=list[AnswerOut]
)
async def history(
    session_id: uuid.UUID,
    question_code: str,
    ctx: OrgContext = Depends(require(P.INTAKE_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[AnswerOut]:
    return [
        _answer_out(a, question_code)
        for a in await service.answer_history(db, ctx.organization_id, session_id, question_code)
    ]
