"""Versioned engine-side execution of an ordered, shared candidate Recipe DAG."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Mapping
from typing import Any, NoReturn

from url4 import Request, ResolutionError

from screamingface_engine.aggregators import CANDIDATE_CASE_SCHEMA
from screamingface_engine.benchmarks import DRACO_LITE_CANDIDATE_ROUTE, DRACO_LITE_ID
from screamingface_engine.catalog import ModelRoute
from screamingface_engine.draco_grader import DracoRubricGrader
from screamingface_engine.evaluation_events import emit_progress
from screamingface_engine.executor import MODEL_INPUT_SCHEMA, ModelExecutor
from screamingface_engine.reduction import select_majority

CANDIDATE_SPEC_SCHEMA = "screamingface.candidate-spec.v1"
_NODE_ID = re.compile(r"node_([1-9][0-9]*)\Z")
_MEMBER_ID = re.compile(r"member_([1-9][0-9]*)\Z")
_MAX_CANDIDATES = 32
_MAX_NODES = 64


class CandidateEvaluator:
    """Resolve shared candidate roots once and grade only each final answer."""

    def __init__(
        self,
        executor: ModelExecutor,
        model_routes: tuple[ModelRoute, ...],
        grader: DracoRubricGrader,
        *,
        case_concurrency: int = 10,
        synthesis_concurrency: int = 16,
    ) -> None:
        self._executor = executor
        self._models = {model.id: model for model in model_routes}
        self._grader = grader
        self._case_semaphore = asyncio.Semaphore(case_concurrency)
        self._synthesis_semaphore = asyncio.Semaphore(synthesis_concurrency)

    async def __call__(self, request: Request) -> str:
        if request.path != DRACO_LITE_CANDIDATE_ROUTE:
            _invalid("candidate evaluator received an unexpected route")
        if request.params:
            _invalid(f"candidate evaluator does not accept parameters: {sorted(request.params)}")
        specification = _specification(request.context)
        case = _case(request.intent)
        if case["benchmark_id"] != DRACO_LITE_ID:
            _invalid(f"candidate evaluator requires benchmark {DRACO_LITE_ID!r}")
        async with self._case_semaphore:
            return await _CandidateRun(
                self._executor,
                self._models,
                self._grader,
                self._synthesis_semaphore,
                specification,
                case,
            ).evaluate()


class _CandidateRun:
    def __init__(
        self,
        executor: ModelExecutor,
        models: Mapping[str, ModelRoute],
        grader: DracoRubricGrader,
        synthesis_semaphore: asyncio.Semaphore,
        specification: Mapping[str, object],
        case: Mapping[str, object],
    ) -> None:
        nodes = specification["nodes"]
        candidates = specification["candidates"]
        assert isinstance(nodes, Mapping)
        assert isinstance(candidates, Mapping)
        self._executor = executor
        self._models = models
        self._grader = grader
        self._synthesis_semaphore = synthesis_semaphore
        self._nodes = nodes
        self._candidates = candidates
        self._case = case
        self._question = _nonblank(case["question"], "candidate case question", strip=False)
        self._model_input = json.dumps(
            {
                "schema": MODEL_INPUT_SCHEMA,
                "question": self._question,
                "tool_policy": case["tool_policy"],
            },
            allow_nan=False,
            separators=(",", ":"),
        )
        self._tasks: dict[str, asyncio.Task[str]] = {}

    async def evaluate(self) -> str:
        entries = tuple(_candidate_entry(slot, raw) for slot, raw in self._candidates.items())
        root_tasks = [self._resolve(root) for _name, root in entries]
        roots = await asyncio.gather(*root_tasks, return_exceptions=True)
        grades = await asyncio.gather(
            *(
                self._grade(candidate_name, outcome)
                for (candidate_name, _root), outcome in zip(entries, roots, strict=True)
            )
        )
        results = {
            candidate_name: grade
            for (candidate_name, _root), grade in zip(entries, grades, strict=True)
        }
        payload = {
            "schema": CANDIDATE_CASE_SCHEMA,
            "benchmark_id": self._case["benchmark_id"],
            "case_id": self._case["case_id"],
            "candidates": results,
        }
        return json.dumps(payload, allow_nan=False, separators=(",", ":"))

    async def _resolve(self, node_id: str) -> str:
        task = self._tasks.get(node_id)
        if task is None:
            task = asyncio.create_task(self._execute(node_id))
            self._tasks[node_id] = task
        return await task

    async def _execute(self, node_id: str) -> str:
        raw = self._nodes[node_id]
        assert isinstance(raw, Mapping)
        name = _nonblank(raw["name"], f"candidate node {node_id} name")
        if raw["kind"] == "model":
            return await self._execute_model(node_id, name, raw)
        return await self._execute_fusion(node_id, name, raw)

    async def _execute_model(self, node_id: str, name: str, raw: Mapping[str, object]) -> str:
        model = self._model(raw["model"])
        operation_id = self._operation_id("model", node_id)
        emit_progress(
            "model",
            "started",
            f"Running {name} ({model.id})",
            operation_id=operation_id,
        )
        try:
            answer = await self._executor.complete(
                model,
                Request(
                    model.route,
                    self._model_input,
                    _nonblank(raw["prompt"], f"candidate node {node_id} prompt", strip=False),
                    _params(raw["params"], f"candidate node {node_id} params"),
                ),
            )
        except BaseException:
            emit_progress(
                "model",
                "failed",
                f"Failed {name} ({model.id})",
                operation_id=operation_id,
            )
            raise
        emit_progress(
            "model",
            "completed",
            f"Completed {name} ({model.id})",
            operation_id=operation_id,
        )
        return answer

    async def _execute_fusion(self, node_id: str, name: str, raw: Mapping[str, object]) -> str:
        members = raw["members"]
        reducer = raw["reducer"]
        assert isinstance(members, Mapping) and isinstance(reducer, Mapping)
        resolved = await asyncio.gather(
            *(
                self._resolve(_nonblank(value, f"candidate node {node_id} member"))
                for value in members.values()
            ),
            return_exceptions=True,
        )
        failure = next((value for value in resolved if isinstance(value, BaseException)), None)
        if failure is not None:
            raise failure
        answers = tuple(str(value) for value in resolved)
        if reducer["kind"] == "majority_vote":
            return select_majority(answers)
        return await self._synthesize(node_id, name, members, reducer, answers)

    async def _synthesize(
        self,
        node_id: str,
        name: str,
        members: Mapping[str, object],
        reducer: Mapping[str, object],
        answers: tuple[str, ...],
    ) -> str:
        model = self._model(reducer["model"])
        operation_id = self._operation_id("synthesis", node_id)
        emit_progress(
            "synthesis",
            "started",
            f"Synthesizing {name} with {model.id}",
            operation_id=operation_id,
        )
        try:
            async with self._synthesis_semaphore:
                answer = await self._executor.complete(
                    model,
                    Request(
                        model.route,
                        _reducer_context(self._question, members, self._nodes, answers),
                        _nonblank(
                            reducer["prompt"],
                            f"candidate node {node_id} reducer prompt",
                            strip=False,
                        ),
                        _params(reducer["params"], f"candidate node {node_id} reducer params"),
                    ),
                )
        except BaseException:
            emit_progress(
                "synthesis",
                "failed",
                f"Failed synthesis for {name} ({model.id})",
                operation_id=operation_id,
            )
            raise
        emit_progress(
            "synthesis",
            "completed",
            f"Synthesized {name} with {model.id}",
            operation_id=operation_id,
        )
        return answer

    async def _grade(self, name: str, outcome: str | BaseException) -> dict[str, object]:
        operation_id = self._operation_id("grading", name)
        if isinstance(outcome, BaseException):
            emit_progress(
                "grading",
                "skipped",
                f"Scoring unavailable for {name}: required answer unavailable",
                operation_id=operation_id,
            )
            return _failed(outcome)
        try:
            emit_progress("grading", "started", f"Grading {name}", operation_id=operation_id)
            grade = await self._grader.grade_answer(
                self._question, self._case["reference"], outcome
            )
        except BaseException as exc:
            emit_progress(
                "grading",
                "failed",
                f"Failed grading {name}: {exc}",
                operation_id=operation_id,
            )
            return _failed(exc)
        emit_progress("grading", "completed", f"Graded {name}", operation_id=operation_id)
        return {"score": grade["score"], "metrics": grade["metrics"], "failure": None}

    def _operation_id(self, stage: str, value: str) -> str:
        return f"{self._case['case_id']}:{stage}:{value}"

    def _model(self, value: object) -> ModelRoute:
        model_id = _nonblank(value, "candidate model ID")
        route = self._models.get(model_id)
        if route is None:
            raise ResolutionError(
                f"candidate model {model_id!r} is not registered",
                code="model_unavailable",
                permanent=True,
            )
        return route


def _specification(text: str) -> dict[str, object]:
    value = _object(text, "candidate specification")
    _exact_fields(value, {"schema", "nodes", "candidates"}, "candidate specification")
    if value["schema"] != CANDIDATE_SPEC_SCHEMA:
        _invalid(f"expected candidate specification schema {CANDIDATE_SPEC_SCHEMA!r}")
    nodes = value["nodes"]
    candidates = value["candidates"]
    if not isinstance(nodes, Mapping) or not 1 <= len(nodes) <= _MAX_NODES:
        _invalid(f"candidate specification nodes must contain 1 to {_MAX_NODES} entries")
    if not isinstance(candidates, Mapping) or not 1 <= len(candidates) <= _MAX_CANDIDATES:
        _invalid(f"candidate specification candidates must contain 1 to {_MAX_CANDIDATES} entries")
    expected_nodes = tuple(f"node_{position}" for position in range(1, len(nodes) + 1))
    if tuple(nodes) != expected_nodes:
        _invalid("candidate specification nodes must be contiguous node_1 through node_n")
    for node_id, raw in nodes.items():
        _node(str(node_id), raw, nodes)
    expected_candidates = tuple(
        f"candidate_{position}" for position in range(1, len(candidates) + 1)
    )
    if tuple(candidates) != expected_candidates:
        _invalid(
            "candidate specification candidates must be contiguous candidate_1 through candidate_n"
        )
    names: set[str] = set()
    for slot, raw in candidates.items():
        name, root = _candidate_entry(str(slot), raw)
        if name in names:
            _invalid(f"candidate specification contains duplicate name {name!r}")
        names.add(name)
        if root not in nodes:
            _invalid(f"candidate {slot!r} references an unknown root")
    _acyclic(nodes, candidates)
    return value


def _node(node_id: str, raw: object, nodes: Mapping[str, object]) -> None:
    if _NODE_ID.fullmatch(node_id) is None or not isinstance(raw, Mapping):
        _invalid("candidate specification contains an invalid node")
    kind = raw.get("kind")
    if kind == "model":
        _model_node(node_id, raw)
    elif kind == "fusion":
        _fusion_node(node_id, raw, nodes)
    else:
        _invalid(f"{node_id} has an unsupported kind")
    _nonblank(raw["name"], f"{node_id} name")


def _model_node(node_id: str, raw: Mapping[str, object]) -> None:
    _exact_fields(raw, {"kind", "name", "model", "prompt", "params"}, node_id)
    _nonblank(raw["model"], f"{node_id} model")
    _nonblank(raw["prompt"], f"{node_id} prompt", strip=False)
    _params(raw["params"], f"{node_id} params")


def _fusion_node(node_id: str, raw: Mapping[str, object], nodes: Mapping[str, object]) -> None:
    _exact_fields(raw, {"kind", "name", "members", "reducer"}, node_id)
    members = raw["members"]
    if not isinstance(members, Mapping) or not members:
        _invalid(f"{node_id} members must be a non-empty object")
    expected = tuple(f"member_{position}" for position in range(1, len(members) + 1))
    if tuple(members) != expected:
        _invalid(f"{node_id} members must be contiguous member_1 through member_n")
    for member_id, reference in members.items():
        if _MEMBER_ID.fullmatch(str(member_id)) is None or reference not in nodes:
            _invalid(f"{node_id} contains an invalid member reference")
    _reducer(node_id, raw["reducer"], len(members))


def _reducer(node_id: str, raw: object, member_count: int) -> None:
    if not isinstance(raw, Mapping):
        _invalid(f"{node_id} reducer must be an object")
    if raw.get("kind") == "model":
        _exact_fields(raw, {"kind", "model", "prompt", "params"}, f"{node_id} reducer")
        _nonblank(raw["model"], f"{node_id} reducer model")
        _nonblank(raw["prompt"], f"{node_id} reducer prompt", strip=False)
        _params(raw["params"], f"{node_id} reducer params")
        return
    if raw.get("kind") == "majority_vote":
        _exact_fields(raw, {"kind"}, f"{node_id} reducer")
        if member_count < 2:
            _invalid(f"{node_id} majority vote requires at least two members")
        return
    _invalid(f"{node_id} has an unsupported reducer")


def _acyclic(nodes: Mapping[str, object], candidates: Mapping[str, object]) -> None:
    visited: set[str] = set()
    active: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in active:
            _invalid(f"candidate specification contains a cycle at {node_id!r}")
        if node_id in visited:
            return
        active.add(node_id)
        node = nodes[node_id]
        assert isinstance(node, Mapping)
        members = node.get("members", {})
        assert isinstance(members, Mapping)
        for reference in members.values():
            visit(str(reference))
        active.remove(node_id)
        visited.add(node_id)

    for slot, raw in candidates.items():
        _name, root = _candidate_entry(str(slot), raw)
        visit(root)


def _candidate_entry(slot: str, raw: object) -> tuple[str, str]:
    if not isinstance(raw, Mapping):
        _invalid(f"candidate {slot!r} must be an object")
    _exact_fields(raw, {"name", "root"}, f"candidate {slot!r}")
    return (
        _nonblank(raw["name"], f"candidate {slot!r} name"),
        _nonblank(raw["root"], f"candidate {slot!r} root"),
    )


def _case(text: str) -> dict[str, object]:
    value = _object(text, "candidate case")
    _exact_fields(
        value,
        {"benchmark_id", "case_id", "question", "reference", "tool_policy"},
        "candidate case",
    )
    _nonblank(value["benchmark_id"], "candidate benchmark ID")
    _nonblank(value["case_id"], "candidate case ID")
    _nonblank(value["question"], "candidate case question", strip=False)
    value["reference"] = _resolved_object(value["reference"], "candidate case reference")
    value["tool_policy"] = _resolved_object(value["tool_policy"], "candidate case tool policy")
    return value


def _resolved_object(value: object, label: str) -> dict[str, object]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, dict):
            return decoded
    _invalid(f"{label} must be an object")


def _reducer_context(
    question: str,
    members: Mapping[str, object],
    nodes: Mapping[str, object],
    answers: tuple[str, ...],
) -> str:
    sections: list[str] = []
    for position, (reference, answer) in enumerate(zip(members.values(), answers, strict=True), 1):
        raw = nodes[str(reference)]
        assert isinstance(raw, Mapping)
        label = _nonblank(raw["name"], "candidate member name")
        sections.append(f"Panel {position} [{label}]:\n{answer}")
    return "Question:\n" + question + "\n\nPanel answers:\n" + "\n\n".join(sections)


def _failed(exc: BaseException) -> dict[str, object]:
    code = exc.code if isinstance(exc, ResolutionError) else "resolution_failed"
    kind = "url4"
    if code == "gateway_timeout":
        kind = "timeout"
    elif code in {
        "authentication_required",
        "connection_needs_reauth",
        "connection_pending",
        "provider_access_denied",
    }:
        kind = "connection"
    return {
        "score": None,
        "metrics": {},
        "failure": {
            "kind": kind,
            "message": str(exc) or type(exc).__name__,
            "status": None,
            "code": code,
        },
    }


def _params(value: object, label: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        _invalid(f"{label} must be an object")
    values: dict[str, str] = {}
    for key, item in value.items():
        name = _nonblank(key, f"{label} name")
        values[name] = _nonblank(item, f"{label} {name!r}", strip=False)
    return values


def _object(text: str, label: str) -> dict[str, object]:
    try:
        value: Any = json.loads(text)
    except json.JSONDecodeError:
        _invalid(f"{label} must be a JSON object")
    if not isinstance(value, dict):
        _invalid(f"{label} must be a JSON object")
    return value


def _exact_fields(value: Mapping[str, object], expected: set[str], label: str) -> None:
    if set(value) != expected:
        _invalid(f"{label} fields must be exactly {sorted(expected)}")


def _nonblank(value: object, label: str, *, strip: bool = True) -> str:
    if not isinstance(value, str) or not value.strip():
        _invalid(f"{label} must be a non-blank string")
    return value.strip() if strip else value


def _invalid(message: str) -> NoReturn:
    raise ResolutionError(message, code="malformed_source", permanent=True)


__all__ = ["CANDIDATE_SPEC_SCHEMA", "CandidateEvaluator"]
