"""Pure deterministic rule evaluation. Missing or non-'answered' inputs yield NOT_EVALUABLE,
never 'no risk'."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.intake.definition import Answers, Condition, _condition_holds


class Outcome(StrEnum):
    TRIGGERED = "triggered"
    NOT_TRIGGERED = "not_triggered"
    NOT_EVALUABLE = "not_evaluable"


class RuleCondition(BaseModel):
    """All listed clauses must hold (logical AND)."""

    model_config = ConfigDict(extra="forbid")
    all: list[Condition] = Field(min_length=1, max_length=10)


def evaluate(condition: dict[str, Any], answers: Answers) -> tuple[Outcome, str | None]:
    """Returns (outcome, code of the first clause's question used as trigger reference)."""
    rule = RuleCondition.model_validate(condition)
    for clause in rule.all:
        ans = answers.get(clause.question)
        if ans is None or ans[0] != "answered":
            return Outcome.NOT_EVALUABLE, None
        if not _condition_holds(clause, ans):
            return Outcome.NOT_TRIGGERED, None
    return Outcome.TRIGGERED, rule.all[-1].question
