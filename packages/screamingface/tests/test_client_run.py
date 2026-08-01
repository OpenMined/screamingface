"""Execution errors surfaced by the single Client.evaluate operation."""

from __future__ import annotations

from typing import Any, cast

import httpx
import pytest

import screamingface as sf

MANIFEST = b"""\
id: draco@1
title: DRACO
cases:
  count: 1
  route: /draco/cases
answer:
  instructions: Answer completely.
  params:
    temperature: 0.2
    reasoning: low
    max_output_tokens: 4096
synthesis:
  model: provider/synthesis
  instructions: Combine the panel answers.
  params:
    temperature: 0.2
    reasoning: low
    max_output_tokens: 4096
grader:
  kind: rubric
  criteria_route: /draco/criteria/{case_id}
  criteria_per_case: 1
  model: provider/judge
  passes: 1
  instructions: Return JSON.
  params: {}
aggregator:
  kind: mean
  route: /benchmark
metrics:
  primary: score
  direction: maximize
tools: []
"""


def _engine(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/v1/models":
        response = httpx.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"id": "provider/opus", "object": "model", "owned_by": "provider"},
                    {"id": "provider/judge", "object": "model", "owned_by": "provider"},
                ],
            },
        )
    elif request.url.path == "/v1/benchmarks":
        response = httpx.Response(
            200,
            json={
                "object": "list",
                "default": "draco",
                "data": [{"id": "draco", "object": "benchmark"}],
            },
        )
    elif request.url.path == "/v1/benchmarks/draco":
        response = httpx.Response(200, content=MANIFEST)
    else:
        response = httpx.Response(404)
    return response


class _ForbiddenTransport:
    called = False

    def run(self, candidate: object, on_event: object) -> object:
        self.called = True
        raise AssertionError("unavailable Models must fail before execution")

    def close(self) -> None:
        pass


def test_evaluate_rejects_an_unavailable_model_before_execution() -> None:
    def engine_without_candidate(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": [
                        {"id": "provider/judge", "object": "model", "owned_by": "provider"},
                    ],
                },
            )
        return _engine(request)

    client = sf.Client(engine_url="https://engine.example")
    private_client = cast(Any, client)
    private_client._http.close()
    private_client._http = httpx.Client(
        base_url="https://engine.example",
        transport=httpx.MockTransport(engine_without_candidate),
    )
    private_client._transport.close()
    transport = _ForbiddenTransport()
    private_client._transport = transport

    with (
        client,
        pytest.raises(
            sf.PlanningError,
            match="Model 'missing/model' is not available on this Engine",
        ) as caught,
    ):
        client.evaluate(sf.Model("missing/model"), benchmark="draco")

    assert caught.value.code == "model_unavailable"
    assert caught.value.permanent is True
    assert caught.value.details == {"models": ["missing/model"]}
    assert transport.called is False


def test_evaluate_rejects_an_unavailable_judge_before_execution() -> None:
    def engine_without_judge(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": [
                        {"id": "provider/opus", "object": "model", "owned_by": "provider"},
                    ],
                },
            )
        return _engine(request)

    client = sf.Client(engine_url="https://engine.example")
    private_client = cast(Any, client)
    private_client._http.close()
    private_client._http = httpx.Client(
        base_url="https://engine.example",
        transport=httpx.MockTransport(engine_without_judge),
    )
    private_client._transport.close()
    transport = _ForbiddenTransport()
    private_client._transport = transport

    with (
        client,
        pytest.raises(
            sf.PlanningError,
            match="Model 'provider/judge' is not available on this Engine",
        ),
    ):
        client.evaluate(sf.Model("provider/opus"), benchmark="draco")

    assert transport.called is False


def test_evaluate_rejects_an_unavailable_fusion_model_before_execution() -> None:
    def engine_without_synthesis(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": [
                        {"id": model, "object": "model", "owned_by": "provider"}
                        for model in ("provider/opus", "provider/gpt", "provider/judge")
                    ],
                },
            )
        return _engine(request)

    fusion = sf.Fusion(
        [sf.Model("provider/opus"), sf.Model("provider/gpt")],
        name="panel",
    )
    client = sf.Client(engine_url="https://engine.example")
    private_client = cast(Any, client)
    private_client._http.close()
    private_client._http = httpx.Client(
        base_url="https://engine.example",
        transport=httpx.MockTransport(engine_without_synthesis),
    )
    private_client._transport.close()
    transport = _ForbiddenTransport()
    private_client._transport = transport

    with (
        client,
        pytest.raises(
            sf.PlanningError,
            match="Model 'provider/synthesis' is not available on this Engine",
        ),
    ):
        client.evaluate(fusion, benchmark="draco")

    assert transport.called is False


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
