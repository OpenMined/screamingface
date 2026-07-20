"""Composition root for the persistent ScreamingFace URL4 engine."""

from __future__ import annotations

import json

from url4 import Url4Node

from screamingface_engine.asgi import EngineASGI
from screamingface_engine.catalog import ModelRoute, registry_document, resolve_model_routes
from screamingface_engine.connection_asgi import ConnectionASGI
from screamingface_engine.connection_gateway import ConnectionGateway
from screamingface_engine.executor import ModelExecutor
from screamingface_engine.gateway import GatewayClient
from screamingface_engine.reducers import MAJORITY_VOTE_ROUTE, majority_vote
from screamingface_engine.settings import MAX_REQUEST_TARGET_BYTES, Settings
from screamingface_engine.web_research import WebResearchClient


def create_node(
    executor: ModelExecutor,
    model_routes: tuple[ModelRoute, ...],
    *,
    enabled_tools: tuple[str, ...] = (),
    max_request_target_bytes: int = MAX_REQUEST_TARGET_BYTES,
) -> Url4Node:
    """Register executable routes plus health and capability metadata."""

    node = Url4Node("screamingface-engine", eval_path="/v1")
    for model in model_routes:
        node.endpoint(model.route)(executor.handler(model))
    node.endpoint(MAJORITY_VOTE_ROUTE)(majority_vote)
    node.data("/healthz", "ok")
    node.data(
        "/.well-known/screamingface",
        json.dumps(
            registry_document(
                model_routes,
                enabled_tools=enabled_tools,
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
    research: WebResearchClient | None = None,
    model_routes: tuple[ModelRoute, ...] | None = None,
) -> EngineASGI:
    """Compose the persistent node, Gateway adapter, and thin ASGI lifecycle."""

    resolved = settings or Settings.from_env()
    adapter = gateway or GatewayClient(
        resolved.gateway_url,
        timeout=resolved.gateway_timeout,
    )
    research_adapter = research
    if research_adapter is None and resolved.searxng_url is not None:
        research_adapter = WebResearchClient(
            resolved.searxng_url,
            timeout=resolved.web_timeout,
            max_results=resolved.web_max_results,
            max_content_chars=resolved.web_max_content_chars,
            max_fetch_bytes=resolved.web_max_fetch_bytes,
        )
    executor = ModelExecutor(
        adapter,
        research_adapter,
        max_tool_calls=resolved.web_max_tool_calls,
    )
    enabled_tools = ("web_search",) if research_adapter is not None else ()

    async def initialize_node() -> Url4Node:
        # INVARIANT: Executable endpoints and advertised models come from one Gateway snapshot.
        discovered = await adapter.list_models()
        return create_node(
            executor,
            resolve_model_routes(discovered),
            enabled_tools=enabled_tools,
            max_request_target_bytes=resolved.max_request_target_bytes,
        )

    node = (
        None
        if model_routes is None
        else create_node(
            executor,
            model_routes,
            enabled_tools=enabled_tools,
            max_request_target_bytes=resolved.max_request_target_bytes,
        )
    )
    return EngineASGI(
        node,
        adapter,
        initialize=initialize_node if node is None else None,
        research=research_adapter,
        connections=ConnectionASGI(
            ConnectionGateway(
                adapter,
                codex_oauth_redirect_uri=resolved.codex_oauth_redirect_uri,
            )
        ),
        max_inflight=resolved.max_inflight,
        timeout=resolved.evaluation_timeout,
        max_request_target_bytes=resolved.max_request_target_bytes,
    )
