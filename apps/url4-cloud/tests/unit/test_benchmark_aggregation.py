"""The generic finalizer owns cross-Benchmark score publication policy."""

from __future__ import annotations

import json
from collections.abc import Sequence

import pytest

from url4 import RelExpr, Text, expr, iterate, render, src
from url4.peer.server import Request, Url4Node
from url4_cloud.benchmarks.aggregation import (
    CandidateScore,
    SelectedCase,
    collected_provider_refusal,
    failed_case_result,
    finalize_candidate_result,
    public_error,
    refused_case_result,
    scored_case_result,
)
from url4_cloud.benchmarks.contract import CaseGrade, CaseResult, Failure
from url4_cloud.benchmarks.errors import ProviderRefusal


def _scored(case_id: int) -> CaseResult:
    return CaseResult(
        status="scored",
        case_id=case_id,
        input=f"input {case_id}",
        output=f"output {case_id}",
        finish_reason="stop",
        refusal=None,
        grade=CaseGrade(method="test", score=1.0, metrics={}, checks=[]),
        failures=[],
        metadata={},
    )


def _failed(case_id: int) -> CaseResult:
    return CaseResult(
        status="failed",
        case_id=case_id,
        input=f"input {case_id}",
        output=None,
        finish_reason=None,
        refusal=None,
        grade=None,
        failures=[
            Failure(
                stage="candidate",
                code="candidate_failed",
                message="Candidate execution failed",
                retryable=True,
                case_id=case_id,
                metadata={},
            )
        ],
        metadata={},
    )


def _selected(*case_ids: int) -> list[SelectedCase]:
    return [
        SelectedCase(case_id=case_id, input=f"input {case_id}", metadata={}) for case_id in case_ids
    ]


def test_all_scored_cases_are_passed_to_the_scorer_in_stable_order() -> None:
    observed: list[int | str] = []

    def scorer(cases: Sequence[CaseResult]) -> CandidateScore:
        observed.extend(case.case_id for case in cases)
        return CandidateScore(score=0.75, metrics={"pass_rate": 0.5, "coverage": 1.0})

    result = finalize_candidate_result(
        benchmark_id="benchmark",
        benchmark_revision="revision",
        selected_cases=_selected(2, 1),
        cases=[_scored(2), _scored(1)],
        scorer=scorer,
    )

    assert observed == [2, 1]
    assert [case.case_id for case in result.cases] == [2, 1]
    assert result.score == 0.75


def test_a_failed_case_skips_the_scorer_and_fails_closed() -> None:
    called = False

    def scorer(cases: Sequence[CaseResult]) -> CandidateScore:
        nonlocal called
        called = True
        return CandidateScore(score=1.0, metrics={"pass_rate": 1.0, "coverage": 1.0})

    result = finalize_candidate_result(
        benchmark_id="benchmark",
        benchmark_revision="revision",
        selected_cases=_selected(1, 2),
        cases=[_scored(1), _failed(2)],
        scorer=scorer,
    )

    assert called is False
    assert result.score is None
    assert result.metrics == {}


def test_a_candidate_level_failure_skips_the_scorer() -> None:
    failure = Failure(
        stage="aggregation",
        code="asset_unavailable",
        message="the scorer asset is unavailable",
        retryable=False,
        case_id=None,
        metadata={},
    )

    result = finalize_candidate_result(
        benchmark_id="benchmark",
        benchmark_revision="revision",
        selected_cases=_selected(1),
        cases=[_scored(1)],
        failures=[failure],
        scorer=lambda _: pytest.fail("scorer must not run"),
    )

    assert result.score is None
    assert result.failures == [failure]


def test_duplicate_case_identity_is_rejected_before_scoring() -> None:
    with pytest.raises(ValueError, match="duplicate case_id"):
        finalize_candidate_result(
            benchmark_id="benchmark",
            benchmark_revision="revision",
            selected_cases=_selected(1),
            cases=[_scored(1), _scored(1)],
            scorer=lambda _: pytest.fail("scorer must not run"),
        )


def test_a_missing_selected_case_is_retained_and_fails_closed() -> None:
    result = finalize_candidate_result(
        benchmark_id="benchmark",
        benchmark_revision="revision",
        selected_cases=[
            SelectedCase(case_id=1, input="input 1", metadata={}),
            SelectedCase(case_id=2, input="input 2", metadata={"split": "test"}),
        ],
        cases=[_scored(1)],
        scorer=lambda _: pytest.fail("scorer must not run with incomplete selected coverage"),
    )

    assert [case.case_id for case in result.cases] == [1, 2]
    assert result.score is None
    assert result.metrics == {}
    missing = result.cases[1]
    assert missing.status == "failed"
    assert missing.input == "input 2"
    assert missing.metadata == {"split": "test"}
    assert [failure.code for failure in missing.failures] == ["case_result_missing"]


def test_scorer_must_return_canonical_metrics() -> None:
    with pytest.raises(ValueError, match="coverage"):
        finalize_candidate_result(
            benchmark_id="benchmark",
            benchmark_revision="revision",
            selected_cases=_selected(1),
            cases=[_scored(1)],
            scorer=lambda _: CandidateScore(score=1.0, metrics={"pass_rate": 1.0}),
        )


def test_finalizer_rejects_boolean_and_non_finite_scores() -> None:
    for score in (True, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="finite number"):
            finalize_candidate_result(
                benchmark_id="benchmark",
                benchmark_revision="revision",
                selected_cases=_selected(1),
                cases=[_scored(1)],
                scorer=lambda _, score=score: CandidateScore(
                    score=score,  # type: ignore[arg-type]
                    metrics={"pass_rate": 1.0, "coverage": 1.0},
                ),
            )


def test_shared_case_constructors_own_the_public_case_envelope() -> None:
    selected = SelectedCase(case_id=7, input="question", metadata={"split": "test"})
    scored = scored_case_result(
        selected_case=selected,
        output="answer",
        finish_reason="stop",
        grade=CaseGrade(method="test", score=1.0, metrics={}, checks=[]),
    )
    failure = Failure(
        stage="grading",
        code="judge_failed",
        message="Judge failed",
        retryable=True,
        case_id=7,
        metadata={},
    )
    failed = failed_case_result(
        selected_case=selected,
        failures=[failure],
        output="answer",
        finish_reason="stop",
    )

    assert scored.status == "scored"
    assert scored.input == failed.input == "question"
    assert scored.metadata == failed.metadata == {"split": "test"}
    assert failed.status == "failed"
    assert failed.output == "answer"
    assert failed.failures == [failure]


def test_finalizer_does_not_coerce_a_string_score() -> None:
    with pytest.raises(ValueError):
        finalize_candidate_result(
            benchmark_id="benchmark",
            benchmark_revision="revision",
            selected_cases=_selected(1),
            cases=[_scored(1)],
            scorer=lambda _: CandidateScore(
                score="1",  # type: ignore[arg-type]
                metrics={"pass_rate": 1.0, "coverage": 1.0},
            ),
        )


def test_collected_provider_refusal_preserves_exact_text_as_a_refused_case() -> None:
    exact = "I can’t provide that dosage."
    row = {
        "error": {
            "kind": "ProviderRefusal",
            "message": json.dumps(
                {"refusal": exact, "finish_reason": "content_filter"},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        }
    }

    refusal = collected_provider_refusal(row)
    assert refusal is not None
    assert (refusal.text, refusal.finish_reason) == (exact, "content_filter")
    case = refused_case_result(
        selected_case=SelectedCase(case_id="health-7", input="Recommend a dosage.", metadata={}),
        refusal=refusal.text,
        finish_reason=refusal.finish_reason,
    )

    assert case.status == "refused"
    assert case.refusal == exact
    assert case.output is None
    assert case.grade is None
    assert case.failures[0].code == "provider_refusal"


def test_collected_provider_refusal_does_not_infer_from_generic_error_text() -> None:
    assert (
        collected_provider_refusal(
            {"error": {"kind": "ResolutionError", "message": "provider refused"}}
        )
        is None
    )


def test_public_error_keeps_safe_diagnostics_and_rejects_internal_detail() -> None:
    safe = public_error(
        {
            "kind": "ResolutionError",
            "code": "provider_error",
            "message": "the provider was unavailable",
            "permanent": True,
        },
        default_code="case_execution_failed",
        default_message="Candidate Case execution failed",
    )
    assert safe.code == "provider_error"
    assert safe.message == "the provider was unavailable"
    assert safe.kind == "ResolutionError"
    assert safe.retryable is False

    unsafe = public_error(
        {
            "kind": "RuntimeError",
            "message": ('Traceback (most recent call last): File "/private/tmp/runner.py", line 4'),
        },
        default_code="case_execution_failed",
        default_message="Candidate Case execution failed",
    )
    assert unsafe.message == "Candidate Case execution failed"
    assert "/private/tmp" not in unsafe.message

    credentials = public_error(
        {
            "message": (
                r"request failed at C:\runner\job.py with password=hunter2 "
                "and access key AKIAIOSFODNN7EXAMPLE"
            )
        },
        default_code="case_execution_failed",
        default_message="Candidate Case execution failed",
    )
    assert credentials.message == "Candidate Case execution failed"


@pytest.mark.parametrize(
    "message",
    (
        "provider rejected OPENAI_API_KEY=abcdefgh",
        "request failed with client_secret=hunter2",
        "authentication used session_cookie=abcdef",
    ),
)
def test_public_error_rejects_compound_credential_assignments(message: str) -> None:
    diagnostic = public_error(
        {"message": message},
        default_code="case_execution_failed",
        default_message="Candidate Case execution failed",
    )

    assert diagnostic.message == "Candidate Case execution failed"


@pytest.mark.asyncio
async def test_provider_refusal_identity_and_text_survive_url4_collection() -> None:
    exact = "I can’t comply with that request."
    node = Url4Node("test")

    @node.endpoint("/refuse")
    def refuse(_: Request) -> str:
        raise ProviderRefusal(exact, finish_reason="content_filter")

    refusal = expr(
        src(RelExpr(path="/refuse", context="$item", intent=Text("run")), name="value"),
        intent=Text("$value"),
    )
    expression = iterate(
        [Text("case")],
        body=(src(refusal, name="refusal", weight=0.0),),
        intent=Text("$refusal"),
        on_error="collect",
    )

    rows = json.loads((await node.evaluate(render(expression))).text)
    refusal = collected_provider_refusal(rows[0])
    assert refusal is not None
    assert (refusal.text, refusal.finish_reason) == (exact, "content_filter")
