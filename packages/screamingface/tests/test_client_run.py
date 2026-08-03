"""Execution errors surfaced by the single Client.evaluate operation."""

from __future__ import annotations

from typing import NoReturn

import httpx
import pytest
from url4 import RelExpr, expr, render, src, text

import screamingface as sf

BENCHMARK_URL4 = render(
    expr(
        src(
            RelExpr(path="/candidate", context="question", intent=text("$candidate")),
            name="answer",
            weight=0.0,
        ),
        src(
            RelExpr(path="/provider/judge", context="$answer", intent=text("Grade.")),
            name="grade",
            weight=0.0,
        ),
        intent=text("$grade"),
    )
)

BENCHMARK = {
    "schema": "screamingface.benchmark.v1",
    "id": "draco",
    "revision": "fixture-revision",
    "case_count": 1,
    "total_case_count": 1,
    "required_models": ["provider/judge"],
    "url4": BENCHMARK_URL4,
}


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
    elif request.url.path == "/v1/benchmarks/draco":
        response = httpx.Response(200, json=BENCHMARK)
    else:
        response = httpx.Response(404)
    return response


class _ForbiddenTransport:
    called = False

    def run(self, candidate: object, on_event: object) -> NoReturn:
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

    transport = _ForbiddenTransport()
    client = sf.Client(
        engine_url="https://engine.example",
        http_transport=httpx.MockTransport(engine_without_candidate),
        run_transport=transport,
    )

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

    transport = _ForbiddenTransport()
    client = sf.Client(
        engine_url="https://engine.example",
        http_transport=httpx.MockTransport(engine_without_judge),
        run_transport=transport,
    )

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
        synthesizer="provider/synthesis",
    )
    transport = _ForbiddenTransport()
    client = sf.Client(
        engine_url="https://engine.example",
        http_transport=httpx.MockTransport(engine_without_synthesis),
        run_transport=transport,
    )

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
    with sf.Client(
        engine_url="http://127.0.0.1:1",
        http_transport=httpx.MockTransport(_engine),
    ) as client:
        with pytest.raises(sf.EngineUnavailableError) as caught:
            client.evaluate(
                sf.Model("provider/opus"),
                benchmark="draco",
                progress=False,
            )

    assert caught.value.code == "engine_unreachable"
    assert caught.value.permanent is False
    assert caught.value.engine_url == "http://127.0.0.1:1"


@pytest.mark.asyncio
async def test_async_evaluate_reports_the_same_unreachable_execution_transport() -> None:
    client = sf.AsyncClient(
        engine_url="http://127.0.0.1:1",
        http_transport=httpx.MockTransport(_engine),
    )

    with pytest.raises(sf.EngineUnavailableError) as caught:
        await client.evaluate(
            sf.Model("provider/opus"),
            benchmark="draco",
            progress=False,
        )
    await client.aclose()

    assert caught.value.retryable is True
    assert caught.value.engine_url == "http://127.0.0.1:1"
