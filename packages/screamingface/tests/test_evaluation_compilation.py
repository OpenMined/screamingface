from __future__ import annotations

from typing import Any, cast

import pytest

import screamingface as sf
from screamingface._evaluation.model import (
    Candidate,
    Operation,
    _compiled_candidate,
    _compiled_evaluation,
    _compiled_operation,
    _Evaluation,
)


def planned_candidate(name: str = "opus") -> Candidate:
    return _compiled_candidate(
        name=name,
        kind="model",
        models=("provider/opus",),
        url4="(@)!'opus'",
        operations=(
            operation(
                id=f"op_{name}",
                kind="model",
                label=f"{name} answer",
                depends_on=(),
            ),
        ),
    )


def evaluation_plan(
    candidates: tuple[Candidate, ...] | None = None,
) -> _Evaluation:
    return _compiled_evaluation(
        benchmark=sf.BenchmarkInfo(
            name="draco",
            id="draco@1",
            title="DRACO",
            case_count=100,
            primary_metric="normalized_score",
            score_direction="maximize",
        ),
        limit=1,
        case_count=1,
        candidates=candidates or (planned_candidate(),),
        required_capabilities=("web_search",),
        required_models=("provider/opus", "provider/judge"),
    )


def operation(
    id: str,
    kind: str,
    label: str,
    depends_on: tuple[str, ...],
) -> Operation:
    return _compiled_operation(
        id=id,
        kind=kind,
        label=label,
        depends_on=depends_on,
    )


def test_plan_values_are_readable_and_support_strict_lookup() -> None:
    plan = evaluation_plan((planned_candidate("opus"), planned_candidate("gpt")))

    assert repr(plan) == ("_Evaluation(benchmark='draco@1', cases=1, candidates=[opus, gpt])")
    assert plan.candidates[0] is plan.candidates["opus"]
    assert plan.candidates[:] == tuple(plan.candidates)
    assert plan.candidates == tuple(plan.candidates)
    assert plan.candidates != object()
    assert not hasattr(plan, "url4")
    with pytest.raises(KeyError, match="unknown Candidate"):
        plan.candidates["missing"]
    with pytest.raises(ValueError, match="exactly one"):
        plan.candidates.only


def test_candidate_exposes_its_compiled_operation_dag() -> None:
    answer = operation(
        id="op_answer",
        kind="model",
        label="opus answer",
        depends_on=(),
    )
    grade = operation(
        id="op_grade",
        kind="grading",
        label="DRACO grading",
        depends_on=("op_answer",),
    )

    candidate = _compiled_candidate(
        name="opus",
        kind="model",
        models=("provider/opus",),
        url4="(@)!'opus'",
        operations=(answer, grade),
    )

    assert candidate.operations == (answer, grade)


@pytest.mark.parametrize(
    ("values", "message"),
    [
        (
            {
                "id": " ",
                "kind": "model",
                "label": "opus answer",
                "depends_on": (),
            },
            "id",
        ),
        (
            {
                "id": "op_answer",
                "kind": " ",
                "label": "opus answer",
                "depends_on": (),
            },
            "kind",
        ),
        (
            {
                "id": "op_answer",
                "kind": "model",
                "label": " ",
                "depends_on": (),
            },
            "label",
        ),
        (
            {
                "id": "op_answer",
                "kind": "model",
                "label": "opus answer",
                "depends_on": ("op_source", "op_source"),
            },
            "unique",
        ),
        (
            {
                "id": "op_answer",
                "kind": "model",
                "label": "opus answer",
                "depends_on": ("op_answer",),
            },
            "itself",
        ),
    ],
)
def test_operation_rejects_malformed_identity_and_dependencies(
    values: dict[str, object],
    message: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        _compiled_operation(**cast(Any, values))


@pytest.mark.parametrize(
    ("operations", "message"),
    [
        ((), "at least one"),
        (
            (
                operation("op_answer", "model", "first", ()),
                operation("op_answer", "grading", "second", ()),
            ),
            "unique",
        ),
        (
            (operation("op_grade", "grading", "grade", ("op_missing",)),),
            "unknown",
        ),
        (
            (
                operation("op_answer", "model", "answer", ("op_grade",)),
                operation("op_grade", "grading", "grade", ("op_answer",)),
            ),
            "cycle",
        ),
    ],
)
def test_candidate_rejects_an_invalid_operation_dag(
    operations: tuple[Operation, ...],
    message: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        _compiled_candidate(
            name="opus",
            kind="model",
            models=("provider/opus",),
            url4="(@)!'opus'",
            operations=operations,
        )


def test_plan_candidate_collection_is_immutable() -> None:
    plan = evaluation_plan()

    assert plan.candidates.only.name == "opus"


def test_engine_resolved_values_cannot_be_fabricated_through_public_constructors() -> None:
    for value_type in (Operation, Candidate, _Evaluation):
        with pytest.raises(TypeError, match="derived internally"):
            value_type()


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (
            lambda: _compiled_candidate(
                name=" ",
                kind="model",
                models=("provider/opus",),
                url4="(@)!'opus'",
                operations=(),
            ),
            "name",
        ),
        (
            lambda: _compiled_candidate(
                name="opus",
                kind=cast(Any, "ensemble"),
                models=("provider/opus",),
                url4="(@)!'opus'",
                operations=(),
            ),
            "kind",
        ),
        (
            lambda: _compiled_candidate(
                name="opus",
                kind="model",
                models=(),
                url4="(@)!'opus'",
                operations=(),
            ),
            "models",
        ),
        (
            lambda: _compiled_candidate(
                name="opus",
                kind="model",
                models=("provider/opus", "provider/gpt"),
                url4="(@)!'opus'",
                operations=(),
            ),
            "exactly one model route",
        ),
        (
            lambda: _compiled_candidate(
                name="opus",
                kind="model",
                models=("provider/opus", "provider/opus"),
                url4="(@)!'opus'",
                operations=(),
            ),
            "unique",
        ),
        (
            lambda: _compiled_candidate(
                name="opus",
                kind="model",
                models=("provider/opus",),
                url4="not url4",
                operations=(),
            ),
            "valid URL4",
        ),
    ],
)
def test_planned_candidate_rejects_invalid_state(factory: object, message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        cast(Any, factory)()


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"benchmark": object()}, "benchmark"),
        ({"limit": 0}, "limit"),
        ({"case_count": 0}, "case_count"),
        ({"limit": 1, "case_count": 2}, "case_count"),
        ({"required_capabilities": ("web_search", "web_search")}, "unique"),
    ],
)
def test_evaluation_plan_rejects_invalid_state(
    overrides: dict[str, object],
    message: str,
) -> None:
    values: dict[str, object] = {
        "benchmark": sf.BenchmarkInfo(
            name="draco",
            id="draco@1",
            title="DRACO",
            case_count=100,
            primary_metric="normalized_score",
            score_direction="maximize",
        ),
        "limit": 1,
        "case_count": 1,
        "candidates": (planned_candidate(),),
        "required_capabilities": ("web_search",),
        "required_models": ("provider/opus", "provider/judge"),
    }
    values.update(overrides)

    with pytest.raises((TypeError, ValueError), match=message):
        _compiled_evaluation(**cast(Any, values))


def test_evaluate_reports_an_unreachable_manifest_engine() -> None:
    with sf.Client(engine_url="http://127.0.0.1:1") as client:
        with pytest.raises(
            sf.EngineUnavailableError,
            match="Could not reach",
        ):
            client.evaluate(sf.Model("provider/opus"), benchmark="draco", limit=1)


@pytest.mark.asyncio
async def test_async_evaluate_reports_an_unreachable_manifest_engine() -> None:
    async with sf.AsyncClient(engine_url="http://127.0.0.1:1") as client:
        with pytest.raises(
            sf.EngineUnavailableError,
            match="Could not reach",
        ):
            await client.evaluate(sf.Model("provider/opus"), benchmark="draco", limit=1)


@pytest.mark.parametrize("limit", [0, -1])
def test_evaluate_rejects_invalid_limit_values_before_network_work(limit: object) -> None:
    with sf.Client() as client:
        with pytest.raises(ValueError, match="positive integer or None"):
            client.evaluate(
                sf.Model("provider/opus"),
                benchmark="draco",
                limit=cast(Any, limit),
            )


@pytest.mark.parametrize("limit", [True, "all"])
def test_evaluate_rejects_invalid_limit_types_before_network_work(limit: object) -> None:
    with sf.Client() as client:
        with pytest.raises(TypeError, match="positive integer or None"):
            client.evaluate(
                sf.Model("provider/opus"),
                benchmark="draco",
                limit=cast(Any, limit),
            )


def test_evaluate_rejects_duplicate_candidate_names_before_network_work() -> None:
    first = sf.Model("provider/opus", name="same")
    second = sf.Model("provider/gpt", name="same")

    with sf.Client() as client:
        with pytest.raises(ValueError, match="duplicate Candidate name"):
            client.evaluate([first, second], benchmark="draco")


@pytest.mark.parametrize("candidates", [[], [object()], object()])
def test_evaluate_rejects_invalid_candidate_inputs(candidates: object) -> None:
    with sf.Client() as client:
        with pytest.raises((TypeError, ValueError)):
            client.evaluate(cast(Any, candidates), benchmark="draco")


@pytest.mark.parametrize("benchmark", ["", " ", 1])
def test_evaluate_rejects_invalid_benchmark_overrides(benchmark: object) -> None:
    with sf.Client() as client:
        with pytest.raises(ValueError, match="benchmark"):
            client.evaluate(
                sf.Model("provider/opus"),
                benchmark=cast(Any, benchmark),
            )


def test_evaluate_does_not_accept_an_imported_url4() -> None:
    with sf.Client() as client:
        with pytest.raises(TypeError, match="candidates"):
            client.evaluate(cast(Any, "(@)!'hello'"), benchmark="draco")
