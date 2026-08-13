"""The client decodes the explicit Case outcome the OME-802 Engine publishes.

INVARIANT defended: the `screamingface.candidate-result.v1` Case Result carries
`status` (scored | refused | failed) and `refusal` on every Case — the client
decodes them strictly (unknown keys and unknown statuses still fail loudly) and
exposes them unmodified, never recalculating Benchmark semantics client-side.
"""

from __future__ import annotations

from typing import Any

import pytest

import screamingface as sf
from screamingface._evaluation.results import _case_result


def _scored_payload() -> dict[str, Any]:
    return {
        "status": "scored",
        "case_id": 1,
        "input": "What is two plus two?",
        "output": "Four.",
        "finish_reason": "stop",
        "refusal": None,
        "grade": {"method": "rubric", "score": 1.0, "metrics": {}, "checks": []},
        "failures": [],
        "metadata": {},
    }


def _refused_payload() -> dict[str, Any]:
    return {
        "status": "refused",
        "case_id": 1,
        "input": "A clinical question",
        "output": None,
        "finish_reason": "stop",
        "refusal": "I can't help with that request.",
        "grade": None,
        "failures": [
            {
                "stage": "candidate",
                "code": "provider_refusal",
                "message": "the provider refused this Case",
                "retryable": None,
                "case_id": 1,
                "metadata": {},
            }
        ],
        "metadata": {},
    }


def _failed_payload() -> dict[str, Any]:
    return {
        "status": "failed",
        "case_id": 1,
        "input": "A question",
        "output": None,
        "finish_reason": None,
        "refusal": None,
        "grade": None,
        "failures": [
            {
                "stage": "candidate",
                "code": "provider_error",
                "message": "the provider failed",
                "retryable": True,
                "case_id": 1,
                "metadata": {},
            }
        ],
        "metadata": {},
    }


@pytest.mark.parametrize(
    ("payload", "status", "refusal"),
    [
        (_scored_payload(), "scored", None),
        (_refused_payload(), "refused", "I can't help with that request."),
        (_failed_payload(), "failed", None),
    ],
)
def test_every_wire_status_decodes_and_is_exposed_unmodified(
    payload: dict[str, Any], status: str, refusal: str | None
) -> None:
    case = _case_result(payload)

    assert case.status == status
    assert case.refusal == refusal


def test_decoded_outcome_survives_export() -> None:
    exported = _case_result(_refused_payload()).to_dict()

    assert exported["status"] == "refused"
    assert exported["refusal"] == "I can't help with that request."


@pytest.mark.parametrize("key", ["status", "refusal"])
def test_a_case_missing_a_contract_key_is_rejected(key: str) -> None:
    payload = {name: value for name, value in _scored_payload().items() if name != key}

    with pytest.raises(sf.ExecutionError, match=f"missing '{key}'"):
        _case_result(payload)


def test_an_unknown_case_key_is_still_rejected() -> None:
    with pytest.raises(sf.ExecutionError, match="unsupported field 'unexpected'"):
        _case_result({**_scored_payload(), "unexpected": True})


def test_an_unsupported_status_is_rejected() -> None:
    with pytest.raises(sf.ExecutionError, match="status is unsupported"):
        _case_result({**_scored_payload(), "status": "skipped"})


def test_blank_refusal_text_is_rejected() -> None:
    with pytest.raises(sf.ExecutionError, match="refusal"):
        _case_result({**_refused_payload(), "refusal": "   "})


def test_a_status_contradicting_the_grade_shape_is_rejected() -> None:
    with pytest.raises(ValueError, match="status"):
        sf.CaseResult(
            status="failed",
            case_id=1,
            input="question",
            output="answer",
            finish_reason="stop",
            grade=sf.CaseGrade(method="rubric", score=1.0, metrics={}, checks=()),
            failures=(),
            metadata={},
        )


def test_a_scored_case_cannot_carry_refusal_text() -> None:
    with pytest.raises(ValueError, match="refusal"):
        sf.CaseResult(
            case_id=1,
            input="question",
            output="answer",
            finish_reason="stop",
            refusal="I refuse.",
            grade=sf.CaseGrade(method="rubric", score=1.0, metrics={}, checks=()),
            failures=(),
            metadata={},
        )


def test_a_refused_case_cannot_carry_output() -> None:
    # INVARIANT: mirrors contract.py _enforce_status — a refused Case has no output,
    # so a locally built value can never round-trip into a contract-invalid payload.
    with pytest.raises(ValueError, match="refused"):
        sf.CaseResult(
            case_id=1,
            input="question",
            output="an answer the engine would reject",
            finish_reason="stop",
            refusal="I can't help with that request.",
            grade=None,
            failures=(
                sf.Failure(
                    stage="candidate",
                    code="provider_refusal",
                    message="the provider refused this Case",
                    case_id=1,
                ),
            ),
            metadata={},
        )


def test_a_refused_case_cannot_carry_a_grade() -> None:
    # INVARIANT: mirrors contract.py _enforce_status — refusal text alongside a grade
    # (even an unscored one) is a shape the engine rejects outright.
    with pytest.raises(ValueError, match="refused"):
        sf.CaseResult(
            case_id=1,
            input="question",
            output=None,
            finish_reason="stop",
            refusal="I can't help with that request.",
            grade=sf.CaseGrade(method="rubric", score=None, metrics={}, checks=()),
            failures=(
                sf.Failure(
                    stage="candidate",
                    code="provider_refusal",
                    message="the provider refused this Case",
                    case_id=1,
                ),
            ),
            metadata={},
        )


def test_a_locally_built_case_derives_the_status_the_engine_would_publish() -> None:
    refused = sf.CaseResult(
        case_id=1,
        input="question",
        output=None,
        finish_reason=None,
        refusal="I can't help with that request.",
        grade=None,
        failures=(
            sf.Failure(
                stage="candidate",
                code="provider_refusal",
                message="the provider refused this Case",
                case_id=1,
            ),
        ),
        metadata={},
    )

    assert refused.status == "refused"
