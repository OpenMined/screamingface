from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from scoreboard.scores.schemas import BaselineImportRow, BaselineSchema, ScoreSubmission


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
        "benchmark_id": "demo-benchmark",
        "model_name": "GPT-5.2",
        "accuracy": 0.62,
        "source": "artificial_analysis",
    }


def test_baseline_import_row_accepts_valid_payload() -> None:
    row = BaselineImportRow.model_validate(_valid_baseline_payload())

    assert row.benchmark_id == "demo-benchmark"
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


def test_baseline_import_row_rejects_javascript_source_url() -> None:
    payload = _valid_baseline_payload()
    payload["source_url"] = "javascript:alert(1)"

    try:
        BaselineImportRow.model_validate(payload)
    except ValidationError as exc:
        assert "http" in str(exc)
    else:
        raise AssertionError("expected validation error")


def test_baseline_import_row_rejects_data_uri_source_url() -> None:
    payload = _valid_baseline_payload()
    payload["source_url"] = "data:text/html,<script>alert(1)</script>"

    try:
        BaselineImportRow.model_validate(payload)
    except ValidationError as exc:
        assert "http" in str(exc)
    else:
        raise AssertionError("expected validation error")


def test_baseline_import_row_rejects_non_url_source_url() -> None:
    payload = _valid_baseline_payload()
    payload["source_url"] = "not a url"

    with pytest.raises(ValidationError):
        BaselineImportRow.model_validate(payload)


def test_baseline_import_row_accepts_https_source_url() -> None:
    payload = _valid_baseline_payload()
    payload["source_url"] = "https://artificialanalysis.ai/evaluations/humanitys-last-exam"

    row = BaselineImportRow.model_validate(payload)

    assert row.source_url == "https://artificialanalysis.ai/evaluations/humanitys-last-exam"


def test_baseline_import_row_rejects_oversized_source_url() -> None:
    payload = _valid_baseline_payload()
    payload["source_url"] = "https://example.test/" + "x" * 2048

    with pytest.raises(ValidationError):
        BaselineImportRow.model_validate(payload)


def test_baseline_import_row_accepts_metadata_within_bounds() -> None:
    payload = _valid_baseline_payload()
    payload["metadata"] = {"published_at": "2026-06-01", "nested": {"note": "ok"}}

    row = BaselineImportRow.model_validate(payload)

    assert row.metadata == {"published_at": "2026-06-01", "nested": {"note": "ok"}}


def _valid_baseline_schema_payload() -> dict[str, object]:
    return {
        "id": uuid4(),
        "benchmark_id": "demo-benchmark",
        "model_name": "GPT-5.2",
        "accuracy": 0.62,
        "source": "artificial_analysis",
        "source_url": None,
        "imported_at": datetime(2026, 7, 10, tzinfo=UTC),
        "metadata": None,
    }


def test_baseline_schema_accepts_metadata_within_bounds() -> None:
    payload = _valid_baseline_schema_payload()
    payload["metadata"] = {"published_at": "2026-06-01"}

    schema = BaselineSchema.model_validate(payload)

    assert schema.metadata == {"published_at": "2026-06-01"}


def test_baseline_schema_rejects_deeply_nested_metadata() -> None:
    payload = _valid_baseline_schema_payload()
    nested: dict[str, object] = {"v": 1}
    for _ in range(10):
        nested = {"nest": nested}
    payload["metadata"] = nested

    with pytest.raises(ValidationError):
        BaselineSchema.model_validate(payload)


def test_baseline_schema_rejects_oversized_metadata() -> None:
    payload = _valid_baseline_schema_payload()
    payload["metadata"] = {"blob": "x" * 10_000}

    with pytest.raises(ValidationError):
        BaselineSchema.model_validate(payload)


# --- OME-834: publish only the local part of a submitter's email ---


@pytest.mark.parametrize(
    ("stored", "published"),
    [
        # The request: an address must not be harvestable from the public API.
        ("trask@openmined.org", "trask"),
        ("filip.boltuzic@openmined.org", "filip.boltuzic"),
        # In authMode: disabled this field is client-supplied free text, so a value
        # that is not an address passes through rather than being mangled.
        ("tester", "tester"),
        ("", ""),
        # The domain is whatever follows the LAST "@".
        ("a@b@openmined.org", "a@b"),
        # An empty local part would render as a missing submitter, so keep the
        # original instead of emitting "".
        ("@openmined.org", "@openmined.org"),
        # OME-834 review: a BLANK local part is the dangerous case. " " is not empty,
        # so the earlier `local or value` guard let it through — and the SDK's _text
        # rejects blank-after-strip, raising LeaderboardError for the WHOLE board.
        (" @openmined.org", " @openmined.org"),
        ("\t@openmined.org", "\t@openmined.org"),
        # OME-834 review: free text containing "@" is not an address. Truncating it
        # contradicts the pass-through contract and loses meaning.
        ("Team A @ OpenMined", "Team A @ OpenMined"),
        ("me @ openmined.org", "me @ openmined.org"),
        # A domain with no dot is not a public address; leave handles alone.
        ("user@github", "user@github"),
    ],
)
def test_score_schema_publishes_only_the_local_part(stored: str, published: str) -> None:
    import json

    from scoreboard.scores.schemas import ScoreSchema

    schema = ScoreSchema(
        id=uuid4(),
        version=1,
        benchmark_id="hle",
        spec_id="spec-1",
        url4_expression="x",
        submitted_by=stored,
        submitted_at=datetime(2026, 8, 14, 12, tzinfo=UTC),
        accuracy=0.5,
        total_questions=2,
        correct_questions=1,
        ran_with_providers=["openai"],
        ran_at_local=None,
        client_name=None,
        client_version=None,
        client_platform=None,
        verified_by_openmined=True,
        metadata=None,
    )

    assert json.loads(schema.model_dump_json())["submitted_by"] == published
    # INVARIANT: only the WIRE form is trimmed. The value in memory — and therefore
    # the value written to and read from the database — keeps its domain, so
    # OpenMined can still contact and audit a submitter (OME-404).
    assert schema.submitted_by == stored


def test_a_null_submitter_stays_null() -> None:
    import json

    from scoreboard.scores.schemas import ScoreSchema

    schema = ScoreSchema(
        id=uuid4(),
        version=1,
        benchmark_id="hle",
        spec_id="spec-1",
        url4_expression="x",
        submitted_by=None,
        submitted_at=datetime(2026, 8, 14, 12, tzinfo=UTC),
        accuracy=0.5,
        total_questions=2,
        correct_questions=1,
        ran_with_providers=["openai"],
        ran_at_local=None,
        client_name=None,
        client_version=None,
        client_platform=None,
        verified_by_openmined=True,
        metadata=None,
    )

    assert json.loads(schema.model_dump_json())["submitted_by"] is None
