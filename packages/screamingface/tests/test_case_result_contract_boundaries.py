"""Case Result values and their Engine wire decoder reject ambiguous states."""

from __future__ import annotations

from typing import Any, cast

import pytest

import screamingface as sf
from screamingface._evaluation.results import (
    _case_result,
    _evidence,
    _failure,
    _failure_case_id,
    _failure_stage,
    _keys,
    _number,
    _positive_integer,
    _producer_type,
    _required,
    _sequence,
    _text,
)


def _producer() -> sf.EvidenceProducer:
    return sf.EvidenceProducer(type="model", id="provider/judge")


def _evidence_value(sequence: int = 1) -> sf.Evidence:
    return sf.Evidence(
        sequence=sequence,
        producer=_producer(),
        valid=True,
        outcome="PASS",
        raw_output=True,
    )


def _check(check_id: str = "criterion-1") -> sf.Check:
    return sf.Check(
        type="criterion",
        id=check_id,
        label="The answer is correct",
        evidence=(_evidence_value(),),
    )


def _grade() -> sf.CaseGrade:
    return sf.CaseGrade(method="rubric", score=1.0, metrics={}, checks=(_check(),))


def _failure_value() -> sf.Failure:
    return sf.Failure(stage="candidate", code="provider_error", message="provider failed")


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (
            lambda: sf.EvidenceProducer(type=cast(Any, "unsupported"), id="judge"),
            "producer type",
        ),
        (
            lambda: sf.Evidence(sequence=0, producer=_producer(), valid=True, raw_output="answer"),
            "positive integer",
        ),
        (
            lambda: sf.Evidence(
                sequence=1,
                producer=cast(Any, object()),
                valid=True,
                raw_output="answer",
            ),
            "EvidenceProducer",
        ),
        (
            lambda: sf.Evidence(
                sequence=1,
                producer=_producer(),
                valid=cast(Any, "yes"),
                raw_output="answer",
            ),
            "boolean",
        ),
        (
            lambda: sf.Evidence(
                sequence=1,
                producer=_producer(),
                valid=False,
                outcome="PASS",
                raw_output="answer",
            ),
            "invalid Evidence",
        ),
        (
            lambda: sf.Check(
                type="criterion",
                id="criterion-1",
                label="label",
                evidence=cast(Any, (object(),)),
            ),
            "sf.Evidence",
        ),
        (
            lambda: sf.Check(
                type="criterion",
                id="criterion-1",
                label="label",
                evidence=(_evidence_value(), _evidence_value()),
            ),
            "unique and ordered",
        ),
        (
            lambda: sf.CaseGrade(
                method="rubric", score=1.0, metrics={}, checks=cast(Any, (object(),))
            ),
            "sf.Check",
        ),
        (
            lambda: sf.CaseGrade(
                method="rubric",
                score=1.0,
                metrics={},
                checks=(_check(), _check()),
            ),
            "ids must be unique",
        ),
        (
            lambda: sf.CaseResult(
                case_id=0,
                input="question",
                output="answer",
                finish_reason="stop",
                grade=_grade(),
                failures=(),
                metadata={},
            ),
            "positive integer",
        ),
        (
            lambda: sf.CaseResult(
                case_id=1,
                input="question",
                output="answer",
                finish_reason="stop",
                grade=cast(Any, object()),
                failures=(),
                metadata={},
            ),
            "sf.CaseGrade",
        ),
        (
            lambda: sf.CaseResult(
                case_id=1,
                input="question",
                output="answer",
                finish_reason=None,
                grade=None,
                failures=cast(Any, (object(),)),
                metadata={},
            ),
            "sf.Failure",
        ),
        (
            lambda: sf.CaseResult(
                case_id=1,
                input="question",
                output=None,
                finish_reason=None,
                grade=None,
                failures=(),
                metadata={},
            ),
            "ungraded",
        ),
        (
            lambda: sf.CaseResult(
                case_id=1,
                input="question",
                output="answer",
                finish_reason="stop",
                grade=sf.CaseGrade(method="rubric", score=None, metrics={}, checks=(_check(),)),
                failures=(),
                metadata={},
            ),
            "unscored Case Grade",
        ),
        (
            lambda: sf.CaseResult(
                case_id=1,
                input="question",
                output="answer",
                finish_reason="stop",
                grade=_grade(),
                failures=(_failure_value(),),
                metadata={},
            ),
            "graded Case Result",
        ),
        (
            lambda: sf.Check(
                type="criterion",
                id="criterion-1",
                label="label",
                evidence=(),
                score=cast(Any, True),
            ),
            "finite number",
        ),
        (
            lambda: sf.CaseGrade(method="rubric", score=float("inf"), metrics={}, checks=()),
            "finite number",
        ),
    ],
)
def test_public_case_result_values_reject_ambiguous_state(factory: Any, message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        factory()


def test_unscored_grade_retains_checks_evidence_and_its_failure() -> None:
    evidence = sf.Evidence(
        sequence=1,
        producer=_producer(),
        valid=False,
        raw_output="not json",
        metadata={"rejection_reason": "invalid_json"},
    )
    failure = sf.Failure(
        stage="grading",
        code="no_valid_judge_verdict",
        message="no valid Judge verdict was produced",
        case_id=1,
    )

    result = sf.CaseResult(
        case_id=1,
        input="question",
        output="answer",
        finish_reason="stop",
        grade=sf.CaseGrade(
            method="rubric",
            score=None,
            metrics={"verdicts_invalid": 1},
            checks=(
                sf.Check(
                    type="criterion",
                    id="criterion-1",
                    label="The answer is correct",
                    evidence=(evidence,),
                ),
            ),
        ),
        failures=(failure,),
        metadata={},
    )

    assert result.grade is not None
    assert result.grade.score is None
    assert result.grade.checks[0].evidence[0].valid is False
    assert result.failures == (failure,)


def test_wire_failure_decoder_accepts_each_stage_and_case_id_shape() -> None:
    decoded = tuple(
        _failure(
            {
                "stage": stage,
                "code": "provider_error",
                "message": "provider failed",
                "retryable": False,
                "operation_id": "op_1",
                "case_id": case_id,
                "metadata": {},
            }
        )
        for stage, case_id in (
            ("candidate", None),
            ("grading", "case-one"),
            ("aggregation", 1),
        )
    )

    assert tuple(item.stage for item in decoded) == ("candidate", "grading", "aggregation")
    assert tuple(item.case_id for item in decoded) == (None, "case-one", 1)


def test_wire_evidence_decoder_accepts_a_deterministic_producer() -> None:
    evidence = _evidence(
        {
            "sequence": 1,
            "producer": {"type": "deterministic", "id": "benchmark/official-verifier"},
            "valid": True,
            "raw_output": True,
            "metadata": {},
        }
    )

    assert evidence.producer.type == "deterministic"


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: _sequence("not-an-array", "Items"), "must be an array"),
        (lambda: _required({}, "answer", "Record"), "missing 'answer'"),
        (
            lambda: _keys({}, required={"answer"}, label="Record"),
            "missing 'answer'",
        ),
        (
            lambda: _keys({"answer": "yes", "extra": True}, required={"answer"}, label="Record"),
            "unsupported field 'extra'",
        ),
        (lambda: _positive_integer(True, "sequence"), "positive integer"),
        (lambda: _text(" ", "label"), "non-empty text"),
        (lambda: _number(True, "score"), "must be numeric"),
        (lambda: _producer_type("unsupported"), "producer type is unsupported"),
        (lambda: _failure_stage("planning"), "Failure stage is unsupported"),
        (lambda: _failure_case_id(True), "case_id must be"),
        (
            lambda: _evidence(
                {
                    "sequence": 1,
                    "producer": {"type": "model", "id": "provider/judge"},
                    "valid": "yes",
                    "raw_output": "answer",
                    "metadata": {},
                }
            ),
            "valid must be boolean",
        ),
        (
            lambda: _failure(
                {
                    "stage": "candidate",
                    "code": "provider_error",
                    "message": "provider failed",
                    "retryable": "yes",
                }
            ),
            "retryable must be boolean or null",
        ),
    ],
)
def test_wire_case_result_decoder_rejects_ambiguous_values(factory: Any, message: str) -> None:
    with pytest.raises(sf.ExecutionError, match=message):
        factory()


def test_wire_case_result_rejects_a_failure_owned_by_another_case() -> None:
    with pytest.raises(sf.ExecutionError, match="another Case"):
        _case_result(
            {
                "status": "failed",
                "case_id": 1,
                "input": "question",
                "output": None,
                "finish_reason": None,
                "refusal": None,
                "grade": None,
                "failures": [
                    {
                        "stage": "candidate",
                        "code": "provider_error",
                        "message": "provider failed",
                        "case_id": 2,
                    }
                ],
                "metadata": {},
            }
        )
