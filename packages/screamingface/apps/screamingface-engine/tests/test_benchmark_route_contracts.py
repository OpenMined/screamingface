from __future__ import annotations

import json
from collections.abc import Callable
from typing import cast

import pytest
from screamingface.benchmark import Case
from url4 import Request, ResolutionError

import screamingface_engine.benchmark_definitions.gpqa as gpqa_source
from screamingface_engine.aggregators import mean
from screamingface_engine.benchmarks import (
    draco_cases,
    draco_lite_cases,
    draco_preview_cases,
    gpqa_cases,
)
from screamingface_engine.graders import exact_choice


def _request(
    path: str,
    *,
    context: str = "",
    intent: str = "",
    params: dict[str, str] | None = None,
) -> Request:
    return Request(path, context, intent, params or {})


def _recipe_result() -> dict[str, object]:
    return {
        "schema": "screamingface.recipe-result.v1",
        "members": {
            "member_1": {"model": "codex/gpt-5.5", "answer": "A"},
            "member_2": {"model": "gemini/2.5-flash", "answer": "B"},
        },
        "answer": "A",
    }


def _case_grade(*, case_id: str = "q1", recipe_score: float = 1.0) -> dict[str, object]:
    return {
        "schema": "screamingface.case-grade.v1",
        "benchmark_id": "gpqa@1",
        "case_id": case_id,
        "recipe": {"score": recipe_score, "metrics": {}, "coverage": 1.0},
        "members": {
            "member_1": {
                "model": "codex/gpt-5.5",
                "score": 1.0,
                "metrics": {},
                "coverage": 1.0,
            },
            "member_2": {
                "model": "gemini/2.5-flash",
                "score": 0.0,
                "metrics": {},
                "coverage": 1.0,
            },
        },
    }


def test_exact_choice_returns_one_strict_case_grade() -> None:
    result = exact_choice(
        _request(
            "/graders/exact-choice/1",
            context=json.dumps(_recipe_result()),
            intent=json.dumps({"benchmark_id": "gpqa@1", "case_id": "q1", "reference": "A"}),
        )
    )

    assert json.loads(result) == _case_grade()


@pytest.mark.parametrize(
    ("request_value", "message"),
    [
        (_request("/graders/exact-choice/1", params={"x": "1"}), "parameters"),
        (_request("/graders/exact-choice/1"), "context must be a JSON object"),
        (
            _request("/graders/exact-choice/1", context="[]", intent="{}"),
            "context must be a JSON object",
        ),
        (
            _request("/graders/exact-choice/1", context="not-json", intent="{}"),
            "context must be a JSON object",
        ),
        (
            _request(
                "/graders/exact-choice/1",
                context=json.dumps({**_recipe_result(), "schema": "wrong"}),
                intent=json.dumps({"benchmark_id": "gpqa@1", "case_id": "q1", "reference": "A"}),
            ),
            "expected Recipe schema",
        ),
        (
            _request(
                "/graders/exact-choice/1",
                context=json.dumps(_recipe_result()),
                intent=json.dumps({"benchmark_id": "gpqa@1", "case_id": "q1"}),
            ),
            "missing field",
        ),
        (
            _request(
                "/graders/exact-choice/1",
                context=json.dumps(_recipe_result()),
                intent=json.dumps(
                    {
                        "benchmark_id": "gpqa@1",
                        "case_id": "q1",
                        "reference": [],
                    }
                ),
            ),
            "non-empty string",
        ),
    ],
)
def test_exact_choice_rejects_malformed_requests(request_value: Request, message: str) -> None:
    with pytest.raises(ResolutionError, match=message) as raised:
        exact_choice(request_value)

    assert raised.value.code == "malformed_source"
    assert raised.value.permanent is True


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value.update(members={}), "non-empty object"),
        (
            lambda value: value.update(
                members={"member_2": {"model": "codex/gpt-5.5", "answer": "A"}}
            ),
            "contiguous",
        ),
        (
            lambda value: value.update(members={"member_1": {"model": "codex/gpt-5.5"}}),
            "missing field",
        ),
        (lambda value: value.update(answer=" "), "Recipe answer"),
    ],
)
def test_exact_choice_rejects_malformed_recipe_results(
    mutate: Callable[[dict[str, object]], None], message: str
) -> None:
    recipe = _recipe_result()
    mutate(recipe)
    request = _request(
        "/graders/exact-choice/1",
        context=json.dumps(recipe),
        intent=json.dumps({"benchmark_id": "gpqa@1", "case_id": "q1", "reference": "A"}),
    )

    with pytest.raises(ResolutionError, match=message):
        exact_choice(request)


def test_mean_aggregates_successes_and_preserves_typed_row_failures() -> None:
    result = mean(
        _request(
            "/aggregators/mean/1",
            intent=json.dumps(
                [
                    _case_grade(),
                    {"error": {"kind": "resolution", "message": "model failed"}},
                ]
            ),
        )
    )

    payload = json.loads(result)
    assert payload["n_cases"] == 2
    assert payload["n_scored"] == 1
    assert payload["coverage"] == 0.5
    assert payload["case_ids"] == ["q1", "row_2"]
    assert payload["failures"] == [
        {
            "case_id": "row_2",
            "kind": "url4",
            "message": "resolution: model failed",
            "status": None,
            "code": "resolution_failed",
        }
    ]


def test_mean_preserves_average_recipe_and_member_metrics() -> None:
    first = _case_grade(case_id="q1")
    second = _case_grade(case_id="q2")
    cast(dict[str, object], first["recipe"])["metrics"] = {"normalized_score": 0.5}
    cast(dict[str, object], second["recipe"])["metrics"] = {"normalized_score": 1.0}
    cast(dict[str, dict[str, object]], first["members"])["member_1"]["metrics"] = {
        "normalized_score": 0.25
    }
    cast(dict[str, dict[str, object]], second["members"])["member_1"]["metrics"] = {
        "normalized_score": 0.75
    }

    payload = json.loads(mean(_request("/aggregators/mean/1", intent=json.dumps([first, second]))))

    assert payload["metrics"] == {"normalized_score": 0.75}
    assert payload["members"]["member_1"]["metrics"] == {"normalized_score": 0.5}


def test_draco_case_routes_use_real_sdk_loaders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = Case("q1", "Question", reference={"sections": []})
    monkeypatch.setenv("HF_TOKEN", "hf_test")
    monkeypatch.setattr(
        "screamingface_engine.benchmark_definitions.draco.draco_cases", lambda: (case,)
    )
    monkeypatch.setattr(
        "screamingface_engine.benchmark_definitions.draco_preview.draco_preview_cases",
        lambda: (case,),
    )
    monkeypatch.setattr(
        "screamingface_engine.benchmark_definitions.draco_lite.draco_lite_cases",
        lambda: (case,),
    )

    assert json.loads(draco_cases()) == case._to_wire()
    assert json.loads(draco_preview_cases()) == case._to_wire()
    assert json.loads(draco_lite_cases()) == case._to_wire()


def test_draco_case_routes_require_dataset_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HF_TOKEN", raising=False)

    with pytest.raises(ResolutionError, match="requires HF_TOKEN") as raised:
        draco_cases()

    assert raised.value.code == "dataset_authentication_required"


def test_draco_case_routes_translate_dataset_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HF_TOKEN", "hf_test")
    monkeypatch.setattr(
        "screamingface_engine.benchmark_definitions.draco.draco_cases",
        lambda: (_ for _ in ()).throw(RuntimeError("offline")),
    )

    with pytest.raises(ResolutionError, match="could not load") as raised:
        draco_cases()

    assert raised.value.code == "dataset_unavailable"


@pytest.mark.parametrize(
    ("request_value", "message"),
    [
        (_request("/aggregators/mean/1", context="x", intent="[]"), "context"),
        (
            _request("/aggregators/mean/1", intent="[]", params={"mode": "mean"}),
            "parameters",
        ),
        (_request("/aggregators/mean/1"), "JSON array"),
        (_request("/aggregators/mean/1", intent="not-json"), "JSON array"),
        (_request("/aggregators/mean/1", intent="[]"), "non-empty"),
        (_request("/aggregators/mean/1", intent="[1]"), "JSON objects"),
        (
            _request(
                "/aggregators/mean/1",
                intent=json.dumps([{"error": {"kind": "url4", "message": "failed"}}]),
            ),
            "failed",
        ),
        (
            _request("/aggregators/mean/1", intent=json.dumps([{"error": "failed"}])),
            "error must be an object",
        ),
    ],
)
def test_mean_rejects_invalid_top_level_inputs(request_value: Request, message: str) -> None:
    with pytest.raises(ResolutionError, match=message):
        mean(request_value)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value.update(schema="wrong"), "is not"),
        (lambda value: value.update(recipe=[]), "grades must be objects"),
        (lambda value: value.update(case_id=" "), "case ID"),
        (lambda value: value.update(members={}), "must not be empty"),
        (
            lambda value: value.update(
                members={
                    "member_2": {
                        "model": "codex/gpt-5.5",
                        "score": 1.0,
                        "metrics": {},
                        "coverage": 1.0,
                    }
                }
            ),
            "contiguous",
        ),
        (
            lambda value: value.update(recipe={"score": "one"}),
            "score must be numeric",
        ),
        (
            lambda value: value.update(recipe={"score": float("nan")}),
            "finite and between",
        ),
    ],
)
def test_mean_rejects_malformed_grade_rows(
    mutate: Callable[[dict[str, object]], None], message: str
) -> None:
    grade = _case_grade()
    mutate(grade)

    with pytest.raises(ResolutionError, match=message):
        mean(_request("/aggregators/mean/1", intent=json.dumps([grade])))


def test_mean_rejects_disagreement_between_successful_rows() -> None:
    first = _case_grade()
    other_benchmark = _case_grade(case_id="q2")
    other_benchmark["benchmark_id"] = "other@1"
    with pytest.raises(ResolutionError, match="benchmark ID"):
        mean(_request("/aggregators/mean/1", intent=json.dumps([first, other_benchmark])))

    other_members = _case_grade(case_id="q2")
    members = other_members["members"]
    assert isinstance(members, dict)
    member = members["member_1"]
    assert isinstance(member, dict)
    member["model"] = "other/model"
    with pytest.raises(ResolutionError, match="Recipe members"):
        mean(_request("/aggregators/mean/1", intent=json.dumps([first, other_members])))


def test_gpqa_route_requires_engine_dataset_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HF_TOKEN", raising=False)
    with pytest.raises(ResolutionError, match="requires HF_TOKEN") as raised:
        gpqa_cases()

    assert raised.value.code == "dataset_authentication_required"


def test_gpqa_route_maps_dataset_loader_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HF_TOKEN", "hf_test")

    def unavailable() -> tuple[()]:
        raise RuntimeError("offline")

    monkeypatch.setattr(gpqa_source, "gpqa_cases", unavailable)
    with pytest.raises(ResolutionError, match="could not load") as raised:
        gpqa_cases()

    assert raised.value.code == "dataset_unavailable"


def test_gpqa_route_preserves_typed_dataset_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HF_TOKEN", "hf_test")
    expected = ResolutionError("gated", code="dataset_authentication_required")

    def gated() -> tuple[()]:
        raise expected

    monkeypatch.setattr(gpqa_source, "gpqa_cases", gated)
    with pytest.raises(ResolutionError) as raised:
        gpqa_cases()

    assert raised.value is expected
