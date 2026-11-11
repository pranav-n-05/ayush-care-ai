import pytest

from app.core.logging import _redact
from app.modules.audit.service import _clean
from app.modules.intake.definition import (
    DefinitionError,
    is_visible,
    parse_definition,
    validate_value,
)
from app.modules.intake.seed_definition import DEMO_DEFINITION
from app.modules.triage.engine import Outcome, evaluate


def _q(**kw):
    return {"code": "q", "type": "text", "text": {"en": "Q"}, **kw}


def _def(questions):
    return {
        "code": "t",
        "title": {"en": "T"},
        "clinical_disclaimer": "d",
        "sections": [{"code": "s", "title": {"en": "S"}, "questions": questions}],
    }


def test_demo_definition_valid():
    assert len(parse_definition(DEMO_DEFINITION).questions()) == 42


@pytest.mark.parametrize(
    "questions,msg",
    [
        ([_q(code="a"), _q(code="a")], "duplicate question"),
        ([_q(code="a", show_if={"question": "zz", "op": "is_true"})], "unknown question"),
        ([_q(code="a", type="boolean", show_if={"question": "a", "op": "is_true"})], "itself"),
        ([_q(code="a", type="single_choice")], "need options"),
        (
            [_q(code="a"), _q(code="b", show_if={"question": "a", "op": "is_true"})],
            "boolean target",
        ),
        (
            [
                {
                    **_q(code="a", type="single_choice"),
                    "options": [{"code": "x", "label": {"en": "x"}}],
                },
                _q(code="b", show_if={"question": "a", "op": "equals", "value": "nope"}),
            ],
            "not an option",
        ),
    ],
)
def test_definition_errors(questions, msg):
    with pytest.raises(DefinitionError) as e:
        parse_definition(_def(questions))
    assert msg in str(e.value)


def test_three_node_cycle_detected():
    qs = [
        _q(code=c, type="boolean", show_if={"question": n, "op": "is_true"})
        for c, n in (("a", "b"), ("b", "c"), ("c", "a"))
    ]
    with pytest.raises(DefinitionError, match="cyclic"):
        parse_definition(_def(qs))


def test_nested_visibility_requires_whole_chain():
    d = parse_definition(
        _def(
            [
                _q(code="a", type="boolean"),
                _q(code="b", type="boolean", show_if={"question": "a", "op": "is_true"}),
                _q(code="c", show_if={"question": "b", "op": "is_true"}),
            ]
        )
    )
    assert not is_visible(d, "c", {"b": ("answered", True)})  # a unanswered
    assert is_visible(d, "c", {"a": ("answered", True), "b": ("answered", True)})
    assert not is_visible(d, "b", {"a": ("unknown", None)})


def test_value_validation():
    d = parse_definition(DEMO_DEFINITION)
    q = {x.code: x for _, x in d.questions()}
    assert validate_value(q["associated_symptoms"], ["pain", "fever"]) == ["fever", "pain"]
    for code, bad in [
        ("severity", True),
        ("severity", "5"),
        ("associated_symptoms", ["pain", "pain"]),
        ("complaint_duration", {"amount": -1, "unit": "days"}),
        ("chief_complaint", "  "),
        ("onset", "never"),
        ("chest_pain", "yes"),
    ]:
        with pytest.raises(ValueError):
            validate_value(q[code], bad)


def test_triage_engine_outcomes():
    cond = {"all": [{"question": "severity", "op": "gte", "value": 9}]}
    assert evaluate(cond, {})[0] is Outcome.NOT_EVALUABLE
    assert evaluate(cond, {"severity": ("declined", None)})[0] is Outcome.NOT_EVALUABLE
    assert evaluate(cond, {"severity": ("answered", 3)})[0] is Outcome.NOT_TRIGGERED
    assert evaluate(cond, {"severity": ("answered", 9)})[0] is Outcome.TRIGGERED


def test_log_redaction_and_audit_key_guard():
    out = _redact(
        None,
        "",
        {"event": "x", "password": "p", "session_token": "t", "patient_name": "n", "count": 3},
    )
    assert out == {
        "event": "x",
        "password": "[REDACTED]",
        "session_token": "[REDACTED]",
        "patient_name": "[REDACTED]",
        "count": 3,
    }
    with pytest.raises(ValueError):
        _clean({"value": "clinical"})
