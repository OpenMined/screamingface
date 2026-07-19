"""Composition root for the persistent ScreamingFace URL4 engine."""

from __future__ import annotations

import json
from collections.abc import Mapping

from url4 import Url4Node

from screamingface_engine.asgi import EngineASGI
from screamingface_engine.catalog import (
    MODEL_ROUTES,
    CaseLoader,
    cases_document,
    manifest_document,
    published_benchmarks,
    registry_document,
)
from screamingface_engine.gateway import GatewayClient
from screamingface_engine.reducers import MAJORITY_VOTE_ROUTE, majority_vote
from screamingface_engine.settings import Settings


def create_node(
    gateway: GatewayClient,
    *,
    case_loaders: Mapping[str, CaseLoader] | None = None,
) -> Url4Node:
    """Register executable model routes and ScreamingFace-owned data routes."""

    publications = published_benchmarks(case_loaders)
    node = Url4Node("screamingface-engine", eval_path="/v1")
    for model in MODEL_ROUTES:
        node.endpoint(model.route)(gateway.handler(model))
    node.endpoint(MAJORITY_VOTE_ROUTE)(majority_vote)
    node.data("/healthz", "ok")
    node.data(
        "/.well-known/screamingface",
        json.dumps(registry_document(publications), separators=(",", ":")),
    )
    for publication in publications:
        node.data(
            f"/benchmarks/{publication.benchmark.id}",
            json.dumps(manifest_document(publication), separators=(",", ":")),
        )
        node.data(
            publication.cases_path,
            lambda publication=publication: cases_document(publication),
            media_type="application/x-ndjson",
        )
    return node


def create_app(
    *,
    settings: Settings | None = None,
    gateway: GatewayClient | None = None,
    case_loaders: Mapping[str, CaseLoader] | None = None,
) -> EngineASGI:
    """Compose the persistent node, Gateway adapter, and thin ASGI lifecycle."""

    resolved = settings or Settings.from_env()
    adapter = gateway or GatewayClient(
        resolved.gateway_url,
        timeout=resolved.gateway_timeout,
    )
    node = create_node(adapter, case_loaders=case_loaders)
    return EngineASGI(
        node,
        adapter,
        max_inflight=resolved.max_inflight,
        timeout=resolved.evaluation_timeout,
    )
