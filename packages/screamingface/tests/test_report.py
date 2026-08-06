from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

import screamingface as sf
from screamingface._evaluation.model import _compiled_operation


def case_results() -> tuple[sf.CaseResult, ...]:
    return tuple(
        sf.CaseResult(
            case_id=case_id,
            input=f"Question {case_id}",
            output=f"Answer {case_id}",
            finish_reason="stop",
            grade=sf.CaseGrade(method="fixture", score=1.0, metrics={}, checks=()),
            failures=(),
            metadata={},
        )
        for case_id in (1, 2)
    )


def candidate(
    name: str,
    *,
    url4: str | None = None,
    score: float | None = 0.5,
    failures: tuple[sf.Failure, ...] = (),
    usage: sf.Usage | None = None,
) -> sf.CandidateResult:
    metrics = {} if score is None else {"coverage": 1.0}
    return sf.CandidateResult(
        run_id=f"run_{name}",
        started_at=datetime(2026, 7, 25, 16, 0, tzinfo=UTC),
        completed_at=datetime(2026, 7, 25, 16, 0, 1, 200000, tzinfo=UTC),
        name=name,
        kind="model",
        url4=url4 or f"(@)!'{name}'",
        models=(f"provider/{name}",),
        operations=(
            _compiled_operation(
                id=f"op_{name}",
                kind="model",
                label=f"{name} answer",
                depends_on=(),
            ),
            _compiled_operation(
                id=f"op_{name}_aggregate",
                kind="aggregation",
                label=f"{name} aggregation",
                depends_on=(f"op_{name}",),
            ),
        ),
        score=score,
        metrics=metrics,
        cases=case_results(),
        members=(),
        failures=failures,
        usage=usage or sf.Usage(input_tokens=100, output_tokens=20, cost_usd="0.12"),
    )


def report(*candidates: sf.CandidateResult) -> sf.Report:
    return sf.Report(
        benchmark=sf.BenchmarkInfo(
            id="draco@1",
            revision="fixture-revision",
            case_count=100,
        ),
        case_count=2,
        candidates=candidates,
    )


def test_report_has_one_ordered_candidate_collection_for_one_or_many_candidates() -> None:
    opus = candidate("opus")
    gpt = candidate("gpt")
    value = report(opus, gpt)

    assert tuple(value.candidates) == (opus, gpt)
    assert value.candidates[0] is opus
    assert value.candidates[-1] is gpt
    assert value.candidates["gpt"] is gpt
    assert value.candidates == (opus, gpt)
    assert repr(value.candidates).startswith("(")
    assert value.duration_ms == 1200

    with pytest.raises(ValueError, match="exactly one"):
        _ = value.candidates.only


def test_report_reuses_public_benchmark_info_and_records_the_selected_case_count() -> None:
    benchmark = sf.BenchmarkInfo(
        id="draco@1",
        revision="fixture-revision",
        case_count=100,
    )

    value = sf.Report(
        benchmark=benchmark,
        case_count=2,
        candidates=(candidate("opus"),),
    )

    assert value.benchmark is benchmark
    assert value.case_count == 2
    assert value.to_dict()["benchmark"] == {
        "id": "draco@1",
        "revision": "fixture-revision",
        "case_count": 2,
    }


def test_only_returns_the_single_candidate() -> None:
    opus = candidate("opus")

    assert report(opus).candidates.only is opus


def test_candidate_result_preserves_its_operation_map_in_portable_json() -> None:
    opus = candidate("opus")

    assert tuple(operation.id for operation in opus.operations) == (
        "op_opus",
        "op_opus_aggregate",
    )
    assert opus.to_dict()["operations"] == [
        {
            "id": "op_opus",
            "kind": "model",
            "label": "opus answer",
            "depends_on": [],
        },
        {
            "id": "op_opus_aggregate",
            "kind": "aggregation",
            "label": "opus aggregation",
            "depends_on": ["op_opus"],
        },
    ]


def test_candidate_result_rejects_a_non_url4_workflow() -> None:
    with pytest.raises(ValueError, match="Candidate URL4"):
        candidate("opus", url4="not a URL4 expression")


def test_report_derives_study_timing_and_complete_usage_from_candidate_runs() -> None:
    opus = candidate("opus")
    gpt = sf.CandidateResult(
        run_id="run_gpt",
        started_at=datetime(2026, 7, 25, 15, 59, 59, tzinfo=UTC),
        completed_at=datetime(2026, 7, 25, 16, 0, 3, tzinfo=UTC),
        name="gpt",
        kind="model",
        url4="(@)!'gpt'",
        models=("provider/gpt",),
        operations=(
            _compiled_operation(
                id="op_gpt",
                kind="model",
                label="gpt answer",
                depends_on=(),
            ),
        ),
        score=0.5,
        metrics={"coverage": 1.0},
        cases=case_results(),
        members=(),
        failures=(),
        usage=sf.Usage(input_tokens=50, output_tokens=None, cost_usd="0.03"),
    )

    value = report(opus, gpt)

    assert value.started_at == gpt.started_at
    assert value.completed_at == gpt.completed_at
    assert value.duration_ms == 4000
    assert value.usage.input_tokens == 150
    assert value.usage.output_tokens is None
    assert value.usage.cost_usd == Decimal("0.15")
    assert not hasattr(value, "run_id")
    assert not hasattr(value, "url4")


def test_report_flattens_candidate_failures_without_duplicating_them_on_the_wire() -> None:
    owned = sf.Failure(
        stage="candidate",
        code="gateway_timeout",
        message="The model timed out.",
        retryable=True,
        operation_id="op_opus",
        case_id="case-2",
    )
    value = report(candidate("opus", score=None, failures=(owned,)))

    assert value.ok is False
    assert value.failures == (owned,)
    payload = value.to_dict()
    candidates = payload["candidates"]
    assert isinstance(candidates, list)
    candidate_payload = candidates[0]
    assert isinstance(candidate_payload, dict)
    assert "failures" not in payload
    assert candidate_payload["failures"] == [owned.to_dict()]


def test_failure_serializes_the_locked_domain_contract() -> None:
    failure = sf.Failure(
        stage="grading",
        code="judge_invalid_response",
        message="The judge returned an invalid verdict.",
        retryable=True,
        operation_id="op_grade_1",
        case_id="case-42",
    )

    assert failure.to_dict() == {
        "stage": "grading",
        "code": "judge_invalid_response",
        "message": "The judge returned an invalid verdict.",
        "retryable": True,
        "operation_id": "op_grade_1",
        "case_id": "case-42",
    }


def test_scored_fusion_preserves_partial_member_failure_evidence() -> None:
    member_failure = sf.Failure(
        stage="candidate",
        code="gateway_timeout",
        message="One panel member timed out.",
        retryable=True,
        operation_id="op_panel_2",
        case_id="case-2",
    )
    value = sf.CandidateResult(
        run_id="run_frontier_pair",
        started_at=datetime(2026, 7, 25, 16, 0, tzinfo=UTC),
        completed_at=datetime(2026, 7, 25, 16, 0, 2, tzinfo=UTC),
        name="frontier-pair",
        kind="fusion",
        url4="(@)!'frontier pair'",
        models=("provider/opus", "provider/gpt"),
        operations=(
            _compiled_operation(
                id="op_opus",
                kind="model",
                label="opus answer",
                depends_on=(),
            ),
            _compiled_operation(
                id="op_gpt",
                kind="model",
                label="gpt answer",
                depends_on=(),
            ),
            _compiled_operation(
                id="op_panel_2",
                kind="model_call",
                label="gpt failed attempt",
                depends_on=("op_gpt",),
            ),
            _compiled_operation(
                id="op_synthesis",
                kind="synthesis",
                label="frontier pair synthesis",
                depends_on=("op_opus", "op_gpt"),
            ),
        ),
        score=0.6,
        metrics={"coverage": 1.0},
        cases=case_results(),
        members=(
            sf.MemberResult(
                operation_id="op_opus",
                name="opus",
                kind="model",
                models=("provider/opus",),
                failures=(),
                duration_ms=1200,
                usage=sf.Usage(input_tokens=100, output_tokens=20, cost_usd="0.12"),
            ),
            sf.MemberResult(
                operation_id="op_gpt",
                name="gpt",
                kind="model",
                models=("provider/gpt",),
                failures=(member_failure,),
                duration_ms=2000,
                usage=sf.Usage(input_tokens=100, output_tokens=0, cost_usd="0.03"),
            ),
        ),
        failures=(),
        usage=sf.Usage(input_tokens=200, output_tokens=20, cost_usd="0.15"),
    )

    result = report(value)

    assert result.candidates.only.score == 0.6
    assert result.failures == (member_failure,)
    assert result.ok is False
    payload = result.to_dict()
    candidates = payload["candidates"]
    assert isinstance(candidates, list)
    candidate_payload = candidates[0]
    assert isinstance(candidate_payload, dict)
    members = candidate_payload["members"]
    assert isinstance(members, list)
    failed_member = members[1]
    assert isinstance(failed_member, dict)
    assert failed_member["operation_id"] == "op_gpt"
    assert failed_member["failures"] == [member_failure.to_dict()]


def test_report_json_is_complete_portable_json_with_decimal_money_as_text() -> None:
    value = report(candidate("opus"))

    payload = json.loads(value.to_json())

    assert payload["schema"] == "screamingface.report.v1"
    assert payload["benchmark"]["id"] == "draco@1"
    assert payload["candidates"][0]["run_id"] == "run_opus"
    assert payload["candidates"][0]["name"] == "opus"
    assert payload["usage"]["cost_usd"] == "0.12"
    assert "ok" not in payload


def test_report_json_marks_unavailable_usage_fields_as_null() -> None:
    value = report(candidate("opus", usage=sf.Usage(input_tokens=100, output_tokens=20)))

    payload = json.loads(value.to_json())

    assert payload["usage"] == {
        "input_tokens": 100,
        "output_tokens": 20,
        "cache_read_tokens": None,
        "cache_creation_tokens": None,
        "reasoning_tokens": None,
        "cost_usd": None,
    }


def test_report_treats_metrics_as_diagnostics_not_a_second_score() -> None:
    value = candidate("opus")
    inconsistent = sf.CandidateResult(
        run_id=value.run_id,
        started_at=value.started_at,
        completed_at=value.completed_at,
        name=value.name,
        kind=value.kind,
        url4=value.url4,
        models=value.models,
        operations=value.operations,
        score=0.7,
        metrics={"coverage": 0.6},
        cases=value.cases,
        members=(),
        failures=(),
        usage=sf.Usage(),
    )

    result = report(inconsistent)

    assert result.candidates.only.score == 0.7
    assert result.candidates.only.metrics == {"coverage": 0.6}


def test_candidate_names_must_be_unique() -> None:
    with pytest.raises(ValueError, match="duplicate Candidate name"):
        report(candidate("opus"), candidate("opus"))


@pytest.mark.parametrize("cost", ["nan", "-0.1", "Infinity"])
def test_usage_rejects_invalid_cost(cost: str) -> None:
    with pytest.raises(ValueError, match="cost_usd"):
        sf.Usage(cost_usd=cost)


def test_report_representation_is_a_compact_run_summary() -> None:
    value = report(candidate("opus"), candidate("gpt"))

    assert repr(value) == ("Report(benchmark='draco@1', candidates=['opus', 'gpt'], ok=True)")
