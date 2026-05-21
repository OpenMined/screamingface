from __future__ import annotations

from pydantic import ValidationError

from scoreboard.scores.schemas import ScoreSubmission


def _valid_payload() -> dict[str, object]:
    return {
        "benchmark_id": "hle",
        "spec_id": "spec-1",
        "url4_expression": "url4://benchmark/spec-1",
        "accuracy": 0.75,
        "total_questions": 4,
        "correct_questions": 3,
        "ran_with_providers": ["openai"],
    }


def test_score_submission_accepts_valid_payload() -> None:
    submission = ScoreSubmission.model_validate(_valid_payload())

    assert submission.version == 1
    assert submission.benchmark_id == "hle"
    assert submission.ran_with_providers == ["openai"]


def test_score_submission_rejects_accuracy_below_zero() -> None:
    payload = _valid_payload()
    payload["accuracy"] = -0.01

    try:
        ScoreSubmission.model_validate(payload)
    except ValidationError as exc:
        assert "accuracy must be between 0 and 1" in str(exc)
    else:
        raise AssertionError("expected validation error")


def test_score_submission_rejects_accuracy_above_one() -> None:
    payload = _valid_payload()
    payload["accuracy"] = 1.01

    try:
        ScoreSubmission.model_validate(payload)
    except ValidationError as exc:
        assert "accuracy must be between 0 and 1" in str(exc)
    else:
        raise AssertionError("expected validation error")


def test_score_submission_rejects_non_positive_total_questions() -> None:
    payload = _valid_payload()
    payload["total_questions"] = 0

    try:
        ScoreSubmission.model_validate(payload)
    except ValidationError as exc:
        assert "total_questions must be positive" in str(exc)
    else:
        raise AssertionError("expected validation error")


def test_score_submission_rejects_negative_correct_questions() -> None:
    payload = _valid_payload()
    payload["correct_questions"] = -1

    try:
        ScoreSubmission.model_validate(payload)
    except ValidationError as exc:
        assert "correct_questions must be non-negative" in str(exc)
    else:
        raise AssertionError("expected validation error")


def test_score_submission_rejects_correct_questions_above_total() -> None:
    payload = _valid_payload()
    payload["correct_questions"] = 5

    try:
        ScoreSubmission.model_validate(payload)
    except ValidationError as exc:
        assert "correct_questions cannot exceed total_questions" in str(exc)
    else:
        raise AssertionError("expected validation error")
