from __future__ import annotations

import json

import httpx

import screamingface as sf
import screamingface._benchmark_execution as execution
import screamingface._profile as profile


def _registry_response() -> httpx.Response:
    payload = {
        "schema": "screamingface.registry.v1",
        "response_schemas": [
            "screamingface.recipe-result.v1",
            "screamingface.case-grade.v1",
            "screamingface.report.v1",
        ],
        "limits": {"max_request_target_bytes": 131072},
        "providers": [
            {"id": "codex", "display_name": "Codex", "auth_methods": ["oauth"]},
            {"id": "gemini", "display_name": "Gemini", "auth_methods": ["api_key"]},
        ],
        "models": [
            {
                "id": "codex/gpt-5.5",
                "provider": "codex",
                "supported_tools": [],
                "required_connections": [],
            },
            {
                "id": "gemini/2.5",
                "provider": "gemini",
                "supported_tools": [],
                "required_connections": [],
            },
        ],
        "benchmarks": [
            {
                "id": "gpqa@1",
                "title": "GPQA Diamond",
                "cases_route": "/benchmarks/gpqa/1/cases",
                "grader": {"kind": "exact_choice", "route": "/graders/exact-choice/1"},
                "aggregator": {"kind": "mean", "route": "/aggregators/mean/1"},
                "tools": [],
                "max_tool_calls": None,
                "tool_policy_route": None,
            }
        ],
        "reducers": [
            {"id": "majority_vote", "route": "/reducers/majority-vote/1"},
        ],
    }
    return httpx.Response(200, text=json.dumps(payload), headers={"content-type": "text/plain"})


def test_loaded_benchmark_evaluates_one_complete_url4_request(monkeypatch) -> None:
    sf.config(engine="http://engine.test")
    monkeypatch.setattr(profile, "_get_text", lambda _path: _registry_response().text)
    monkeypatch.setattr(execution, "require_connections", lambda *_args, **_kwargs: None)
    expressions: list[str] = []

    def evaluate(expression: str, *, timeout: float, on_event: object) -> str:
        assert timeout > 0
        assert on_event is not None
        expressions.append(expression)
        payload = {
            "schema": "screamingface.report.v1",
            "benchmark_id": "gpqa@1",
            "case_ids": ["q1"],
            "n_cases": 1,
            "n_scored": 1,
            "coverage": 1.0,
            "score": 1.0,
            "baseline": 1.0,
            "gain": 0.0,
            "members": {
                "member_1": {"model": "codex/gpt-5.5", "score": 1.0, "metrics": {}},
                "member_2": {"model": "gemini/2.5", "score": 0.0, "metrics": {}},
            },
            "metrics": {},
            "failures": [],
            "complete": True,
        }
        return json.dumps(payload)

    monkeypatch.setattr(execution, "evaluate_stream", evaluate)
    benchmark = sf.benchmarks.load("gpqa@1")
    fusion = sf.Fusion(
        "duo",
        members=["codex/gpt-5.5", "gemini/2.5"],
        reducer=sf.reducers.MajorityVote(),
    )

    report = benchmark.evaluate(fusion, first=1, progress=False)

    assert len(expressions) == 1
    assert "/benchmarks/gpqa/1/cases*" in expressions[0]
    assert "iteration.slice=0:1" in expressions[0]
    assert "/graders/exact-choice/1" in expressions[0]
    assert "/aggregators/mean/1" in expressions[0]
    assert report.url4 == expressions[0]
    assert report.score == 1.0
    assert report.gain == 0.0
