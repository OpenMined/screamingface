"""Composition root for the persistent ScreamingFace URL4 engine."""

from __future__ import annotations

import json

from url4 import Url4Node

from screamingface_engine.asgi import EngineASGI
from screamingface_engine.catalog import MODEL_ROUTES, registry_document
from screamingface_engine.gateway import GatewayClient
from screamingface_engine.reducers import MAJORITY_VOTE_ROUTE, majority_vote
from screamingface_engine.settings import Settings


def create_node(
    gateway: GatewayClient,
) -> Url4Node:
    """Register executable routes plus health and capability metadata."""

    node = Url4Node("screamingface-engine", eval_path="/v1")
    for model in MODEL_ROUTES:
        node.endpoint(model.route)(gateway.handler(model))
    node.endpoint(MAJORITY_VOTE_ROUTE)(majority_vote)
    node.data("/healthz", "ok")
    node.data(
        "/.well-known/screamingface",
        json.dumps(registry_document(), separators=(",", ":")),
    )
    return node


def create_app(
    *,
    settings: Settings | None = None,
    gateway: GatewayClient | None = None,
) -> EngineASGI:
    """Compose the persistent node, Gateway adapter, and thin ASGI lifecycle."""

    resolved = settings or Settings.from_env()
    adapter = gateway or GatewayClient(
        resolved.gateway_url,
        timeout=resolved.gateway_timeout,
    )
    node = create_node(adapter)
    return EngineASGI(
        node,
        adapter,
        max_inflight=resolved.max_inflight,
        timeout=resolved.evaluation_timeout,
    )
