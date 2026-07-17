from __future__ import annotations

import json
import re
from collections import Counter
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from url4 import Request, Url4Node

import screamingface as sf
import screamingface.draco as draco_module
import screamingface.evaluation as evaluation
from screamingface.benchmarks import _EvaluationCase, _resolve_benchmark
from screamingface.draco import (
    _draco_row,
    _normalized_score,
    _parse_criterion_verdict,
    _parse_draco_rubric,
    _pass_rate,
    _select_draco_rows,
)
from screamingface.engine import Url4EngineClient

_KEYWORD = re.compile(r"\[mock-keyword:\s*([^\]]+)\]", re.IGNORECASE)
_CRITERION = re.compile(r"<criterion>\s*(.*?)\s*</criterion>", re.DOTALL)
_RESPONSE = re.compile(r"<response>\s*(.*?)\s*</response>", re.DOTALL)


def test_draco_registry_and_mock_adapter_contract() -> None:
    definition = _resolve_benchmark("draco")
    loaded = definition.load(sf.Session(mode="mock"), first=2, seed=3)

    assert definition.name == "DRACO"
    assert definition.version == "perplexity-ai/draco-test-v1"
    assert definition.primary_metric == "normalized_score"
    assert definition.grader.name == "draco_rubric"
    assert loaded.display_name == "DRACO-shaped synthetic research fixture"
    assert loaded.dataset_source == "synthetic-draco-shaped"
    assert len(loaded.cases) == 2
    assert loaded.cases[0].metadata["judge_runs"] == 1
    assert loaded.cases[0].metadata["domain"] in {"Academic", "Technology"}


def test_draco_weighted_score_rewards_positive_and_penalizes_negative_criteria() -> None:
    criteria = _parse_draco_rubric(
        {
            "sections": [
                {
                    "id": "factual-accuracy",
                    "criteria": [
                        {"id": "a", "weight": 10, "requirement": "A"},
                        {"id": "b", "weight": 10, "requirement": "B"},
                        {"id": "bad", "weight": -5, "requirement": "Bad"},
                    ],
                }
            ]
        }
    )

    assert _normalized_score(criteria, {"a": True, "b": True, "bad": False}) == 1.0
    assert _normalized_score(criteria, {"a": True, "b": True, "bad": True}) == 0.75
    assert _pass_rate(criteria, {"a": True, "b": False, "bad": False}) == pytest.approx(2 / 3)
    assert _normalized_score(criteria, {}) == 0.0
    assert _pass_rate(criteria, {}) == 0.0


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("not-json", "not valid rubric JSON"),
        ({}, "containing sections"),
        ({"sections": []}, "at least one criterion"),
        ({"sections": ["bad"]}, "sections must be objects"),
        ({"sections": [{}]}, "require an id and criteria list"),
        (
            {"sections": [{"id": "axis", "criteria": ["bad"]}]},
            "criteria must be objects",
        ),
        (
            {
                "sections": [
                    {
                        "id": "axis",
                        "criteria": [{"id": "", "weight": 1, "requirement": "A"}],
                    }
                ]
            },
            "non-empty id",
        ),
    ],
)
def test_draco_rubric_validation_fails_loudly(raw: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _parse_draco_rubric(raw)


def test_draco_row_selection_validates_bounds_and_row_shape() -> None:
    with pytest.raises(ValueError, match="first must be positive"):
        _select_draco_rows([], 0, 0)
    with pytest.raises(ValueError, match="contains 0 rows"):
        _select_draco_rows([], 1, 0)
    with pytest.raises(ValueError, match="non-empty id"):
        _draco_row({"problem": "P", "domain": "D", "answer": {"sections": []}})


def test_draco_live_adapter_uses_public_test_split(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = json.loads(
        draco_module.files("screamingface._data")
        .joinpath("draco_shaped_synthetic.json")
        .read_text()
    )
    seen: list[tuple[str, str]] = []

    def load_dataset(name: str, *, split: str):
        seen.append((name, split))
        return raw

    monkeypatch.setattr(
        draco_module,
        "import_module",
        lambda _name: SimpleNamespace(load_dataset=load_dataset),
    )
    loaded = _resolve_benchmark("draco").load(sf.Session(mode="live"), 1, 0)

    assert seen == [("perplexity-ai/draco", "test")]
    assert loaded.display_name == "DRACO"
    assert loaded.dataset_source == "huggingface:perplexity-ai/draco:test"
    assert loaded.cases[0].metadata["judge_runs"] == 5


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"explanation":"present","criterion_status":"MET"}', True),
        ('```json\n{"explanation":"absent","criterion_status":"UNMET"}\n```', False),
        ('{"criterion_status":"MET"}', None),
        ("not JSON", None),
    ],
)
def test_draco_judge_verdict_parser(raw: str, expected: bool | None) -> None:
    assert _parse_criterion_verdict(raw) is expected


@pytest.mark.asyncio
async def test_draco_grader_reports_empty_answers_and_invalid_judge_results() -> None:
    definition = _resolve_benchmark("draco")
    case = definition.load(sf.Session(mode="mock"), 1, 0).cases[0]

    class InvalidJudge:
        async def evaluate(self, _expression: str) -> str:
            return "not JSON"

    engine: Any = InvalidJudge()
    empty = await definition.grader.grade(case, "", engine=engine)
    invalid = await definition.grader.grade(case, "answer", engine=engine)

    assert empty.failure_code == "invalid_answer"
    assert invalid.failure_code == "invalid_judge_result"
    bad_case = _EvaluationCase("bad", "prompt", "not a rubric")
    with pytest.raises(TypeError, match="invalid rubric reference"):
        await definition.grader.grade(bad_case, "answer", engine=engine)


@pytest.mark.asyncio
async def test_draco_evaluation_runs_panel_synthesis_and_grading_through_url4() -> None:
    calls: Counter[str] = Counter()
    node = _draco_node(calls)
    transport = httpx.ASGITransport(app=node.asgi())
    async with httpx.AsyncClient(transport=transport, base_url="http://url4.test") as http:
        engine = Url4EngineClient("http://url4.test", client=http)
        session = sf.Session(mode="mock", engine=engine)
        fusion = sf.Fusion(
            "draco-trio",
            sf.models.list()[:3],
            prompt="Research this question thoroughly: $question",
            reducer=sf.ModelReducer(
                model="codex/gpt-5.5",
                prompt=("Produce one unified research answer for $question from $panel_answers"),
            ),
        )
        run = await evaluation.evaluate(
            session=session,
            fusion=fusion,
            benchmark="draco",
            first=2,
            seed=0,
        )

    assert run.primary_metric == "normalized_score"
    assert run.score == 100.0
    assert run.baseline == 33.3
    assert run.gain == 66.7
    assert dict(run.metrics) == {
        "factual_accuracy": 100.0,
        "normalized_score": 100.0,
        "pass_rate": 100.0,
        "verdict_coverage": 100.0,
    }
    assert calls["judge"] == 32


def _draco_node(calls: Counter[str]) -> Url4Node:
    node = Url4Node("draco-contract")

    async def panel(request: Request, *, keyword: str) -> str:
        calls[keyword] += 1
        if "unified" in request.intent.lower():
            return "Unified research response: alpha, beta, gamma"
        return f"Independent research response covering {keyword}."

    async def judge(request: Request) -> str:
        calls["judge"] += 1
        criterion = _CRITERION.search(request.intent)
        response = _RESPONSE.search(request.intent)
        assert criterion is not None and response is not None
        keyword = _KEYWORD.search(criterion.group(1))
        assert keyword is not None
        met = keyword.group(1).strip().lower() in response.group(1).lower()
        status = "MET" if met else "UNMET"
        return json.dumps({"explanation": status, "criterion_status": status})

    node.endpoint("/codex/gpt-5.5")(lambda request: panel(request, keyword="alpha"))
    node.endpoint("/gemini/2.5")(lambda request: panel(request, keyword="beta"))
    node.endpoint("/claude/sonnet-4.6")(lambda request: panel(request, keyword="gamma"))
    node.endpoint("/gemini/3.1-pro-preview")(judge)
    return node
