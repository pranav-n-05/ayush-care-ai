import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, NotFound, PermissionDenied, ValidationFailed
from app.core.timeutil import utcnow
from app.modules.audit.service import add_audit
from app.modules.encounters.service import get_encounter
from app.modules.identity.access import OrgContext
from app.modules.identity.permissions import P
from app.modules.intake import definition as qdef
from app.modules.intake.models import (
    IntakeAnswer,
    IntakeSession,
    Question,
    QuestionnaireTemplate,
    QuestionnaireVersion,
)

# ---------------- questionnaire authoring ----------------


async def create_template_with_draft(
    db: AsyncSession, org_id: uuid.UUID, raw: dict[str, Any]
) -> QuestionnaireVersion:
    parsed = _parse(raw)
    if await db.scalar(
        select(QuestionnaireTemplate).where(
            QuestionnaireTemplate.organization_id == org_id,
            QuestionnaireTemplate.code == parsed.code,
        )
    ):
        raise Conflict("A questionnaire with this code already exists")
    template = QuestionnaireTemplate(
        organization_id=org_id, code=parsed.code, title=parsed.title.en
    )
    db.add(template)
    await db.flush()
    version = QuestionnaireVersion(
        organization_id=org_id,
        template_id=template.id,
        version_number=1,
        status="draft",
        definition=raw,
        checksum=qdef.checksum(raw),
    )
    db.add(version)
    await db.flush()
    return version


async def create_draft_version(
    db: AsyncSession, ctx: OrgContext, template_id: uuid.UUID, raw: dict[str, Any]
) -> QuestionnaireVersion:
    template = await db.scalar(
        select(QuestionnaireTemplate).where(
            QuestionnaireTemplate.id == template_id,
            QuestionnaireTemplate.organization_id == ctx.organization_id,
        )
    )
    if template is None:
        raise NotFound("Questionnaire not found")
    parsed = _parse(raw)
    if parsed.code != template.code:
        raise ValidationFailed("Definition code must match the template code")
    latest = await db.scalar(
        select(func.max(QuestionnaireVersion.version_number)).where(
            QuestionnaireVersion.template_id == template.id
        )
    )
    version = QuestionnaireVersion(
        organization_id=ctx.organization_id,
        template_id=template.id,
        version_number=(latest or 0) + 1,
        status="draft",
        definition=raw,
        checksum=qdef.checksum(raw),
    )
    db.add(version)
    add_audit(
        db,
        action="questionnaire.draft_created",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
        entity_type="questionnaire_version",
    )
    await db.commit()
    return version


def _parse(raw: dict[str, Any]) -> qdef.QuestionnaireDef:
    try:
        return qdef.parse_definition(raw)
    except qdef.DefinitionError as exc:
        raise ValidationFailed("Invalid questionnaire definition", details=exc.errors) from exc


async def publish_version_unchecked(
    db: AsyncSession, version: QuestionnaireVersion, publisher_user_id: uuid.UUID | None
) -> None:
    if version.status != "draft":
        raise Conflict("Only draft versions can be published")
    parsed = _parse(version.definition)
    if qdef.checksum(version.definition) != version.checksum:
        raise Conflict("Draft definition changed unexpectedly")
    for position, (section, q) in enumerate(parsed.questions()):
        db.add(
            Question(
                organization_id=version.organization_id,
                questionnaire_version_id=version.id,
                code=q.code,
                section=section.code,
                position=position,
                answer_type=q.type,
                respondent=q.respondent,
                spec=q.model_dump(mode="json", exclude_none=True),
            )
        )
    version.status = "published"
    version.published_at = utcnow()
    version.published_by_user_id = publisher_user_id
    await db.flush()


async def publish_version(
    db: AsyncSession, ctx: OrgContext, version_id: uuid.UUID
) -> QuestionnaireVersion:
    version = await db.scalar(
        select(QuestionnaireVersion)
        .where(
            QuestionnaireVersion.id == version_id,
            QuestionnaireVersion.organization_id == ctx.organization_id,
        )
        .with_for_update()
    )
    if version is None:
        raise NotFound("Questionnaire version not found")
    await publish_version_unchecked(db, version, ctx.user_id)
    add_audit(
        db,
        action="questionnaire.published",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
        entity_type="questionnaire_version",
        entity_id=version.id,
    )
    await db.commit()
    return version


async def list_published_versions(
    db: AsyncSession, org_id: uuid.UUID
) -> list[QuestionnaireVersion]:
    return list(
        (
            await db.scalars(
                select(QuestionnaireVersion)
                .where(
                    QuestionnaireVersion.organization_id == org_id,
                    QuestionnaireVersion.status == "published",
                )
                .order_by(QuestionnaireVersion.created_at)
            )
        ).all()
    )


# ---------------- sessions & answers ----------------


async def start_session(
    db: AsyncSession, ctx: OrgContext, encounter_id: uuid.UUID, version_id: uuid.UUID, language: str
) -> IntakeSession:
    enc = await get_encounter(db, ctx.organization_id, encounter_id)
    if enc.status == "closed":
        raise Conflict("Encounter is closed")
    version = await db.scalar(
        select(QuestionnaireVersion).where(
            QuestionnaireVersion.id == version_id,
            QuestionnaireVersion.organization_id == ctx.organization_id,
        )
    )
    if version is None:
        raise NotFound("Questionnaire version not found")
    if version.status != "published":
        raise Conflict("Intake sessions can only use a published questionnaire version")
    session = IntakeSession(
        organization_id=ctx.organization_id,
        encounter_id=enc.id,
        questionnaire_version_id=version.id,
        language=language,
        started_by_user_id=ctx.user_id,
    )
    db.add(session)
    await db.flush()
    add_audit(
        db,
        action="intake.session_started",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
        entity_type="intake_session",
        entity_id=session.id,
    )
    await db.commit()
    return session


@dataclass
class LoadedSession:
    session: IntakeSession
    version: QuestionnaireVersion
    definition: qdef.QuestionnaireDef
    questions: dict[str, Question]
    current: dict[uuid.UUID, IntakeAnswer]  # question_id -> current answer

    def answer_map(self) -> qdef.Answers:
        by_id = {q.id: q.code for q in self.questions.values()}
        return {by_id[qid]: (a.answer_status, a.value) for qid, a in self.current.items()}


async def load_session(
    db: AsyncSession, org_id: uuid.UUID, session_id: uuid.UUID, *, lock: bool = False
) -> LoadedSession:
    stmt = select(IntakeSession).where(
        IntakeSession.id == session_id, IntakeSession.organization_id == org_id
    )
    if lock:
        stmt = stmt.with_for_update()
    session = await db.scalar(stmt)
    if session is None:
        raise NotFound("Intake session not found")
    version = await db.get(QuestionnaireVersion, session.questionnaire_version_id)
    assert version is not None and version.organization_id == org_id
    questions = {
        q.code: q
        for q in (
            await db.scalars(
                select(Question)
                .where(Question.questionnaire_version_id == version.id)
                .order_by(Question.position)
            )
        ).all()
    }
    current = {
        a.question_id: a
        for a in (
            await db.scalars(
                select(IntakeAnswer).where(
                    IntakeAnswer.intake_session_id == session.id, IntakeAnswer.is_current
                )
            )
        ).all()
    }
    return LoadedSession(
        session, version, qdef.parse_definition(version.definition), questions, current
    )


@dataclass
class AnswerInput:
    question_code: str
    answer_status: str
    value: Any = None
    translated_text_en: str | None = None
    change_reason: str | None = None


def _same(a: IntakeAnswer, inp: AnswerInput, value: Any) -> bool:
    return (
        a.answer_status == inp.answer_status
        and a.value == value
        and (inp.translated_text_en is None or a.translated_text_en == inp.translated_text_en)
    )


async def submit_answers(
    db: AsyncSession, ctx: OrgContext, session_id: uuid.UUID, inputs: list[AnswerInput]
) -> list[IntakeAnswer]:
    loaded = await load_session(db, ctx.organization_id, session_id, lock=True)
    session = loaded.session
    if session.status == "reviewed":
        raise Conflict("Session has been reviewed; start a new intake session for changes")
    editing_submitted = session.status == "submitted"
    if editing_submitted and not ctx.has(P.INTAKE_REVIEW):
        raise PermissionDenied("Only reviewers may change answers after submission")
    enc = await get_encounter(db, ctx.organization_id, session.encounter_id)
    if enc.status == "closed":
        raise Conflict("Encounter is closed")

    errors: list[dict[str, str]] = []
    written: list[IntakeAnswer] = []
    answers = loaded.answer_map()
    q_by_code = {q.code: q for _, q in loaded.definition.questions()}
    for inp in inputs:
        q_row = loaded.questions.get(inp.question_code)
        q_def = q_by_code.get(inp.question_code)
        if q_row is None or q_def is None:
            errors.append({"question": inp.question_code, "error": "Unknown question"})
            continue
        if inp.answer_status not in ("answered", "unknown", "declined", "not_applicable"):
            errors.append({"question": inp.question_code, "error": "Invalid answer status"})
            continue
        if not qdef.is_visible(loaded.definition, q_def.code, answers):
            errors.append(
                {
                    "question": inp.question_code,
                    "error": "Question is not applicable given earlier answers",
                }
            )
            continue
        if q_def.respondent == "practitioner" and not ctx.has(P.INTAKE_REVIEW):
            errors.append(
                {
                    "question": inp.question_code,
                    "error": "Practitioner observation requires reviewer permission",
                }
            )
            continue
        value: Any = None
        if inp.answer_status == "answered":
            try:
                value = qdef.validate_value(q_def, inp.value)
            except ValueError as exc:
                errors.append({"question": inp.question_code, "error": str(exc)})
                continue
        elif inp.value is not None:
            errors.append(
                {"question": inp.question_code, "error": "Value is only allowed when answered"}
            )
            continue
        prev = loaded.current.get(q_row.id)
        if prev is not None and _same(prev, inp, value):
            continue
        if editing_submitted and not inp.change_reason:
            errors.append(
                {
                    "question": inp.question_code,
                    "error": "A change reason is required after submission",
                }
            )
            continue
        is_text = q_def.type in ("text", "long_text") and inp.answer_status == "answered"
        if not is_text or session.language == "en":
            t_status = "not_required"
        elif inp.translated_text_en:
            t_status = "draft_requires_review"
        else:
            t_status = "translation_pending"
        if prev is not None:
            prev.is_current = False
            await db.flush()
        new = IntakeAnswer(
            organization_id=ctx.organization_id,
            intake_session_id=session.id,
            question_id=q_row.id,
            revision=(prev.revision + 1) if prev else 1,
            is_current=True,
            supersedes_id=prev.id if prev else None,
            answer_status=inp.answer_status,
            value=value,
            source="practitioner_observed"
            if q_def.respondent == "practitioner"
            else "patient_reported",
            original_language=session.language,
            original_text=value if is_text else None,
            translated_text_en=inp.translated_text_en if is_text else None,
            translation_status=t_status,
            entered_by_user_id=ctx.user_id,
            change_reason=inp.change_reason,
        )
        db.add(new)
        await db.flush()
        loaded.current[q_row.id] = new
        answers[q_def.code] = (new.answer_status, new.value)
        written.append(new)

    if errors:
        await db.rollback()
        raise ValidationFailed("Some answers were rejected; nothing was saved", details=errors)

    from app.modules.triage.service import evaluate_session

    await evaluate_session(db, loaded)
    add_audit(
        db,
        action="intake.answers_recorded",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
        entity_type="intake_session",
        entity_id=session.id,
        details={"count": len(written)},
    )
    await db.commit()
    return written


def question_states(loaded: LoadedSession) -> list[dict[str, Any]]:
    answers = loaded.answer_map()
    out = []
    for _, q in loaded.definition.questions():
        visible = qdef.is_visible(loaded.definition, q.code, answers)
        row = loaded.questions[q.code]
        current = loaded.current.get(row.id)
        if not visible:
            state = "not_asked"
        elif current is None:
            state = "unanswered"
        else:
            state = current.answer_status
        out.append({"code": q.code, "visible": visible, "state": state, "required": q.required})
    return out


def missing_required(loaded: LoadedSession) -> list[str]:
    return [
        s["code"]
        for s in question_states(loaded)
        if s["visible"] and s["required"] and s["state"] == "unanswered"
    ]


async def submit_session(db: AsyncSession, ctx: OrgContext, session_id: uuid.UUID) -> IntakeSession:
    loaded = await load_session(db, ctx.organization_id, session_id, lock=True)
    if loaded.session.status != "in_progress":
        raise Conflict("Session is not in progress")
    missing = missing_required(loaded)
    if missing:
        raise ValidationFailed("Required questions have no response", details={"missing": missing})
    loaded.session.status = "submitted"
    loaded.session.submitted_at = utcnow()
    add_audit(
        db,
        action="intake.session_submitted",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
        entity_type="intake_session",
        entity_id=loaded.session.id,
    )
    await db.commit()
    return loaded.session


async def review_session(db: AsyncSession, ctx: OrgContext, session_id: uuid.UUID) -> IntakeSession:
    loaded = await load_session(db, ctx.organization_id, session_id, lock=True)
    if loaded.session.status != "submitted":
        raise Conflict("Only submitted sessions can be marked reviewed")
    loaded.session.status = "reviewed"
    loaded.session.reviewed_at = utcnow()
    loaded.session.reviewed_by_user_id = ctx.user_id
    add_audit(
        db,
        action="intake.session_reviewed",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
        entity_type="intake_session",
        entity_id=loaded.session.id,
    )
    await db.commit()
    return loaded.session


async def answer_history(
    db: AsyncSession, org_id: uuid.UUID, session_id: uuid.UUID, question_code: str
) -> list[IntakeAnswer]:
    loaded = await load_session(db, org_id, session_id)
    q = loaded.questions.get(question_code)
    if q is None:
        raise NotFound("Question not found")
    return list(
        (
            await db.scalars(
                select(IntakeAnswer)
                .where(
                    IntakeAnswer.intake_session_id == session_id, IntakeAnswer.question_id == q.id
                )
                .order_by(IntakeAnswer.revision)
            )
        ).all()
    )
