from __future__ import annotations

import pytest
from pydantic import ValidationError

from scoreboard.scores.schemas import BaselineImportRow, ScoreSubmission


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


def _valid_baseline_payload() -> dict[str, object]:
    return {
        "benchmark_id": "hle",
        "model_name": "GPT-5.2",
        "accuracy": 0.62,
        "source": "artificial_analysis",
    }


def test_baseline_import_row_accepts_valid_payload() -> None:
    row = BaselineImportRow.model_validate(_valid_baseline_payload())

    assert row.benchmark_id == "hle"
    assert row.model_name == "GPT-5.2"
    assert row.source_url is None
    assert row.metadata is None


def test_baseline_import_row_accepts_optional_source_url_and_metadata() -> None:
    payload = _valid_baseline_payload()
    payload["source_url"] = "https://artificialanalysis.ai/benchmarks/hle"
    payload["metadata"] = {"published_at": "2026-06-01"}

    row = BaselineImportRow.model_validate(payload)

    assert row.source_url == "https://artificialanalysis.ai/benchmarks/hle"
    assert row.metadata == {"published_at": "2026-06-01"}


def test_baseline_import_row_rejects_empty_benchmark_id() -> None:
    payload = _valid_baseline_payload()
    payload["benchmark_id"] = ""

    try:
        BaselineImportRow.model_validate(payload)
    except ValidationError as exc:
        assert "identifier fields must be non-empty" in str(exc)
    else:
        raise AssertionError("expected validation error")


def test_baseline_import_row_rejects_empty_model_name() -> None:
    payload = _valid_baseline_payload()
    payload["model_name"] = ""

    try:
        BaselineImportRow.model_validate(payload)
    except ValidationError as exc:
        assert "identifier fields must be non-empty" in str(exc)
    else:
        raise AssertionError("expected validation error")


def test_baseline_import_row_rejects_empty_source() -> None:
    payload = _valid_baseline_payload()
    payload["source"] = ""

    try:
        BaselineImportRow.model_validate(payload)
    except ValidationError as exc:
        assert "identifier fields must be non-empty" in str(exc)
    else:
        raise AssertionError("expected validation error")


def test_baseline_import_row_rejects_accuracy_below_zero() -> None:
    payload = _valid_baseline_payload()
    payload["accuracy"] = -0.01

    try:
        BaselineImportRow.model_validate(payload)
    except ValidationError as exc:
        assert "accuracy must be between 0 and 1" in str(exc)
    else:
        raise AssertionError("expected validation error")


def test_baseline_import_row_rejects_accuracy_above_one() -> None:
    payload = _valid_baseline_payload()
    payload["accuracy"] = 1.01

    try:
        BaselineImportRow.model_validate(payload)
    except ValidationError as exc:
        assert "accuracy must be between 0 and 1" in str(exc)
    else:
        raise AssertionError("expected validation error")


def test_baseline_import_row_rejects_unknown_fields() -> None:
    payload = _valid_baseline_payload()
    payload["extra_field"] = "not allowed"

    try:
        BaselineImportRow.model_validate(payload)
    except ValidationError as exc:
        assert "extra_field" in str(exc)
    else:
        raise AssertionError("expected validation error")


def test_baseline_import_row_rejects_bool_accuracy() -> None:
    payload = _valid_baseline_payload()
    payload["accuracy"] = True

    with pytest.raises(ValidationError):
        BaselineImportRow.model_validate(payload)


def test_baseline_import_row_rejects_numeric_string_accuracy() -> None:
    payload = _valid_baseline_payload()
    payload["accuracy"] = "0.62"

    with pytest.raises(ValidationError):
        BaselineImportRow.model_validate(payload)


def test_baseline_import_row_rejects_non_finite_accuracy() -> None:
    payload = _valid_baseline_payload()
    payload["accuracy"] = float("nan")

    with pytest.raises(ValidationError):
        BaselineImportRow.model_validate(payload)


def test_baseline_import_row_still_accepts_plain_float_accuracy() -> None:
    payload = _valid_baseline_payload()
    payload["accuracy"] = 0.71

    row = BaselineImportRow.model_validate(payload)

    assert row.accuracy == 0.71


def test_baseline_import_row_rejects_deeply_nested_metadata() -> None:
    payload = _valid_baseline_payload()
    nested: dict[str, object] = {"v": 1}
    for _ in range(10):
        nested = {"nest": nested}
    payload["metadata"] = nested

    try:
        BaselineImportRow.model_validate(payload)
    except ValidationError as exc:
        assert "nested" in str(exc)
    else:
        raise AssertionError("expected validation error")


def test_baseline_import_row_rejects_oversized_metadata() -> None:
    payload = _valid_baseline_payload()
    payload["metadata"] = {"blob": "x" * 10_000}

    try:
        BaselineImportRow.model_validate(payload)
    except ValidationError as exc:
        assert "bytes" in str(exc)
    else:
        raise AssertionError("expected validation error")


def test_baseline_import_row_accepts_metadata_within_bounds() -> None:
    payload = _valid_baseline_payload()
    payload["metadata"] = {"published_at": "2026-06-01", "nested": {"note": "ok"}}

    row = BaselineImportRow.model_validate(payload)

    assert row.metadata == {"published_at": "2026-06-01", "nested": {"note": "ok"}}
