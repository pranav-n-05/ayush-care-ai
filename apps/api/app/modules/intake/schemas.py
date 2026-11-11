import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.core.schemas import APIModel

AnswerStatus = Literal["answered", "unknown", "declined", "not_applicable"]


class QuestionnaireVersionOut(APIModel):
    id: uuid.UUID
    template_id: uuid.UUID
    version_number: int
    status: str
    clinical_review_status: str
    title: str
    published_at: datetime | None


class DraftCreate(APIModel):
    definition: dict[str, Any]


class StartSession(APIModel):
    questionnaire_version_id: uuid.UUID
    language: Literal["en", "hi", "ta"] = "en"


class AnswerIn(APIModel):
    question_code: str = Field(max_length=80)
    answer_status: AnswerStatus
    value: Any = None
    translated_text_en: str | None = Field(
        None,
        max_length=10000,
        description="Optional staff-provided English rendering; stored as a draft needing review",
    )
    change_reason: str | None = Field(None, max_length=200)


class AnswersSubmit(APIModel):
    answers: list[AnswerIn] = Field(min_length=1, max_length=100)


class AnswerOut(APIModel):
    id: uuid.UUID
    question_code: str
    revision: int
    answer_status: str
    value: Any
    source: str
    original_language: str
    original_text: str | None
    translated_text_en: str | None
    translation_status: str
    entered_by_user_id: uuid.UUID
    change_reason: str | None
    created_at: datetime


class RenderedQuestion(APIModel):
    code: str
    section: str
    type: str
    respondent: str
    required: bool
    text: str
    text_is_fallback: bool = Field(
        description="True when the requested language was missing and English was shown"
    )
    help: str | None
    options: list[dict[str, Any]] | None
    min: float | None
    max: float | None
    unit: str | None
    visible: bool
    state: str = Field(
        description="unanswered | answered | unknown | declined | not_applicable | not_asked"
    )
    current_answer: AnswerOut | None


class SessionOut(APIModel):
    id: uuid.UUID
    encounter_id: uuid.UUID
    questionnaire_version_id: uuid.UUID
    questionnaire_clinical_review_status: str
    clinical_disclaimer: str
    status: str
    language: str
    submitted_at: datetime | None
    reviewed_at: datetime | None
    questions: list[RenderedQuestion]
    missing_required: list[str]
    red_flag_rule_coverage: list[dict[str, str]]
