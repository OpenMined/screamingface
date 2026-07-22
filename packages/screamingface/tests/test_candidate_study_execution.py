"""End-to-end SDK contracts for one shared candidate-study URL4."""

from __future__ import annotations

import json

import pytest
from url4 import build

import screamingface as sf
import screamingface._benchmark_execution as execution
import screamingface._profile as profile


def _registry() -> dict[str, object]:
    return {
        "schema": "screamingface.registry.v1",
        "response_schemas": [
            "screamingface.recipe-result.v1",
            "screamingface.case-grade.v1",
            "screamingface.report.v1",
            "screamingface.candidate-case-results.v1",
            "screamingface.study-report.v1",
        ],
        "limits": {"max_request_target_bytes": 131072},
        "providers": [
            {"id": "openrouter", "display_name": "OpenRouter", "auth_methods": ["api_key"]}
        ],
        "models": [
            {
                "id": model,
                "provider": "openrouter",
                "supported_tools": ["web_search", "web_fetch"],
                "required_connections": [],
            }
            for model in ("openrouter/a", "openrouter/b", "openrouter/judge")
        ],
        "benchmarks": [
            {
                "id": "draco-lite@1",
                "title": "DRACO Lite",
                "cases_route": "/benchmarks/draco-lite/1/cases",
                "grader": {
                    "kind": "rubric",
                    "route": "/graders/draco-lite-rubric/1",
                    "model": "openrouter/judge",
                    "prompt": "Judge one criterion",
                    "passes": 1,
                    "params": {"temperature": 0.2},
                },
                "aggregator": {"kind": "mean", "route": "/aggregators/mean/1"},
                "tools": ["web_search", "web_fetch"],
                "max_tool_calls": 12,
                "tool_policy_route": "/benchmarks/draco/1/tool-policy",
                "candidate_route": "/benchmarks/draco-lite/1/evaluate-candidates",
                "candidate_aggregator_route": "/aggregators/candidate-mean/1",
            }
        ],
        "reducers": [{"id": "majority_vote", "route": "/reducers/majority-vote/1"}],
    }


def _candidates() -> tuple[sf.Recipe, ...]:
    a = sf.Model("openrouter/a", name="a", prompt="Answer")
    b = sf.Model("openrouter/b", name="b", prompt="Answer")
    pair = sf.Fusion("pair", members=[a, b], reducer=sf.reducers.MajorityVote())
    return a, b, pair


def _payload(*, failed: bool = False) -> dict[str, object]:
    failure: dict[str, object] | None = None
    if failed:
        failure = {
            "case_id": "q1",
            "kind": "url4",
            "message": "provider unavailable",
            "status": None,
            "code": "provider_unavailable",
        }
    return {
        "schema": "screamingface.study-report.v1",
        "benchmark_id": "draco-lite@1",
        "case_ids": ["q1"],
        "candidates": {
            name: {
                "n_cases": 1,
                "n_scored": 0 if failed and name == "b" else 1,
                "coverage": 0.0 if failed and name == "b" else 1.0,
                "score": None if failed and name == "b" else score,
                "metrics": {} if failed and name == "b" else {"normalized_score": score},
                "failures": [failure] if failed and name == "b" else [],
                "complete": not (failed and name == "b"),
            }
            for name, score in (("a", 0.25), ("b", 0.5), ("pair", 0.75))
        },
        "complete": not failed,
    }


def _loaded(monkeypatch: pytest.MonkeyPatch) -> sf.Benchmark:
    sf.config(engine="http://engine.test")
    monkeypatch.setattr(profile, "_get_text", lambda _path: json.dumps(_registry()))
    monkeypatch.setattr(execution, "require_connections", lambda *_args, **_kwargs: None)
    return sf.benchmarks.load("draco-lite@1")


@pytest.mark.parametrize("failed", [False, True])
def test_candidate_study_executes_one_complete_request(
    monkeypatch: pytest.MonkeyPatch, failed: bool
) -> None:
    benchmark = _loaded(monkeypatch)
    expressions: list[str] = []

    def evaluate(expression: str, **_kwargs: object) -> str:
        expressions.append(expression)
        return json.dumps(_payload(failed=failed))

    monkeypatch.setattr(execution, "evaluate_stream", evaluate)
    report = benchmark.evaluate(_candidates(), first=1, progress=False)

    assert isinstance(report, sf.StudyReport)
    assert len(expressions) == 1
    assert report.url4 == expressions[0]
    assert "/benchmarks/draco-lite/1/evaluate-candidates" in report.url4
    assert "/aggregators/candidate-mean/1" in report.url4
    assert "iteration.slice=0:1" in report.url4
    assert tuple(report.candidates) == ("a", "b", "pair")
    assert report.best is not None and report.best.name == "pair"
    assert report.complete is (not failed)


def test_candidate_study_failure_marks_progress_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    benchmark = _loaded(monkeypatch)
    monkeypatch.setattr(
        execution,
        "evaluate_stream",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("transport failed")),
    )

    with pytest.raises(RuntimeError, match="transport failed"):
        benchmark.evaluate(_candidates(), progress=False)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"schema": "wrong"}, "expected schema"),
        ({"benchmark_id": "other@1"}, "benchmark ID"),
        ({"case_ids": ["q1", "q1"]}, "unique"),
        ({"candidates": {}}, "requested candidate order"),
        ({"complete": False}, "complete flag"),
    ],
)
def test_candidate_study_response_is_strict(
    monkeypatch: pytest.MonkeyPatch,
    change: dict[str, object],
    message: str,
) -> None:
    benchmark = _loaded(monkeypatch)
    payload = _payload()
    payload.update(change)

    with pytest.raises(sf.EngineProtocolError, match=message):
        execution._study_report(json.dumps(payload), benchmark, _candidates(), "(/cases)!'run'")


def test_candidate_arguments_and_routes_are_strict(monkeypatch: pytest.MonkeyPatch) -> None:
    benchmark = _loaded(monkeypatch)
    candidates = _candidates()

    with pytest.raises(TypeError, match="sequence"):
        execution.candidates_url4(benchmark, "bad")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="at least one"):
        execution.candidates_url4(benchmark, ())
    with pytest.raises(ValueError, match="duplicate candidate"):
        execution.candidates_url4(benchmark, (candidates[0], candidates[0]))
    with pytest.raises(TypeError, match="sf.Benchmark"):
        execution.candidates_url4(object(), candidates)  # type: ignore[arg-type]

    local = sf.Benchmark(
        "local@1",
        cases=[sf.Case("q1", "Question", reference={})],
        grader=sf.graders.ExactChoice(),
    )
    with pytest.raises(ValueError, match="candidate evaluation route"):
        execution.candidates_url4(local, candidates)


def test_candidate_names_are_values_not_url4_struct_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    benchmark = _loaded(monkeypatch)
    candidate = sf.Model("openrouter/a", name="claude-fable-5", prompt="Answer")

    expression = execution.candidates_url4(benchmark, (candidate,), first=1)

    assert "candidate_1: {name: 'claude-fable-5', root: 'node_1'}" in expression
    assert "claude-fable-5:" not in expression
    assert build(expression) is not None


def test_candidate_record_rejects_inconsistent_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    benchmark = _loaded(monkeypatch)
    payload = _payload()
    candidates = payload["candidates"]
    assert isinstance(candidates, dict)
    a = candidates["a"]
    assert isinstance(a, dict)
    a["n_cases"] = 2

    with pytest.raises(sf.EngineProtocolError, match="case count"):
        execution._study_report(json.dumps(payload), benchmark, _candidates(), "expr")
