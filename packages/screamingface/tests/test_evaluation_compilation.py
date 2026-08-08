from __future__ import annotations

from typing import Any, cast

import pytest

import screamingface as sf
from screamingface._evaluation.model import (
    Candidate,
    _compiled_candidate,
    _compiled_evaluation,
    _compiled_operation,
    _Evaluation,
    _member_projection,
    _model_parameter_assignment,
)
from screamingface.operation import OperationInfo


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
            id="draco@1",
            revision="fixture-revision",
            case_count=100,
        ),
        limit=1,
        case_count=1,
        candidates=candidates or (planned_candidate(),),
        required_models=("provider/opus", "provider/judge"),
    )


def operation(
    id: str,
    kind: str,
    label: str,
    depends_on: tuple[str, ...],
) -> OperationInfo:
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
    operations: tuple[OperationInfo, ...],
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
    for value_type in (Candidate, _Evaluation):
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


def test_compiled_candidate_rejects_inconsistent_member_state() -> None:
    answer = operation("op_answer", "model", "answer", ())
    member = _member_projection(
        operation_id="op_answer",
        name="member",
        kind="model",
        models=("provider/member",),
    )

    with pytest.raises(TypeError, match="member projections"):
        _compiled_candidate(
            name="pair",
            kind="fusion",
            models=("provider/member",),
            url4="(@)!'pair'",
            operations=(answer,),
            members=cast(Any, (object(), object())),
        )
    with pytest.raises(ValueError, match="cannot contain members"):
        _compiled_candidate(
            name="model",
            kind="model",
            models=("provider/member",),
            url4="(@)!'model'",
            operations=(answer,),
            members=(member,),
        )
    with pytest.raises(ValueError, match="at least two direct members"):
        _compiled_candidate(
            name="pair",
            kind="fusion",
            models=("provider/member",),
            url4="(@)!'pair'",
            operations=(answer,),
            members=(member,),
        )


def test_compiled_candidate_rejects_unknown_operation_references() -> None:
    answer = operation("op_answer", "model", "answer", ())
    unknown_member = _member_projection(
        operation_id="op_missing",
        name="member",
        kind="model",
        models=("provider/member",),
    )
    assignment = _model_parameter_assignment(
        operation_id="op_missing",
        model="provider/member",
        params={"temperature": 0.2},
    )

    with pytest.raises(ValueError, match="unknown selected Operation ID"):
        _compiled_candidate(
            name="model",
            kind="model",
            models=("provider/member",),
            url4="(@)!'model'",
            operations=(answer,),
            known_operation_ids=("op_other",),
        )
    with pytest.raises(ValueError, match="member has unknown Operation ID"):
        _compiled_candidate(
            name="pair",
            kind="fusion",
            models=("provider/member",),
            url4="(@)!'pair'",
            operations=(answer,),
            members=(unknown_member, unknown_member),
        )
    with pytest.raises(ValueError, match="assignment has unknown Operation ID"):
        _compiled_candidate(
            name="model",
            kind="model",
            models=("provider/member",),
            url4="(@)!'model'",
            operations=(answer,),
            parameter_assignments=(assignment,),
        )


def test_compiled_candidate_rejects_invalid_parameter_assignments() -> None:
    answer = operation("op_answer", "model", "answer", ())

    with pytest.raises(ValueError, match="must not be empty"):
        _model_parameter_assignment(
            operation_id="op_answer",
            model="provider/member",
            params={},
        )
    with pytest.raises(TypeError, match="compiled assignments"):
        _compiled_candidate(
            name="model",
            kind="model",
            models=("provider/member",),
            url4="(@)!'model'",
            operations=(answer,),
            parameter_assignments=cast(Any, (object(),)),
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"benchmark": object()}, "benchmark"),
        ({"limit": 0}, "limit"),
        ({"case_count": False}, "case_count"),
        ({"case_count": 0}, "case_count"),
        ({"limit": 1, "case_count": 2}, "case_count"),
    ],
)
def test_evaluation_plan_rejects_invalid_state(
    overrides: dict[str, object],
    message: str,
) -> None:
    values: dict[str, object] = {
        "benchmark": sf.BenchmarkInfo(
            id="draco@1",
            revision="fixture-revision",
            case_count=100,
        ),
        "limit": 1,
        "case_count": 1,
        "candidates": (planned_candidate(),),
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


@pytest.mark.parametrize("benchmark", ["", " ", "default", 1])
def test_evaluate_rejects_invalid_benchmark_ids(benchmark: object) -> None:
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
