from __future__ import annotations

import asyncio
import json
from typing import Any, cast

import httpx
import pytest
import screamingface as sf
from screamingface._compiler import compile_candidates_benchmark_expression
from url4 import Request, ResolutionError, Url4Node

from screamingface_engine.aggregators import (
    CANDIDATE_CASE_SCHEMA,
    CANDIDATE_MEAN_ROUTE,
    STUDY_REPORT_SCHEMA,
    candidate_mean,
)
from screamingface_engine.benchmarks import DRACO_LITE_CANDIDATE_ROUTE
from screamingface_engine.candidate_evaluator import CandidateEvaluator
from screamingface_engine.candidate_evaluator import _failed as candidate_failure
from screamingface_engine.catalog import ModelRoute
from screamingface_engine.draco_grader import DracoRubricGrader
from screamingface_engine.evaluation_events import evaluation_event_sink
from screamingface_engine.executor import ModelExecutor

MODEL_A = ModelRoute("openrouter/a/a", "openrouter/a/a", "openrouter")
MODEL_B = ModelRoute("openrouter/b/b", "openrouter/b/b", "openrouter")


class Executor:
    def __init__(self, *, fail_model: str | None = None) -> None:
        self.fail_model = fail_model
        self.calls: list[tuple[str, str]] = []

    async def complete(self, model: ModelRoute, request: Request) -> str:
        self.calls.append((model.id, request.intent))
        if self.fail_model == model.id:
            raise ResolutionError("temporary provider failure", code="provider_unavailable")
        return f"answer-{len(self.calls)}"


class Grader:
    def __init__(self) -> None:
        self.answers: list[str] = []

    async def grade_answer(
        self, question: str, reference: object, answer: str
    ) -> dict[str, object]:
        assert question == "Question"
        assert isinstance(reference, dict)
        self.answers.append(answer)
        return {"score": 0.5, "metrics": {"normalized_score": 0.5}}


class BlockingGrader(Grader):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def grade_answer(
        self, question: str, reference: object, answer: str
    ) -> dict[str, object]:
        self.answers.append(answer)
        if len(self.answers) == 3:
            self.started.set()
        await self.release.wait()
        return {"score": 0.5, "metrics": {"normalized_score": 0.5}}


def _spec(*, independent_duplicate: bool = False) -> dict[str, object]:
    nodes: dict[str, object] = {
        "node_1": {
            "kind": "model",
            "name": "a",
            "model": MODEL_A.id,
            "prompt": "Answer",
            "params": {"temperature": "0"},
        },
        "node_2": {
            "kind": "model",
            "name": "b",
            "model": MODEL_B.id,
            "prompt": "Answer",
            "params": {"temperature": "0"},
        },
        "node_3": {
            "kind": "fusion",
            "name": "pair",
            "members": {"member_1": "node_1", "member_2": "node_2"},
            "reducer": {
                "kind": "model",
                "model": MODEL_A.id,
                "prompt": "Synthesize",
                "params": {"temperature": "0"},
            },
        },
    }
    candidates: dict[str, object] = {
        "candidate_1": {"name": "a", "root": "node_1"},
        "candidate_2": {"name": "b", "root": "node_2"},
        "candidate_3": {"name": "pair", "root": "node_3"},
    }
    if independent_duplicate:
        nodes["node_4"] = dict(cast(dict[str, object], nodes["node_1"]), name="a-sample-2")
        candidates["candidate_4"] = {"name": "a-sample-2", "root": "node_4"}
    return {
        "schema": "screamingface.candidate-spec.v1",
        "nodes": nodes,
        "candidates": candidates,
    }


def _case() -> dict[str, object]:
    return {
        "benchmark_id": "draco-lite@1",
        "case_id": "case-1",
        "question": "Question",
        "reference": {"sections": [{"criteria": [{"id": "c", "weight": 1}]}]},
        "tool_policy": {"schema": "screamingface.tool-policy.v1"},
    }


async def _evaluate(
    executor: Executor, grader: Grader, *, independent_duplicate: bool = False
) -> dict[str, object]:
    evaluator = CandidateEvaluator(
        cast(ModelExecutor, executor),
        (MODEL_A, MODEL_B),
        cast(DracoRubricGrader, grader),
    )
    raw = await evaluator(
        Request(
            DRACO_LITE_CANDIDATE_ROUTE,
            json.dumps(_spec(independent_duplicate=independent_duplicate)),
            json.dumps(_case()),
            {},
        )
    )
    return cast(dict[str, object], json.loads(raw))


def _evaluator(
    executor: Executor | None = None, grader: Grader | None = None
) -> CandidateEvaluator:
    return CandidateEvaluator(
        cast(ModelExecutor, executor or Executor()),
        (MODEL_A, MODEL_B),
        cast(DracoRubricGrader, grader or Grader()),
    )


@pytest.mark.asyncio
async def test_shared_nodes_execute_once_and_only_final_candidates_are_graded() -> None:
    executor = Executor()
    grader = Grader()

    payload = await _evaluate(executor, grader)

    assert payload["schema"] == CANDIDATE_CASE_SCHEMA
    assert len(executor.calls) == 3  # two shared leaves + one synthesis
    assert len(grader.answers) == 3  # three final candidates, never Fusion members again


@pytest.mark.asyncio
async def test_independent_candidate_grades_start_concurrently() -> None:
    grader = BlockingGrader()
    task = asyncio.create_task(_evaluate(Executor(), grader))

    await asyncio.wait_for(grader.started.wait(), timeout=1)
    assert len(grader.answers) == 3
    grader.release.set()
    await task


@pytest.mark.asyncio
async def test_candidate_operations_have_stable_ids_and_distinct_stages() -> None:
    events: list[dict[str, object]] = []

    with evaluation_event_sink(events.append):
        await _evaluate(Executor(), Grader())

    assert any(
        event
        == {
            "stage": "model",
            "status": "started",
            "label": "Running a (openrouter/a/a)",
            "operation_id": "case-1:model:node_1",
        }
        for event in events
    )
    assert any(
        event["stage"] == "synthesis"
        and event["status"] == "completed"
        and event["operation_id"] == "case-1:synthesis:node_3"
        for event in events
    )
    assert sum(event["stage"] == "grading" for event in events) == 6


@pytest.mark.asyncio
async def test_independent_equal_model_nodes_remain_two_calls() -> None:
    executor = Executor()
    grader = Grader()

    await _evaluate(executor, grader, independent_duplicate=True)

    calls = [
        model for model, prompt in executor.calls if model == MODEL_A.id and prompt == "Answer"
    ]
    assert calls == [
        MODEL_A.id,
        MODEL_A.id,
    ]


@pytest.mark.asyncio
async def test_one_failed_dependency_does_not_discard_unrelated_candidate() -> None:
    payload = await _evaluate(Executor(fail_model=MODEL_B.id), Grader())
    candidates = cast(dict[str, dict[str, object]], payload["candidates"])

    assert candidates["a"]["score"] == 0.5
    assert candidates["b"]["failure"] == {
        "kind": "url4",
        "message": "temporary provider failure",
        "status": None,
        "code": "provider_unavailable",
    }
    assert cast(dict[str, object], candidates["pair"]["failure"])["code"] == "provider_unavailable"


def test_candidate_aggregator_preserves_order_and_partial_failures() -> None:
    case = {
        "schema": CANDIDATE_CASE_SCHEMA,
        "benchmark_id": "draco-lite@1",
        "case_id": "case-1",
        "candidates": {
            "a": {"score": 0.5, "metrics": {"normalized_score": 0.5}, "failure": None},
            "b": {
                "score": None,
                "metrics": {},
                "failure": {
                    "kind": "url4",
                    "message": "failed",
                    "status": None,
                    "code": "provider_unavailable",
                },
            },
        },
    }

    events: list[dict[str, object]] = []
    with evaluation_event_sink(events.append):
        raw = candidate_mean(Request(CANDIDATE_MEAN_ROUTE, "", json.dumps([case]), {}))
    payload = cast(dict[str, Any], json.loads(raw))

    assert payload["schema"] == STUDY_REPORT_SCHEMA
    assert list(payload["candidates"]) == ["a", "b"]
    assert payload["candidates"]["a"]["score"] == 0.5
    assert payload["candidates"]["b"]["n_scored"] == 0
    assert payload["complete"] is False
    finalized = [event for event in events if event["stage"] == "candidate"]
    assert [(event["status"], event["operation_id"]) for event in finalized] == [
        ("completed", "candidate:a"),
        ("skipped", "candidate:b"),
    ]
    assert finalized[1]["label"] == "Unavailable b (0/1 cases scored)"


@pytest.mark.asyncio
async def test_majority_vote_candidate_is_reduced_without_an_extra_model_call() -> None:
    specification = _spec()
    nodes = cast(dict[str, dict[str, object]], specification["nodes"])
    nodes["node_3"]["reducer"] = {"kind": "majority_vote"}
    executor = Executor()
    raw = await _evaluator(executor)(
        Request(
            DRACO_LITE_CANDIDATE_ROUTE,
            json.dumps(specification),
            json.dumps(_case()),
            {},
        )
    )

    assert json.loads(raw)["candidates"]["pair"]["score"] == 0.5
    assert len(executor.calls) == 2


@pytest.mark.asyncio
async def test_candidate_route_and_parameters_are_strict() -> None:
    evaluator = _evaluator()
    with pytest.raises(ResolutionError, match="unexpected route"):
        await evaluator(Request("/wrong", json.dumps(_spec()), json.dumps(_case()), {}))
    with pytest.raises(ResolutionError, match="does not accept parameters"):
        await evaluator(
            Request(
                DRACO_LITE_CANDIDATE_ROUTE,
                json.dumps(_spec()),
                json.dumps(_case()),
                {"extra": "1"},
            )
        )

    case = _case()
    case["benchmark_id"] = "other@1"
    with pytest.raises(ResolutionError, match="requires benchmark"):
        await evaluator(
            Request(
                DRACO_LITE_CANDIDATE_ROUTE,
                json.dumps(_spec()),
                json.dumps(case),
                {},
            )
        )


@pytest.mark.asyncio
async def test_candidate_case_decodes_objects_interpolated_by_url4_structs() -> None:
    case = _case()
    case["reference"] = json.dumps(case["reference"])
    case["tool_policy"] = json.dumps(case["tool_policy"])

    raw = await _evaluator()(
        Request(
            DRACO_LITE_CANDIDATE_ROUTE,
            json.dumps(_spec()),
            json.dumps(case),
            {},
        )
    )

    assert json.loads(raw)["schema"] == CANDIDATE_CASE_SCHEMA


@pytest.mark.asyncio
async def test_complete_url4_preserves_hyphenated_names_and_nested_case_objects() -> None:
    node = Url4Node("candidate-integration", eval_path="/v1")
    node.endpoint(DRACO_LITE_CANDIDATE_ROUTE)(_evaluator())
    node.endpoint(CANDIDATE_MEAN_ROUTE)(candidate_mean)
    source_case = _case()
    node.data(
        "/cases",
        json.dumps(
            {
                "id": source_case["case_id"],
                "input": source_case["question"],
                "reference": source_case["reference"],
            }
        ),
        media_type="application/x-ndjson",
    )
    node.data(
        "/tool-policy",
        json.dumps(source_case["tool_policy"]),
        media_type="application/json",
    )
    candidate = sf.Model(MODEL_A.id, name="claude-fable-5", prompt="Answer")
    expression = compile_candidates_benchmark_expression(
        benchmark_id="draco-lite@1",
        cases_route="/cases",
        candidate_route=DRACO_LITE_CANDIDATE_ROUTE,
        aggregator_route=CANDIDATE_MEAN_ROUTE,
        candidates=(candidate,),
        tool_policy_route="/tool-policy",
        first=1,
    )

    transport = httpx.ASGITransport(app=node.asgi())
    async with httpx.AsyncClient(transport=transport, base_url="http://engine.test") as client:
        response = await client.get("/v1", params={"q": expression})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["schema"] == STUDY_REPORT_SCHEMA
    assert tuple(payload["candidates"]) == ("claude-fable-5",)
    assert payload["candidates"]["claude-fable-5"]["score"] == 0.5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda spec: spec.update(schema="wrong"), "expected candidate specification schema"),
        (lambda spec: spec.update(nodes={}), "nodes must contain"),
        (lambda spec: spec.update(candidates={}), "candidates must contain"),
        (
            lambda spec: cast(dict[str, object], spec["nodes"]).update(
                {"node_5": cast(dict[str, object], spec["nodes"])["node_1"]}
            ),
            "contiguous",
        ),
        (
            lambda spec: cast(dict[str, dict[str, object]], spec["nodes"])["node_1"].update(
                kind="unknown"
            ),
            "unsupported kind",
        ),
        (
            lambda spec: cast(dict[str, dict[str, object]], spec["nodes"])["node_3"].update(
                members={}
            ),
            "non-empty object",
        ),
        (
            lambda spec: cast(dict[str, dict[str, object]], spec["nodes"])["node_3"].update(
                reducer={"kind": "unknown"}
            ),
            "unsupported reducer",
        ),
        (
            lambda spec: cast(dict[str, dict[str, object]], spec["candidates"])[
                "candidate_1"
            ].update(root="missing"),
            "unknown root",
        ),
        (
            lambda spec: cast(dict[str, dict[str, object]], spec["candidates"])[
                "candidate_2"
            ].update(name="a"),
            "duplicate name",
        ),
        (
            lambda spec: (
                lambda candidates: candidates.__setitem__(
                    "candidate_4", candidates.pop("candidate_1")
                )
            )(cast(dict[str, object], spec["candidates"])),
            "contiguous candidate",
        ),
        (
            lambda spec: cast(dict[str, object], spec["candidates"]).update(candidate_1="node_1"),
            "must be an object",
        ),
        (
            lambda spec: cast(dict[str, dict[str, object]], spec["nodes"])["node_1"].update(
                params=[]
            ),
            "must be an object",
        ),
        (
            lambda spec: cast(dict[str, dict[str, object]], spec["nodes"])["node_3"].update(
                reducer=[]
            ),
            "reducer must be an object",
        ),
        (
            lambda spec: cast(dict[str, dict[str, object]], spec["nodes"])["node_3"].update(
                members={"member_2": "node_1"}
            ),
            "contiguous member",
        ),
    ],
)
async def test_candidate_specification_rejects_malformed_graphs(mutate, message: str) -> None:
    specification = _spec()
    mutate(specification)
    with pytest.raises(ResolutionError, match=message):
        await _evaluator()(
            Request(
                DRACO_LITE_CANDIDATE_ROUTE,
                json.dumps(specification),
                json.dumps(_case()),
                {},
            )
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("context", "message"),
    [("not-json", "JSON object"), ("[]", "JSON object"), ("{}", "fields must be exactly")],
)
async def test_candidate_specification_requires_one_strict_json_object(
    context: str, message: str
) -> None:
    with pytest.raises(ResolutionError, match=message):
        await _evaluator()(Request(DRACO_LITE_CANDIDATE_ROUTE, context, json.dumps(_case()), {}))


def test_candidate_failures_classify_timeout_and_connections() -> None:
    timeout = candidate_failure(ResolutionError("slow", code="gateway_timeout"))
    connection = candidate_failure(
        ResolutionError("connect", code="authentication_required", permanent=True)
    )

    timeout_failure = cast(dict[str, object], timeout["failure"])
    connection_failure = cast(dict[str, object], connection["failure"])
    assert timeout_failure["kind"] == "timeout"
    assert connection_failure["kind"] == "connection"


def test_candidate_aggregator_means_two_rows() -> None:
    first = {
        "schema": CANDIDATE_CASE_SCHEMA,
        "benchmark_id": "draco-lite@1",
        "case_id": "case-1",
        "candidates": {
            "a": {"score": 0.25, "metrics": {"normalized_score": 0.25}, "failure": None}
        },
    }
    second = {
        **first,
        "case_id": "case-2",
        "candidates": {
            "a": {"score": 0.75, "metrics": {"normalized_score": 0.75}, "failure": None}
        },
    }

    payload = json.loads(
        candidate_mean(Request(CANDIDATE_MEAN_ROUTE, "", json.dumps([first, second]), {}))
    )

    assert payload["case_ids"] == ["case-1", "case-2"]
    assert payload["candidates"]["a"]["score"] == 0.5
    assert payload["candidates"]["a"]["coverage"] == 1.0


def test_candidate_aggregator_rejects_whole_case_iteration_errors() -> None:
    with pytest.raises(ResolutionError, match="case failed"):
        candidate_mean(
            Request(
                CANDIDATE_MEAN_ROUTE,
                "",
                json.dumps([{"error": {"kind": "resolution", "message": "case failed"}}]),
                {},
            )
        )


def test_candidate_aggregator_rejects_context_params_and_inconsistent_rows() -> None:
    with pytest.raises(ResolutionError, match="does not accept context"):
        candidate_mean(Request(CANDIDATE_MEAN_ROUTE, "context", "[]", {}))
    with pytest.raises(ResolutionError, match="does not accept parameters"):
        candidate_mean(Request(CANDIDATE_MEAN_ROUTE, "", "[]", {"x": "1"}))

    row = {
        "schema": CANDIDATE_CASE_SCHEMA,
        "benchmark_id": "draco-lite@1",
        "case_id": "case-1",
        "candidates": {"a": {"score": 0.5, "metrics": {}, "failure": None}},
    }
    other_benchmark = {**row, "benchmark_id": "other@1", "case_id": "case-2"}
    with pytest.raises(ResolutionError, match="benchmark ID"):
        candidate_mean(Request(CANDIDATE_MEAN_ROUTE, "", json.dumps([row, other_benchmark]), {}))
    other_order = {
        **row,
        "case_id": "case-2",
        "candidates": {
            "b": {"score": 0.5, "metrics": {}, "failure": None},
            "a": {"score": 0.5, "metrics": {}, "failure": None},
        },
    }
    with pytest.raises(ResolutionError, match="candidate order"):
        candidate_mean(Request(CANDIDATE_MEAN_ROUTE, "", json.dumps([row, other_order]), {}))


@pytest.mark.parametrize(
    ("row", "message"),
    [
        ({"schema": "wrong"}, "is not"),
        (
            {
                "schema": CANDIDATE_CASE_SCHEMA,
                "benchmark_id": "draco-lite@1",
                "case_id": "case-1",
                "candidates": {},
            },
            "non-empty object",
        ),
    ],
)
def test_candidate_aggregator_rejects_malformed_case_rows(
    row: dict[str, object], message: str
) -> None:
    with pytest.raises(ResolutionError, match=message):
        candidate_mean(Request(CANDIDATE_MEAN_ROUTE, "", json.dumps([row]), {}))
