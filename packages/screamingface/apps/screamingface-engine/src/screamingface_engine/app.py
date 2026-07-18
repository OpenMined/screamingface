"""Url4Node composition root for ScreamingFace-owned profile data."""

from __future__ import annotations

import json
from collections.abc import Mapping

from url4 import Url4Node

from screamingface_engine.catalog import (
    CaseLoader,
    cases_document,
    manifest_document,
    published_benchmarks,
    registry_document,
)


def create_node(*, case_loaders: Mapping[str, CaseLoader] | None = None) -> Url4Node:
    """Create the real URL4 node with ScreamingFace profile data routes."""

    publications = published_benchmarks(case_loaders)
    node = Url4Node("screamingface-engine", eval_path="/v1")
    node.data("/healthz", "ok")
    node.data(
        "/.well-known/screamingface",
        json.dumps(registry_document(publications), separators=(",", ":")),
    )
    for publication in publications:
        node.data(
            f"/sf/benchmarks/{publication.benchmark.id}",
            json.dumps(manifest_document(publication), separators=(",", ":")),
        )
        node.data(
            publication.cases_path,
            lambda publication=publication: cases_document(publication),
            media_type="application/x-ndjson",
        )
    return node


def create_app(*, case_loaders: Mapping[str, CaseLoader] | None = None):
    """Return the framework-free ASGI application exposed by the profile node."""

    return create_node(case_loaders=case_loaders).asgi()
