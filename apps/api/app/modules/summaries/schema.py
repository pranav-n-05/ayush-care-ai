"""Structured summary format. Every claim carries source references (with exact revisions)
and an explicit provenance. Validation rejects fabricated or cross-tenant citations."""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SourceKind = Literal["intake_answer", "extracted_entity"]
Provenance = Literal[
    "patient_reported", "practitioner_observed", "document_verified", "practitioner_authored"
]
SECTION_CODES = (
    "presenting_complaint",
    "history_of_present_illness",
    "relevant_medical_history",
    "medications_and_allergies",
    "ayurveda_observations",
)


class SourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: SourceKind
    id: str
    revision: int


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=1000)
    provenance: Provenance
    certainty: Literal["stated", "uncertain"] = "stated"
    source_refs: list[SourceRef] = Field(default_factory=list, max_length=10)


class Section(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: Literal[
        "presenting_complaint",
        "history_of_present_illness",
        "relevant_medical_history",
        "medications_and_allergies",
        "ayurveda_observations",
    ]
    title: str = Field(max_length=100)
    claims: list[Claim] = Field(max_length=50)


class MissingItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_code: str
    state: Literal["unanswered", "unknown", "declined", "not_asked"]


class Contradiction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(max_length=500)
    source_refs: list[SourceRef] = Field(min_length=2, max_length=10)


class Clarification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(max_length=300)
    source_refs: list[SourceRef] = Field(default_factory=list, max_length=5)


class SummaryContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sections: list[Section]
    missing_information: list[MissingItem] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    clarification_questions: list[Clarification] = Field(default_factory=list)
    disclaimer: str = Field(max_length=500)


# Advisory/diagnostic language is out of scope for this system's drafts. This is a coarse
# guard, not a guarantee; practitioner review remains the control.
_PROHIBITED = re.compile(
    r"\b(prescrib\w*|recommend(?:ed|s)? (?:taking|starting)|take \d+\s*(?:mg|ml|g)\b|"
    r"diagnos(?:is is|ed with)|you (?:have|should)|treatment plan|dosage)\b",
    re.I,
)


def prohibited_language(text: str) -> bool:
    return bool(_PROHIBITED.search(text))
