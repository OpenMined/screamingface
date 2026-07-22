"""Composition root for the persistent ScreamingFace URL4 engine."""

from __future__ import annotations

import asyncio
import json

from url4 import Url4Node

from screamingface_engine.aggregators import (
    CANDIDATE_MEAN_ROUTE,
    MEAN_ROUTE,
    candidate_mean,
    mean,
)
from screamingface_engine.asgi import EngineASGI
from screamingface_engine.benchmarks import (
    DRACO_CASES_ROUTE,
    DRACO_LITE_CANDIDATE_ROUTE,
    DRACO_LITE_CASES_ROUTE,
    DRACO_PREVIEW_CASES_ROUTE,
    DRACO_TOOL_POLICY_ROUTE,
    GPQA_CASES_ROUTE,
    draco_cases,
    draco_lite_cases,
    draco_preview_cases,
    draco_tool_policy,
    gpqa_cases,
)
from screamingface_engine.candidate_evaluator import CandidateEvaluator
from screamingface_engine.catalog import (
    ModelRoute,
    benchmark_routes,
    registry_document,
    resolve_model_routes,
)
from screamingface_engine.connection_asgi import ConnectionASGI
from screamingface_engine.connection_gateway import ConnectionGateway
from screamingface_engine.connection_manager import ConnectionManager
from screamingface_engine.docs import DocumentationASGI
from screamingface_engine.draco_grader import (
    DRACO_JUDGE_MODEL,
    DRACO_JUDGE_PASSES,
    DRACO_LITE_JUDGE_PASSES,
    DRACO_LITE_RUBRIC_ROUTE,
    DRACO_PREVIEW_JUDGE_PASSES,
    DRACO_PREVIEW_RUBRIC_ROUTE,
    DRACO_RUBRIC_ROUTE,
    DracoRubricGrader,
)
from screamingface_engine.executor import ModelExecutor
from screamingface_engine.gateway import GatewayClient
from screamingface_engine.graders import EXACT_CHOICE_ROUTE, exact_choice
from screamingface_engine.reducers import MAJORITY_VOTE_ROUTE, majority_vote
from screamingface_engine.settings import MAX_REQUEST_TARGET_BYTES, Settings
from screamingface_engine.tavily import TavilyService


def create_node(
    executor: ModelExecutor,
    model_routes: tuple[ModelRoute, ...],
    *,
    max_request_target_bytes: int = MAX_REQUEST_TARGET_BYTES,
    url4_concurrency: int = 32,
    case_concurrency: int = 10,
    synthesis_concurrency: int = 16,
    judge_concurrency: int = 32,
) -> Url4Node:
    """Register executable routes plus health and capability metadata."""

    node = Url4Node(
        "screamingface-engine",
        eval_path="/v1",
        concurrency=url4_concurrency,
    )
    for model in model_routes:
        node.endpoint(model.route)(executor.handler(model))
    node.endpoint(MAJORITY_VOTE_ROUTE)(majority_vote)
    node.endpoint(EXACT_CHOICE_ROUTE)(exact_choice)
    node.endpoint(MEAN_ROUTE)(mean)
    node.endpoint(CANDIDATE_MEAN_ROUTE)(candidate_mean)
    node.data(GPQA_CASES_ROUTE, media_type="application/x-ndjson")(gpqa_cases)
    node.data(DRACO_TOOL_POLICY_ROUTE, media_type="application/json")(draco_tool_policy)
    advertised = {benchmark.id for benchmark in benchmark_routes(model_routes)}
    judge = next((model for model in model_routes if model.id == DRACO_JUDGE_MODEL), None)
    judge_semaphore = asyncio.Semaphore(judge_concurrency)
    if judge is not None and "draco-preview@1" in advertised:
        node.endpoint(DRACO_PREVIEW_RUBRIC_ROUTE)(
            DracoRubricGrader(
                executor,
                judge,
                passes=DRACO_PREVIEW_JUDGE_PASSES,
                semaphore=judge_semaphore,
            )
        )
        node.data(DRACO_PREVIEW_CASES_ROUTE, media_type="application/x-ndjson")(draco_preview_cases)
    if judge is not None and "draco-lite@1" in advertised:
        lite_grader = DracoRubricGrader(
            executor,
            judge,
            passes=DRACO_LITE_JUDGE_PASSES,
            semaphore=judge_semaphore,
        )
        node.endpoint(DRACO_LITE_RUBRIC_ROUTE)(lite_grader)
        node.endpoint(DRACO_LITE_CANDIDATE_ROUTE)(
            CandidateEvaluator(
                executor,
                model_routes,
                lite_grader,
                case_concurrency=case_concurrency,
                synthesis_concurrency=synthesis_concurrency,
            )
        )
        node.data(DRACO_LITE_CASES_ROUTE, media_type="application/x-ndjson")(draco_lite_cases)
    if judge is not None and "draco@1" in advertised:
        node.endpoint(DRACO_RUBRIC_ROUTE)(
            DracoRubricGrader(
                executor,
                judge,
                passes=DRACO_JUDGE_PASSES,
                semaphore=judge_semaphore,
            )
        )
        node.data(DRACO_CASES_ROUTE, media_type="application/x-ndjson")(draco_cases)
    node.data("/healthz", "ok")
    node.data(
        "/.well-known/screamingface",
        json.dumps(
            registry_document(
                model_routes,
                max_request_target_bytes=max_request_target_bytes,
            ),
            separators=(",", ":"),
        ),
    )
    return node


def create_app(
    *,
    settings: Settings | None = None,
    gateway: GatewayClient | None = None,
    model_routes: tuple[ModelRoute, ...] | None = None,
    tavily: TavilyService | None = None,
) -> EngineASGI:
    """Compose the persistent node, Gateway adapter, and thin ASGI lifecycle."""

    resolved = settings or Settings.from_env()
    adapter = gateway or GatewayClient(
        resolved.gateway_url,
        timeout=resolved.gateway_timeout,
    )
    tavily_adapter = tavily or TavilyService(timeout=resolved.tavily_timeout)
    executor = ModelExecutor(
        adapter,
        tavily_adapter,
        concurrency=resolved.model_concurrency,
    )
    documentation = DocumentationASGI(max_request_target_bytes=resolved.max_request_target_bytes)

    async def initialize_node() -> Url4Node:
        # INVARIANT: Executable endpoints and advertised models come from one Gateway snapshot.
        discovered = await adapter.list_models()
        routes = resolve_model_routes(discovered)
        documentation.configure(routes)
        return create_node(
            executor,
            routes,
            max_request_target_bytes=resolved.max_request_target_bytes,
            url4_concurrency=resolved.url4_concurrency,
            case_concurrency=resolved.case_concurrency,
            synthesis_concurrency=resolved.synthesis_concurrency,
            judge_concurrency=resolved.judge_concurrency,
        )

    node = (
        None
        if model_routes is None
        else create_node(
            executor,
            model_routes,
            max_request_target_bytes=resolved.max_request_target_bytes,
            url4_concurrency=resolved.url4_concurrency,
            case_concurrency=resolved.case_concurrency,
            synthesis_concurrency=resolved.synthesis_concurrency,
            judge_concurrency=resolved.judge_concurrency,
        )
    )
    if model_routes is not None:
        documentation.configure(model_routes)
    return EngineASGI(
        node,
        adapter,
        initialize=initialize_node if node is None else None,
        connections=ConnectionASGI(
            ConnectionManager(
                ConnectionGateway(
                    adapter,
                    codex_oauth_redirect_uri=resolved.codex_oauth_redirect_uri,
                ),
                tavily_adapter,
            )
        ),
        documentation=documentation,
        max_inflight=resolved.max_inflight,
        timeout=resolved.evaluation_timeout,
        max_request_target_bytes=resolved.max_request_target_bytes,
    )
    (draco_cases,)
    (draco_preview_cases,)
