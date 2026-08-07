"""Benchmark retrieval is a ceiling that Candidate calls may explicitly narrow.

FEATURE: DRACO gives retrieval to answer-producing Candidate Models while keeping both the
Fusion synthesizer and the Benchmark-owned Judge retrieval-free.
STORY: as a researcher, my DRACO score must describe the published protocol rather than a
stronger experiment where synthesis or Grading can consult the live web.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from url4 import RelExpr, Text, expr, render, src, text
from url4.core.errors import ResolutionError
from url4_cloud.benchmarks.candidate import install_candidate_invocation
from url4_cloud.benchmarks.definition import candidate
from url4_cloud.benchmarks.draco.definition import EXCLUDED_DOMAINS, JUDGE_MODEL, JUDGE_PARAMS
from url4_cloud.benchmarks.ifeval.definition import IFEVAL
from url4_cloud.benchmarks.ifeval.iterative_correction import (
    IFEVAL_SELF_CORRECTIVE,
    IFEVAL_VERIFYING_ENSEMBLE,
)
from url4_cloud.runner.config import ModelSpec
from url4_cloud.runner.connector import (
    AigatewayConfig,
    AigatewayWorld,
)
from url4_cloud.runner.connector import (
    build_aigateway_world as _build_aigateway_world,
)


async def build_aigateway_world(
    config: AigatewayConfig,
    **kwargs: Any,
) -> AigatewayWorld:
    """Compose Candidate Invocation only in tests that exercise that extension."""

    world = await _build_aigateway_world(config, **kwargs)
    install_candidate_invocation(world.node)
    return world


def _link(candidate_expression, benchmark_expression) -> str:
    """Link an inert Candidate exactly as the SDK does."""

    return render(
        expr(
            src(text(render(candidate_expression)), name="candidate", weight=0.0),
            benchmark_expression,
            intent=text(""),
        )
    )


def _benchmark_call(question: str):
    return expr(
        src(
            candidate(
                question,
                web_search=True,
                web_search_exclude=EXCLUDED_DOMAINS,
            ),
            name="answer",
            weight=0.0,
        ),
        intent=text("$answer"),
    )


async def _request_bodies(
    candidate_expression,
    benchmark_expression,
    models: tuple[ModelSpec, ...],
) -> list[dict[str, object]]:
    bodies: list[dict[str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        model = body["model"]
        content = "final answer" if model.endswith("synthesizer") else "member answer"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond), base_url="http://aigateway.test"
    ) as client:
        world = await build_aigateway_world(
            AigatewayConfig(default_model=models[0].id, models=models),
            client=client,
            tavily_client=client,
            tavily_api_key="tv-key",
        )
        try:
            await world.node.evaluate(_link(candidate_expression, benchmark_expression))
        finally:
            await world.aclose()
    return bodies


@pytest.mark.asyncio
async def test_draco_retrieval_reaches_members_but_not_fusion_synthesis() -> None:
    """A Benchmark policy is a ceiling: a Candidate operation may narrow it to no search."""

    member = "provider/member"
    synthesizer = "provider/synthesizer"
    candidate_expression = expr(
        src(
            RelExpr(
                path=f"/{member}",
                context="$input",
                intent=Text("Answer."),
            ),
            name="member",
            weight=0.0,
        ),
        src(
            RelExpr(
                path=f"/{synthesizer}",
                context="$member",
                intent=Text("Synthesize."),
                params=(("web_search", "false"),),
            ),
            name="synthesis",
            weight=0.0,
        ),
        intent=text("$synthesis"),
    )

    bodies = await _request_bodies(
        candidate_expression,
        _benchmark_call("Research this question."),
        (
            ModelSpec(id=member, native_web_search=True),
            ModelSpec(id=synthesizer, native_web_search=True),
        ),
    )

    assert bodies[0]["model"] == member
    assert bodies[0]["web_search"] is True
    assert bodies[0]["web_search_excluded_domains"] == sorted(EXCLUDED_DOMAINS)
    assert bodies[1]["model"] == synthesizer
    assert "web_search" not in bodies[1]
    assert "web_search_excluded_domains" not in bodies[1]


@pytest.mark.asyncio
async def test_one_route_can_retrieve_as_a_candidate_and_stay_tool_free_as_the_judge() -> None:
    """Gemini Pro's route capability must not silently change its retrieval-free Judge call."""

    candidate_expression = expr(
        src(
            RelExpr(
                path=f"/{JUDGE_MODEL}",
                context="$input",
                intent=Text("Answer."),
            ),
            name="answer",
            weight=0.0,
        ),
        intent=text("$answer"),
    )
    benchmark_expression = expr(
        src(
            candidate(
                "Research this question.",
                web_search=True,
                web_search_exclude=EXCLUDED_DOMAINS,
            ),
            name="answer",
            weight=0.0,
        ),
        src(
            RelExpr(
                path=f"/{JUDGE_MODEL}",
                context="$answer",
                intent=Text("Grade without retrieval."),
                params=JUDGE_PARAMS,
            ),
            name="grade",
            weight=0.0,
        ),
        intent=text("$grade"),
    )

    bodies = await _request_bodies(
        candidate_expression,
        benchmark_expression,
        (ModelSpec(id=JUDGE_MODEL, web_tools=True),),
    )

    assert bodies[0]["model"] == JUDGE_MODEL
    tools = bodies[0]["tools"]
    assert isinstance(tools, list)
    names: list[str] = []
    for tool in tools:
        assert isinstance(tool, dict)
        function = tool["function"]
        assert isinstance(function, dict)
        name = function["name"]
        assert isinstance(name, str)
        names.append(name)
    assert names == ["web_search", "web_fetch"]
    assert bodies[1]["model"] == JUDGE_MODEL
    assert "tools" not in bodies[1]
    assert "tool_choice" not in bodies[1]


@pytest.mark.parametrize("tavily_api_key", [None, "", "   "])
@pytest.mark.asyncio
async def test_draco_tavily_route_without_a_key_fails_before_model_spend(
    tavily_api_key: str | None,
) -> None:
    """Required guarded retrieval cannot silently degrade into an answer from model weights."""

    gateway_bodies: list[dict[str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        gateway_bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "answer"}}]})

    route = "provider/tavily-candidate"
    candidate_expression = expr(
        src(
            RelExpr(
                path=f"/{route}",
                context="$input",
                intent=Text("Answer."),
            ),
            name="answer",
            weight=0.0,
        ),
        intent=text("$answer"),
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond), base_url="http://aigateway.test"
    ) as client:
        world = await build_aigateway_world(
            AigatewayConfig(
                default_model=route,
                models=(ModelSpec(id=route, web_tools=True),),
            ),
            client=client,
            tavily_api_key=tavily_api_key,
        )
        try:
            with pytest.raises(ResolutionError, match="requires a configured Tavily") as exc_info:
                await world.node.evaluate(
                    _link(candidate_expression, _benchmark_call("Research this question."))
                )
        finally:
            await world.aclose()

    assert exc_info.value.code == "benchmark_retrieval_unavailable"
    assert exc_info.value.permanent is True
    assert gateway_bodies == []


@pytest.mark.asyncio
async def test_explicit_tavily_retrieval_without_a_key_fails_even_without_exclusions() -> None:
    """The retrieval toggle itself is enough to require the configured mechanism."""

    gateway_bodies: list[dict[str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        gateway_bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "answer"}}]})

    route = "provider/tavily-candidate"
    candidate_expression = expr(
        src(
            RelExpr(
                path=f"/{route}",
                context="$input",
                intent=Text("Answer."),
            ),
            name="answer",
            weight=0.0,
        ),
        intent=text("$answer"),
    )
    benchmark_expression = candidate("Research this question.", web_search=True)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond), base_url="http://aigateway.test"
    ) as client:
        world = await build_aigateway_world(
            AigatewayConfig(
                default_model=route,
                models=(ModelSpec(id=route, web_tools=True),),
            ),
            client=client,
        )
        try:
            with pytest.raises(ResolutionError) as exc_info:
                await world.node.evaluate(_link(candidate_expression, benchmark_expression))
        finally:
            await world.aclose()

    assert exc_info.value.code == "benchmark_retrieval_unavailable"
    assert exc_info.value.permanent is True
    assert gateway_bodies == []


@pytest.mark.asyncio
async def test_required_tavily_failure_is_typed_instead_of_becoming_an_answer() -> None:
    """A bad or unavailable Tavily credential cannot degrade DRACO into a weights-only run."""

    gateway_calls = 0

    def gateway(request: httpx.Request) -> httpx.Response:
        nonlocal gateway_calls
        gateway_calls += 1
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "search-1",
                                    "type": "function",
                                    "function": {
                                        "name": "web_search",
                                        "arguments": '{"query":"current result"}',
                                    },
                                }
                            ],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    def tavily(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "invalid API key"})

    route = "provider/tavily-candidate"
    candidate_expression = expr(
        src(
            RelExpr(
                path=f"/{route}",
                context="$input",
                intent=Text("Answer."),
            ),
            name="answer",
            weight=0.0,
        ),
        intent=text("$answer"),
    )
    async with (
        httpx.AsyncClient(
            transport=httpx.MockTransport(gateway), base_url="http://aigateway.test"
        ) as gateway_client,
        httpx.AsyncClient(
            transport=httpx.MockTransport(tavily), base_url="http://tavily.test"
        ) as tavily_client,
    ):
        world = await build_aigateway_world(
            AigatewayConfig(
                default_model=route,
                models=(ModelSpec(id=route, web_tools=True),),
            ),
            client=gateway_client,
            tavily_client=tavily_client,
            tavily_api_key="bad-key",
        )
        try:
            with pytest.raises(ResolutionError) as exc_info:
                await world.node.evaluate(
                    _link(candidate_expression, _benchmark_call("Research this question."))
                )
        finally:
            await world.aclose()

    assert exc_info.value.code == "web_retrieval_unavailable"
    assert exc_info.value.permanent is True
    assert gateway_calls == 1


@pytest.mark.parametrize("payload", [b"not-json", b'{"results":"not-a-list"}'])
@pytest.mark.asyncio
async def test_malformed_tavily_success_payload_is_a_typed_retrieval_failure(
    payload: bytes,
) -> None:
    """An HTTP 200 that violates Tavily's response contract cannot become model-visible prose."""

    def gateway(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "search-1",
                                    "type": "function",
                                    "function": {
                                        "name": "web_search",
                                        "arguments": '{"query":"current result"}',
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
        )

    def tavily(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload)

    route = "provider/tavily-candidate"
    candidate_expression = expr(
        src(
            RelExpr(
                path=f"/{route}",
                context="$input",
                intent=Text("Answer."),
            ),
            name="answer",
            weight=0.0,
        ),
        intent=text("$answer"),
    )
    async with (
        httpx.AsyncClient(
            transport=httpx.MockTransport(gateway), base_url="http://aigateway.test"
        ) as gateway_client,
        httpx.AsyncClient(
            transport=httpx.MockTransport(tavily), base_url="http://tavily.test"
        ) as tavily_client,
    ):
        world = await build_aigateway_world(
            AigatewayConfig(default_model=route, models=(ModelSpec(id=route, web_tools=True),)),
            client=gateway_client,
            tavily_client=tavily_client,
            tavily_api_key="tv-key",
        )
        try:
            with pytest.raises(ResolutionError) as exc_info:
                await world.node.evaluate(
                    _link(candidate_expression, _benchmark_call("Research this question."))
                )
        finally:
            await world.aclose()

    assert exc_info.value.code == "web_retrieval_unavailable"


@pytest.mark.parametrize(
    "benchmark",
    (IFEVAL, IFEVAL_SELF_CORRECTIVE, IFEVAL_VERIFYING_ENSEMBLE),
)
def test_every_ifeval_candidate_invocation_remains_retrieval_free(benchmark) -> None:
    """Retrieval-scope changes cannot alter canonical, corrective, or ensemble IFEval."""

    url4 = benchmark.resource(1)["url4"]
    assert isinstance(url4, str)
    assert url4.count("/candidate?") == url4.count("/candidate?web_search=false")
