"""Questionnaire definition schema, structural validation and answer validation.

Pure functions, no database access, so the engine is unit-testable in isolation.
"""

import datetime as dt
import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

LANGS = ("en", "hi", "ta")
AnswerType = Literal[
    "text", "long_text", "single_choice", "multi_choice", "boolean", "number", "date", "duration"
]
DURATION_UNITS = ("days", "weeks", "months", "years")


class Localized(BaseModel):
    """English is mandatory. Hindi/Tamil strings are optional DRAFTS that require linguistic
    and practitioner review; missing languages fall back to English and are flagged."""

    model_config = ConfigDict(extra="forbid")
    en: str = Field(min_length=1, max_length=500)
    hi: str | None = Field(None, max_length=500)
    ta: str | None = Field(None, max_length=500)

    def render(self, lang: str) -> tuple[str, bool]:
        value = getattr(self, lang, None)
        return (value, False) if value else (self.en, lang != "en")


class Option(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^[a-z0-9_]{1,60}$")
    label: Localized


class Condition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str
    op: Literal["equals", "in", "is_true", "is_false", "gte", "lte", "contains"]
    value: Any = None


class QuestionDef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^[a-z0-9_]{1,80}$")
    type: AnswerType
    text: Localized
    help: Localized | None = None
    required: bool = False
    respondent: Literal["patient", "practitioner"] = "patient"
    options: list[Option] | None = None
    min: float | None = None
    max: float | None = None
    unit: str | None = None
    show_if: Condition | None = None

    @model_validator(mode="after")
    def _shape(self) -> "QuestionDef":
        choice = self.type in ("single_choice", "multi_choice")
        if choice and not self.options:
            raise ValueError(f"{self.code}: choice questions need options")
        if not choice and self.options:
            raise ValueError(f"{self.code}: only choice questions may define options")
        if self.options and len({o.code for o in self.options}) != len(self.options):
            raise ValueError(f"{self.code}: duplicate option codes")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"{self.code}: min > max")
        return self


class SectionDef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^[a-z0-9_]{1,80}$")
    title: Localized
    questions: list[QuestionDef] = Field(min_length=1)


class QuestionnaireDef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^[a-z0-9_]{1,80}$")
    title: Localized
    clinical_disclaimer: str
    sections: list[SectionDef] = Field(min_length=1)

    def questions(self) -> list[tuple[SectionDef, QuestionDef]]:
        return [(s, q) for s in self.sections for q in s.questions]


class DefinitionError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


def parse_definition(raw: dict[str, Any]) -> QuestionnaireDef:
    try:
        definition = QuestionnaireDef.model_validate(raw)
    except ValidationError as exc:
        raise DefinitionError(
            [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]
        ) from exc
    errors: list[str] = []
    by_code: dict[str, QuestionDef] = {}
    for _, q in definition.questions():
        if q.code in by_code:
            errors.append(f"duplicate question code: {q.code}")
        by_code[q.code] = q
    if len({s.code for s in definition.sections}) != len(definition.sections):
        errors.append("duplicate section codes")
    for q in by_code.values():
        cond = q.show_if
        if cond is None:
            continue
        target = by_code.get(cond.question)
        if target is None:
            errors.append(f"{q.code}: show_if references unknown question {cond.question}")
            continue
        if cond.question == q.code:
            errors.append(f"{q.code}: show_if references itself")
        if cond.op in ("is_true", "is_false") and target.type != "boolean":
            errors.append(f"{q.code}: {cond.op} requires a boolean target")
        if cond.op in ("equals", "in", "contains") and target.options:
            codes = {o.code for o in target.options}
            vals = cond.value if isinstance(cond.value, list) else [cond.value]
            if any(v not in codes for v in vals):
                errors.append(f"{q.code}: show_if value is not an option of {cond.question}")
        if cond.op in ("gte", "lte") and target.type != "number":
            errors.append(f"{q.code}: {cond.op} requires a number target")
    errors.extend(_find_cycles(by_code))
    if errors:
        raise DefinitionError(errors)
    return definition


def _find_cycles(by_code: dict[str, QuestionDef]) -> list[str]:
    white, grey, black = 0, 1, 2
    color = dict.fromkeys(by_code, white)
    errors: list[str] = []

    def visit(code: str, path: list[str]) -> None:
        color[code] = grey
        cond = by_code[code].show_if
        nxt = cond.question if cond else None
        if nxt in by_code:
            if color[nxt] == grey:
                cycle = path[path.index(nxt) :] + [nxt] if nxt in path else [code, nxt]
                errors.append("cyclic show_if dependency: " + " -> ".join(cycle))
            elif color[nxt] == white:
                visit(nxt, path + [nxt])
        color[code] = black

    for code in by_code:
        if color[code] == white:
            visit(code, [code])
    return errors


def checksum(raw: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(raw, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


# ---------------- runtime evaluation ----------------

# current answers: code -> (answer_status, value)
Answers = dict[str, tuple[str, Any]]


def _condition_holds(cond: Condition, answer: tuple[str, Any] | None) -> bool:
    if answer is None or answer[0] != "answered":
        return False  # unknown/declined/not answered never satisfies a branch condition
    value = answer[1]
    match cond.op:
        case "equals":
            return bool(value == cond.value)
        case "in":
            return value in (cond.value or [])
        case "contains":
            return isinstance(value, list) and cond.value in value
        case "is_true":
            return value is True
        case "is_false":
            return value is False
        case "gte":
            return isinstance(value, int | float) and value >= cond.value
        case "lte":
            return isinstance(value, int | float) and value <= cond.value
    return False


def is_visible(definition: QuestionnaireDef, code: str, answers: Answers) -> bool:
    by_code = {q.code: q for _, q in definition.questions()}
    q = by_code[code]
    seen: set[str] = set()
    while q.show_if is not None:
        if q.code in seen:  # defensive; parse_definition rejects cycles
            return False
        seen.add(q.code)
        if not _condition_holds(q.show_if, answers.get(q.show_if.question)):
            return False
        q = by_code[q.show_if.question]
    return True


def validate_value(q: QuestionDef, value: Any) -> Any:
    """Returns the normalized value or raises ValueError with a user-safe message."""
    t = q.type
    if t in ("text", "long_text"):
        limit = 2000 if t == "text" else 10000
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Expected non-empty text")
        if len(value) > limit:
            raise ValueError(f"Text exceeds {limit} characters")
        return value.strip()
    if t == "boolean":
        if not isinstance(value, bool):
            raise ValueError("Expected true or false")
        return value
    if t == "number":
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError("Expected a number")
        if q.min is not None and value < q.min or q.max is not None and value > q.max:
            raise ValueError(f"Number must be between {q.min} and {q.max}")
        return value
    if t == "single_choice":
        codes = {o.code for o in q.options or []}
        if value not in codes:
            raise ValueError("Not a valid option")
        return value
    if t == "multi_choice":
        codes = {o.code for o in q.options or []}
        if not isinstance(value, list) or not value or len(set(value)) != len(value):
            raise ValueError("Expected a non-empty list of distinct options")
        if any(v not in codes for v in value):
            raise ValueError("Contains an invalid option")
        return sorted(value)
    if t == "date":
        try:
            d = dt.date.fromisoformat(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("Expected an ISO date (YYYY-MM-DD)") from exc
        if d > dt.date.today():
            raise ValueError("Date cannot be in the future")
        return d.isoformat()
    if t == "duration":
        if not isinstance(value, dict) or set(value) != {"amount", "unit"}:
            raise ValueError("Expected {amount, unit}")
        amount, unit = value["amount"], value["unit"]
        if isinstance(amount, bool) or not isinstance(amount, int | float) or amount <= 0:
            raise ValueError("Duration amount must be positive")
        if unit not in DURATION_UNITS:
            raise ValueError("Duration unit must be days, weeks, months or years")
        return {"amount": amount, "unit": unit}
    raise ValueError("Unsupported question type")
