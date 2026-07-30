"""Execution errors surfaced by the single Client.evaluate operation."""

from __future__ import annotations

import hashlib
from typing import Any, cast

import httpx
import pytest

import screamingface as sf

MANIFEST = b"""\
schema: screamingface.benchmark-manifest.v1
name: draco
id: draco@1
title: DRACO
cases:
  route: /benchmarks/draco/cases
  count: 1
grader:
  route: /benchmarks/draco/grade
  criteria_per_case: 1
aggregator:
  route: /benchmarks/draco/aggregate
metrics:
  primary: score
  direction: maximize
tools: []
"""
DIGEST = f"sha256:{hashlib.sha256(MANIFEST).hexdigest()}"


def _engine(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/v1/benchmarks":
        return httpx.Response(
            200,
            json={
                "benchmarks": [
                    {
                        "name": "draco",
                        "id": "draco@1",
                        "manifest_digest": DIGEST,
                    }
                ]
            },
        )
    if request.url.path == "/v1/benchmarks/draco/manifest":
        return httpx.Response(200, content=MANIFEST)
    return httpx.Response(404)


def test_evaluate_reports_an_unreachable_execution_transport() -> None:
    with sf.Client(engine_url="http://127.0.0.1:1") as client:
        private_client = cast(Any, client)
        private_client._http.close()
        private_client._http = httpx.Client(
            base_url="http://127.0.0.1:1",
            transport=httpx.MockTransport(_engine),
        )
        with pytest.raises(sf.ExecutionError) as caught:
            client.evaluate(
                sf.Model("provider/opus"),
                benchmark="draco",
                progress=False,
            )

    assert caught.value.code == "engine_unreachable"
    assert caught.value.permanent is False
