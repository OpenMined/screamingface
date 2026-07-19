from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable

import httpx
import pytest
from url4 import Request, Url4Node, build

import screamingface as sf
from screamingface import _grading
from screamingface._compiler import compile_model_expression
from screamingface._profile import ModelRecord, Registry


def _registry(*models: str) -> Registry:
    selected = models or ("judge/model",)
    return Registry(
        models=tuple(ModelRecord(model, ()) for model in selected),
        reducers=(),
        benchmarks=(),
        response_schemas=("screamingface.fusion-result.v1",),
    )


def _reference() -> dict[str, object]:
    return {
        "id": "rubric-1",
        "sections": [
            {
                "id": "factual-accuracy",
                "title": "Factual Accuracy",
                "criteria": [
                    {
                        "id": "required-fact",
                        "weight": 10,
                        "requirement": "Names the required fact.",
                    },
                    {
                        "id": "hallucination",
                        "weight": -5,
                        "requirement": "Invents an unsupported fact.",
                    },
                ],
            },
            {
                "id": "presentation-quality",
                "criteria": [
                    {
                        "id": "clear-prose",
                        "weight": 4,
                        "requirement": "Uses clear prose.",
                    }
                ],
            },
        ],
    }


def _rubric_benchmark(
    *,
    cases: list[sf.Case] | None = None,
    passes: int = 1,
    prompt: str = "Judge the criterion.",
) -> sf.Benchmark:
    return sf.Benchmark(
        "rubric@1",
        cases=cases or [sf.Case("q1", "Research question", reference=_reference())],
        grader=sf.graders.Rubric(
            model="judge/model",
            prompt=prompt,
            passes=passes,
            params={"temperature": 0.2, "reasoning": "low", "max_tokens": 4096},
        ),
    )


def _run(
    benchmark: sf.Benchmark,
    *,
    answer: str = "Fusion answer",
    members: dict[str, sf.MemberResult] | None = None,
) -> sf.Run:
    selected_members = members or {
        "member_1": sf.MemberResult("worker/one", "Member one"),
        "member_2": sf.MemberResult("worker/two", "Member two"),
    }
    selected_cases = benchmark._materialize_cases()
    return sf.Run(
        benchmark=benchmark,
        fusion_name="test-fusion",
        fusion_url4="(recipe)",
        members={member_id: member.model for member_id, member in selected_members.items()},
        cases=selected_cases,
        results=[
            sf.CaseResult(
                selected_cases[0].id,
                members=selected_members,
                answer=answer,
            )
        ],
    )


def _response(
    body: str = '{"explanation":"Supported.","criterion_status":"MET"}',
    *,
    status: int = 200,
    content_type: str = "text/plain; charset=utf-8",
) -> httpx.Response:
    return httpx.Response(
        status,
        text=body,
        headers={"content-type": content_type},
        request=httpx.Request("GET", "http://engine.test/v1"),
    )


class RecordingClient:
    def __init__(
        self,
        provider: Callable[[str, int], httpx.Response],
        *,
        delay: float = 0.0,
    ) -> None:
        self.provider = provider
        self.delay = delay
        self.calls: list[str] = []
        self.counts: dict[str, int] = {}
        self.active = 0
        self.max_active = 0
        self._lock = threading.Lock()

    def __enter__(self) -> RecordingClient:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def get(self, path: str, *, params: dict[str, str]) -> httpx.Response:
        assert path == "/v1"
        expression = params["q"]
        with self._lock:
            attempt = self.counts.get(expression, 0) + 1
            self.counts[expression] = attempt
            self.calls.append(expression)
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                time.sleep(self.delay)
            return self.provider(expression, attempt)
        finally:
            with self._lock:
                self.active -= 1


def _install(
    monkeypatch: pytest.MonkeyPatch,
    provider: Callable[[str, int], httpx.Response],
    *,
    models: tuple[str, ...] = ("judge/model",),
    delay: float = 0.0,
) -> RecordingClient:
    client = RecordingClient(provider, delay=delay)
    monkeypatch.setattr(_grading, "load_registry", lambda: _registry(*models))
    monkeypatch.setattr(_grading.httpx, "Client", lambda **_kwargs: client)
    return client


def test_run_grade_dispatches_exact_choice_locally_without_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    benchmark = sf.Benchmark(
        "gpqa@1",
        cases=[sf.Case("q1", "Question", reference="B")],
        grader=sf.graders.ExactChoice(),
    )
    run = _run(
        benchmark,
        answer="Final answer: B",
        members={
            "member_1": sf.MemberResult("worker/one", "A"),
            "member_2": sf.MemberResult("worker/two", "B"),
        },
    )
    monkeypatch.setattr(
        _grading,
        "load_registry",
        lambda: pytest.fail("ExactChoice must not load the engine registry"),
    )

    grades = run.grade()

    assert grades.results[0].fusion is not None
    assert grades.results[0].fusion.score == 1.0
    assert [grade.score for grade in grades.results[0].members.values()] == [0.0, 1.0]
    assert grades.complete is True


def test_exact_grading_preserves_failed_run_cases_and_revalidates_references() -> None:
    benchmark = sf.Benchmark(
        "gpqa@1",
        cases=[sf.Case("q1", "Question", reference="B")],
        grader=sf.graders.ExactChoice(),
    )
    failure = sf.RunFailure("q1", "timeout", "URL4 engine evaluation timed out")
    run = sf.Run(
        benchmark=benchmark,
        fusion_name="test-fusion",
        fusion_url4="(recipe)",
        members={"member_1": "worker/one", "member_2": "worker/two"},
        cases=benchmark._materialize_cases(),
        results=[sf.CaseResult("q1", members=(), answer=None, failure=failure)],
    )

    grades = run.grade()

    assert grades.results[0].run_failure == failure
    assert grades.results[0].fusion is None
    assert grades.failures == (failure,)

    invalid = sf.Benchmark(
        "bad@1",
        cases=[sf.Case("q1", "Question", reference=1)],
        grader=sf.graders.ExactChoice(),
    )
    invalid_run = sf.Run(
        benchmark=invalid,
        fusion_name="test-fusion",
        fusion_url4="(recipe)",
        members={"member_1": "worker/one", "member_2": "worker/two"},
        cases=invalid._materialize_cases(),
        results=[sf.CaseResult("q1", members=(), answer=None, failure=failure)],
    )
    with pytest.raises(sf.InvalidBenchmarkError, match="exact-choice reference"):
        invalid_run.grade()


def test_grade_run_rejects_non_runs_and_unimplemented_grader_strategies() -> None:
    with pytest.raises(TypeError, match="sf.Run"):
        _grading.grade_run(None)  # type: ignore[arg-type]

    class OtherGrader(sf.Grader):
        kind = "other"

    benchmark = sf.Benchmark(
        "other@1",
        cases=[sf.Case("q1", "Question", reference="answer")],
        grader=OtherGrader(),
    )
    run = _run(
        benchmark,
        members={
            "member_1": sf.MemberResult("worker/one", "answer"),
            "member_2": sf.MemberResult("worker/two", "answer"),
        },
    )
    with pytest.raises(TypeError, match="unsupported grader"):
        run.grade()


def test_grading_uses_the_exact_cases_captured_by_the_run() -> None:
    calls = 0

    def cases() -> list[sf.Case]:
        nonlocal calls
        calls += 1
        reference = "A" if calls == 1 else "B"
        return [sf.Case("q1", "Question", reference=reference)]

    benchmark = sf.Benchmark("changing", cases=cases, grader=sf.graders.ExactChoice())
    selected_cases = benchmark._materialize_cases()
    run = sf.Run(
        benchmark=benchmark,
        fusion_name="test-fusion",
        fusion_url4="(recipe)",
        members={"member_1": "worker/one", "member_2": "worker/two"},
        cases=selected_cases,
        results=[
            sf.CaseResult(
                "q1",
                members={
                    "member_1": sf.MemberResult("worker/one", "A"),
                    "member_2": sf.MemberResult("worker/two", "A"),
                },
                answer="A",
            )
        ],
    )

    grades = run.grade()

    assert calls == 1
    assert grades.results[0].fusion is not None
    assert grades.results[0].fusion.score == 1.0


def test_rubric_preflight_validates_all_references_before_registry_or_judge_traffic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    valid = sf.Case("q1", "Question one", reference=_reference())
    invalid = sf.Case("q2", "Question two", reference={"sections": []})
    benchmark = _rubric_benchmark(cases=[valid, invalid])
    failure = sf.RunFailure("q2", "timeout", "run failed")
    run = sf.Run(
        benchmark=benchmark,
        fusion_name="test-fusion",
        fusion_url4="(recipe)",
        members={"member_1": "worker/one", "member_2": "worker/two"},
        cases=benchmark._materialize_cases(),
        results=[
            sf.CaseResult(
                "q1",
                members={
                    "member_1": sf.MemberResult("worker/one", "answer"),
                    "member_2": sf.MemberResult("worker/two", "answer"),
                },
                answer="fusion",
            ),
            sf.CaseResult("q2", members=(), answer=None, failure=failure),
        ],
    )
    monkeypatch.setattr(
        _grading,
        "load_registry",
        lambda: pytest.fail("registry must not load before every reference validates"),
    )

    with pytest.raises(sf.InvalidBenchmarkError, match="q2.*at least one section"):
        run.grade()


@pytest.mark.parametrize(
    ("reference", "message"),
    [
        (None, "must be an object"),
        ({}, "sections must be an array"),
        ({"sections": []}, "at least one section"),
        ({"sections": [{}]}, "requires an ID or title"),
        ({"sections": [{"id": "facts", "criteria": []}]}, "must contain criteria"),
        (
            {
                "sections": [
                    {
                        "id": "facts",
                        "criteria": [{"id": "c1", "weight": -1, "requirement": "Avoids error"}],
                    }
                ]
            },
            "positive-weight",
        ),
        (
            {
                "sections": [
                    {
                        "id": "facts",
                        "criteria": [{"id": "c1", "weight": True, "requirement": "Fact"}],
                    }
                ]
            },
            "weight must be numeric",
        ),
        (
            {
                "sections": [
                    {
                        "id": "facts",
                        "criteria": [{"id": "c1", "weight": 0, "requirement": "Fact"}],
                    }
                ]
            },
            "finite and non-zero",
        ),
        (
            {
                "sections": [
                    {
                        "id": "pass-rate",
                        "criteria": [{"id": "c1", "weight": 1, "requirement": "Fact"}],
                    }
                ]
            },
            "metric key",
        ),
        (
            {
                "sections": [
                    {
                        "id": "Facts!",
                        "criteria": [{"id": "c1", "weight": 1, "requirement": "Fact"}],
                    },
                    {
                        "id": "facts",
                        "criteria": [{"id": "c2", "weight": 1, "requirement": "Fact"}],
                    },
                ]
            },
            "metric key",
        ),
        (
            {
                "sections": [
                    {
                        "id": "facts",
                        "criteria": [
                            {"id": "same", "weight": 1, "requirement": "Fact"},
                            {"id": "same", "weight": 1, "requirement": "Other"},
                        ],
                    }
                ]
            },
            "criterion ID",
        ),
    ],
)
def test_rubric_reference_contract_is_strict(reference: object, message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        _grading._decode_rubric(reference)


def test_rubric_accepts_title_identity_and_rejects_empty_metric_identity() -> None:
    reference = {
        "sections": [
            {
                "title": "Citation Quality",
                "criteria": [{"id": "citation", "weight": 1, "requirement": "Cites source"}],
            }
        ]
    }
    decoded = _grading._decode_rubric(reference)

    assert decoded.section_metrics == ("citation_quality",)
    assert decoded.criteria[0].section == "Citation Quality"

    invalid = {
        "sections": [
            {
                "id": "---",
                "criteria": [{"id": "citation", "weight": 1, "requirement": "Cites source"}],
            }
        ]
    }
    with pytest.raises(ValueError, match="cannot form a metric key"):
        _grading._decode_rubric(invalid)


def test_rubric_requires_the_judge_to_remain_advertised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _install(monkeypatch, lambda _expression, _attempt: _response(), models=("other",))

    with pytest.raises(sf.UnknownModelError, match="judge/model"):
        _run(_rubric_benchmark()).grade()

    assert client.calls == []


def test_rubric_builds_literal_url4_and_preserves_official_context_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = {
        "sections": [
            {
                "id": "facts",
                "criteria": [
                    {
                        "id": "money",
                        "weight": 1,
                        "requirement": "Explains what $5 buys.",
                    }
                ],
            }
        ]
    }
    benchmark = _rubric_benchmark(
        cases=[sf.Case("q1", "What does $5 buy?", reference=reference)],
        prompt="Judge against the $policy.",
    )
    client = _install(monkeypatch, lambda _expression, _attempt: _response())

    grades = _run(
        benchmark,
        answer="A $5 snack.",
        members={
            "member_1": sf.MemberResult("worker/one", "Nothing for $5."),
            "member_2": sf.MemberResult("worker/two", "Something for $5."),
        },
    ).grade()

    assert grades.complete is True
    assert len(client.calls) == 3
    expression = client.calls[0]
    assert build(expression)
    assert expression.startswith("(/judge/model?temperature=0.2&reasoning=low&max_tokens=4096&q=(")
    assert "<criterion_type>\npositive\n</criterion_type>" in expression
    assert "<query>What does $$5 buy?</query>" in expression
    assert "<response>\nA $$5 snack.\n</response>" in expression
    assert "Explains what $$5 buys." in expression
    assert ")!'Judge against the $$policy.'" in expression
    assert "weight" not in expression
    assert "pass_number" not in expression


@pytest.mark.asyncio
async def test_compiled_judge_expression_crosses_real_url4_http_boundary() -> None:
    node = Url4Node("judge-test")
    observed: list[Request] = []

    @node.endpoint("/judge/model")
    async def judge(request: Request) -> str:
        observed.append(request)
        return '{"explanation":"Supported.","criterion_status":"MET"}'

    expression = compile_model_expression(
        model="judge/model",
        context="<query>What does $5 buy?</query>",
        intent="Judge $literally.",
        params={"temperature": 0.2},
    )
    transport = httpx.ASGITransport(app=node.asgi())
    async with httpx.AsyncClient(transport=transport, base_url="http://judge.test") as client:
        response = await client.get("/v1", params={"q": expression})

    assert response.status_code == 200
    assert response.text == '{"explanation":"Supported.","criterion_status":"MET"}'
    assert observed[0].context == "<query>What does $5 buy?</query>"
    assert observed[0].intent == "Judge $literally."
    assert observed[0].params == {"temperature": "0.2"}
    await node.aclose()


def test_failed_rubric_run_case_is_preflighted_but_receives_no_judge_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    benchmark = _rubric_benchmark()
    failure = sf.RunFailure("q1", "timeout", "run failed")
    run = sf.Run(
        benchmark=benchmark,
        fusion_name="test-fusion",
        fusion_url4="(recipe)",
        members={"member_1": "worker/one", "member_2": "worker/two"},
        cases=benchmark._materialize_cases(),
        results=[sf.CaseResult("q1", members=(), answer=None, failure=failure)],
    )
    client = _install(monkeypatch, lambda _expression, _attempt: _response())

    grades = run.grade()

    assert client.calls == []
    assert grades.results[0].run_failure == failure
    assert grades.results[0].fusion is None
    assert grades.failures == (failure,)


def test_invalid_judge_output_retries_twice_with_the_identical_expression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def provider(_expression: str, attempt: int) -> httpx.Response:
        if attempt < 3:
            return _response('```json\n{"criterion_status":"MAYBE"}\n```')
        return _response('Result:\n```json\n{"explanation":"Valid.","criterion_status":"MET"}\n```')

    reference = {
        "sections": [
            {
                "id": "facts",
                "criteria": [{"id": "c1", "weight": 1, "requirement": "Fact"}],
            }
        ]
    }
    benchmark = _rubric_benchmark(cases=[sf.Case("q1", "Question", reference=reference)])
    client = _install(monkeypatch, provider)

    grades = _run(
        benchmark,
        members={
            "member_1": sf.MemberResult("worker/one", "member"),
            "member_2": sf.MemberResult("worker/two", "member two"),
        },
    ).grade()

    assert grades.complete is True
    assert len(client.calls) == 9
    assert set(client.counts.values()) == {3}
    assert all(grade.verdicts[0].status == "MET" for grade in _all_grades(grades))
    assert all(
        grade.verdicts[0].raw_response is not None
        and grade.verdicts[0].raw_response.startswith("Result:")
        for grade in _all_grades(grades)
    )


def test_exhausted_validation_retries_preserve_evidence_without_partial_scores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _install(monkeypatch, lambda _expression, _attempt: _response("not valid JSON"))
    reference = {
        "sections": [
            {
                "id": "facts",
                "criteria": [{"id": "c1", "weight": 1, "requirement": "Fact"}],
            }
        ]
    }
    benchmark = _rubric_benchmark(cases=[sf.Case("q1", "Question", reference=reference)])

    grades = _run(
        benchmark,
        members={
            "member_1": sf.MemberResult("worker/one", "member"),
            "member_2": sf.MemberResult("worker/two", "member two"),
        },
    ).grade()

    assert len(client.calls) == 9
    assert grades.complete is False
    for grade in _all_grades(grades):
        assert grade.score is None
        assert grade.metrics == {}
        assert grade.coverage == 0.0
        assert grade.verdicts[0].raw_response == "not valid JSON"
        assert grade.verdicts[0].failure is not None
        assert grade.verdicts[0].failure.kind == "invalid_judge_output"
        assert grade.failure is not None
        assert grade.failure.kind == "incomplete_verdicts"
    assert [failure.kind for failure in grades.failures] == [
        "invalid_judge_output",
        "incomplete_verdicts",
        "invalid_judge_output",
        "incomplete_verdicts",
        "invalid_judge_output",
        "incomplete_verdicts",
    ]


@pytest.mark.parametrize(
    ("provider", "kind", "code"),
    [
        (
            lambda _expression, _attempt: _response(
                json.dumps({"error": {"code": "timeout", "message": "judge timed out"}}),
                status=504,
                content_type="application/json",
            ),
            "timeout",
            "timeout",
        ),
        (
            lambda _expression, _attempt: _response(
                json.dumps({"error": {"code": "resolution_failed", "message": "failed"}}),
                status=400,
                content_type="application/json",
            ),
            "url4",
            "resolution_failed",
        ),
        (
            lambda _expression, _attempt: _response(
                "private provider body", status=502, content_type="application/json"
            ),
            "http",
            None,
        ),
        (
            lambda _expression, _attempt: _response("{}", content_type="application/json"),
            "protocol",
            None,
        ),
    ],
)
def test_non_validation_failures_are_recorded_once_without_retry(
    monkeypatch: pytest.MonkeyPatch,
    provider: Callable[[str, int], httpx.Response],
    kind: str,
    code: str | None,
) -> None:
    client = _install(monkeypatch, provider)
    reference = {
        "sections": [
            {
                "id": "facts",
                "criteria": [{"id": "c1", "weight": 1, "requirement": "Fact"}],
            }
        ]
    }
    benchmark = _rubric_benchmark(cases=[sf.Case("q1", "Question", reference=reference)])

    grades = _run(
        benchmark,
        members={
            "member_1": sf.MemberResult("worker/one", "member"),
            "member_2": sf.MemberResult("worker/two", "member two"),
        },
    ).grade()

    assert len(client.calls) == 3
    for grade in _all_grades(grades):
        failure = grade.verdicts[0].failure
        assert failure is not None
        assert failure.kind == kind
        assert failure.code == code
        assert "private provider body" not in failure.message


@pytest.mark.parametrize(
    ("error", "kind"),
    [(httpx.ConnectError("secret host"), "connection"), (httpx.ReadTimeout("late"), "timeout")],
)
def test_transport_failures_are_safe_and_not_retried(
    monkeypatch: pytest.MonkeyPatch, error: Exception, kind: str
) -> None:
    class BrokenClient(RecordingClient):
        def get(self, path: str, *, params: dict[str, str]) -> httpx.Response:
            self.calls.append(params["q"])
            raise error

    client = BrokenClient(lambda _expression, _attempt: _response())
    monkeypatch.setattr(_grading, "load_registry", lambda: _registry("judge/model"))
    monkeypatch.setattr(_grading.httpx, "Client", lambda **_kwargs: client)
    reference = {
        "sections": [
            {
                "id": "facts",
                "criteria": [{"id": "c1", "weight": 1, "requirement": "Fact"}],
            }
        ]
    }
    benchmark = _rubric_benchmark(cases=[sf.Case("q1", "Question", reference=reference)])

    grades = _run(
        benchmark,
        members={
            "member_1": sf.MemberResult("worker/one", "member"),
            "member_2": sf.MemberResult("worker/two", "member two"),
        },
    ).grade()

    assert len(client.calls) == 3
    for grade in _all_grades(grades):
        failure = grade.verdicts[0].failure
        assert failure is not None
        assert failure.kind == kind
        assert "secret host" not in failure.message


def test_transport_failure_after_invalid_output_retains_last_plaintext_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def provider(_expression: str, attempt: int) -> httpx.Response:
        if attempt == 1:
            return _response("malformed judge output")
        raise httpx.ReadTimeout("late")

    client = _install(monkeypatch, provider)
    reference = {
        "sections": [
            {
                "id": "facts",
                "criteria": [{"id": "c1", "weight": 1, "requirement": "Fact"}],
            }
        ]
    }
    benchmark = _rubric_benchmark(cases=[sf.Case("q1", "Question", reference=reference)])

    grades = _run(
        benchmark,
        members={
            "member_1": sf.MemberResult("worker/one", "member"),
            "member_2": sf.MemberResult("worker/two", "member two"),
        },
    ).grade()

    assert len(client.calls) == 6
    for grade in _all_grades(grades):
        verdict = grade.verdicts[0]
        assert verdict.failure is not None
        assert verdict.failure.kind == "timeout"
        assert verdict.raw_response == "malformed judge output"


def test_complete_rubric_scoring_matches_draco_weight_and_pass_rate_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def provider(expression: str, _attempt: int) -> httpx.Response:
        status = "MET"
        if "Invents an unsupported fact." in expression:
            status = "MET"
        return _response(json.dumps({"explanation": "Checked.", "criterion_status": status}))

    client = _install(monkeypatch, provider)
    grades = _run(_rubric_benchmark(passes=2)).grade()

    assert len(client.calls) == 18
    assert grades.complete is True
    for grade in _all_grades(grades):
        assert grade.score == pytest.approx(9 / 14)
        assert grade.coverage == 1.0
        assert grade.metrics == {
            "pass_rate": pytest.approx(2 / 3),
            "factual_accuracy": 0.5,
            "presentation_quality": 1.0,
        }
        assert [(verdict.pass_number, verdict.criterion_id) for verdict in grade.verdicts] == [
            (1, "required-fact"),
            (1, "hallucination"),
            (1, "clear-prose"),
            (2, "required-fact"),
            (2, "hallucination"),
            (2, "clear-prose"),
        ]


def test_judge_concurrency_is_bounded_at_sixteen_and_results_remain_ordered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = {
        "sections": [
            {
                "id": "facts",
                "criteria": [{"id": "c1", "weight": 1, "requirement": "Fact"}],
            }
        ]
    }
    benchmark = _rubric_benchmark(cases=[sf.Case("q1", "Question", reference=reference)])
    members = {
        f"member_{index}": sf.MemberResult(f"worker/{index}", f"answer {index}")
        for index in range(1, 20)
    }
    client = _install(
        monkeypatch,
        lambda _expression, _attempt: _response(),
        delay=0.02,
    )

    grades = _run(benchmark, members=members).grade()

    assert len(client.calls) == 20
    assert 2 <= client.max_active <= 16
    assert tuple(grades.results[0].members) == tuple(members)
    assert all(grade.score == 1.0 for grade in _all_grades(grades))


def test_judge_parser_accepts_a_preamble_or_fence_and_rejects_schema_drift() -> None:
    assert _grading._judge_output(
        'Result:\n```json\n{"explanation":"Yes.","criterion_status":"MET"}\n```'
    ) == ("Yes.", "MET")

    invalid = [
        "",
        "not json",
        "{bad}",
        "[]",
        '{"explanation":"Yes."}',
        '{"explanation":"Yes.","criterion_status":"MAYBE"}',
        '{"explanation":"","criterion_status":"MET"}',
        '{"explanation":"Yes.","criterion_status":"MET","extra":true}',
        '{"explanation":"one","explanation":"two","criterion_status":"MET"}',
    ]
    for body in invalid:
        with pytest.raises((TypeError, ValueError)):
            _grading._judge_output(body)


def _all_grades(grades: sf.Grades) -> tuple[sf.Grade, ...]:
    case = grades.results[0]
    assert case.fusion is not None
    return (case.fusion, *case.members.values())
