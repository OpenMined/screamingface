"""Composition root for the persistent ScreamingFace URL4 engine."""

from __future__ import annotations

import json

from url4 import Url4Node

from screamingface_engine.aggregators import MEAN_ROUTE, mean
from screamingface_engine.asgi import EngineASGI
from screamingface_engine.benchmarks import GPQA_CASES_ROUTE, gpqa_cases
from screamingface_engine.catalog import ModelRoute, registry_document, resolve_model_routes
from screamingface_engine.connection_asgi import ConnectionASGI
from screamingface_engine.connection_gateway import ConnectionGateway
from screamingface_engine.connection_manager import ConnectionManager
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
) -> Url4Node:
    """Register executable routes plus health and capability metadata."""

    node = Url4Node("screamingface-engine", eval_path="/v1")
    for model in model_routes:
        node.endpoint(model.route)(executor.handler(model))
    node.endpoint(MAJORITY_VOTE_ROUTE)(majority_vote)
    node.endpoint(EXACT_CHOICE_ROUTE)(exact_choice)
    node.endpoint(MEAN_ROUTE)(mean)
    node.data(GPQA_CASES_ROUTE, media_type="application/x-ndjson")(gpqa_cases)
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
    executor = ModelExecutor(adapter, tavily_adapter)

    async def initialize_node() -> Url4Node:
        # INVARIANT: Executable endpoints and advertised models come from one Gateway snapshot.
        discovered = await adapter.list_models()
        return create_node(
            executor,
            resolve_model_routes(discovered),
            max_request_target_bytes=resolved.max_request_target_bytes,
        )

    node = (
        None
        if model_routes is None
        else create_node(
            executor,
            model_routes,
            max_request_target_bytes=resolved.max_request_target_bytes,
        )
    )
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
        max_inflight=resolved.max_inflight,
        timeout=resolved.evaluation_timeout,
        max_request_target_bytes=resolved.max_request_target_bytes,
    )
