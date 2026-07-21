from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

import pytest
from url4 import Request, ResolutionError

from screamingface_engine.catalog import ModelRoute
from screamingface_engine.executor import ModelExecutor
from screamingface_engine.gateway import AssistantTurn, ToolCall
from screamingface_engine.tool_policy import ExtractPolicy, SearchPolicy

HF_MODEL = ModelRoute(
    "huggingface/deepseek-ai/DeepSeek-V4-Pro~deepinfra",
    "huggingface/deepseek-ai/DeepSeek-V4-Pro:deepinfra",
    "huggingface",
    ("web_search", "web_fetch"),
)
TOOL_FREE_MODEL = ModelRoute("codex/gpt-5.5", "codex/gpt-5.5", "codex")


class Gateway:
    def __init__(self, turns: Sequence[AssistantTurn]) -> None:
        self.turns = iter(turns)
        self.requests: list[
            tuple[
                ModelRoute,
                list[dict[str, object]],
                Mapping[str, str],
                tuple[dict[str, object], ...],
            ]
        ] = []

    async def turn(
        self,
        model: ModelRoute,
        *,
        messages: list[dict[str, object]],
        params: Mapping[str, str],
        tools: tuple[dict[str, object], ...],
    ) -> AssistantTurn:
        self.requests.append((model, list(messages), dict(params), tools))
        return next(self.turns)


class Tavily:
    def __init__(self, *, connected: bool = True) -> None:
        self.connected = connected
        self.calls: list[tuple[str, object, object]] = []

    async def is_connected(self) -> bool:
        return self.connected

    async def search(self, query: str, policy: SearchPolicy) -> dict[str, object]:
        self.calls.append(("search", query, policy))
        return {"answer": None, "results": [], "truncated": False}

    async def extract(
        self, url: str, policy: ExtractPolicy, *, query: str | None
    ) -> dict[str, object]:
        self.calls.append(("extract", url, query))
        return {"url": url, "content": "Evidence", "truncated": False}


def _params(*, tools: str = "web_search:web_fetch", rounds: int = 12) -> dict[str, str]:
    values = {
        "tools": tools,
        "max_tool_rounds": str(rounds),
        "temperature": "0.2",
    }
    if "web_search" in tools:
        values.update(
            {
                "tavily.search.search_depth": "basic",
                "tavily.search.max_results": "5",
                "tavily.search.topic": "general",
                "tavily.search.include_answer": "false",
                "tavily.search.include_raw_content": "false",
                "tavily.search.include_images": "false",
                "tavily.search.include_image_descriptions": "false",
                "tavily.search.include_favicon": "false",
                "tavily.search.auto_parameters": "false",
                "tavily.search.exact_match": "false",
                "tavily.search.include_usage": "false",
                "tavily.search.safe_search": "false",
            }
        )
    if "web_fetch" in tools:
        values.update(
            {
                "tavily.extract.extract_depth": "basic",
                "tavily.extract.include_images": "false",
                "tavily.extract.include_favicon": "false",
                "tavily.extract.format": "markdown",
                "tavily.extract.include_usage": "false",
            }
        )
    return values


@pytest.mark.asyncio
async def test_agent_loop_preserves_calls_executes_sequentially_and_returns_plaintext() -> None:
    gateway = Gateway(
        (
            AssistantTurn(
                None,
                (
                    ToolCall("search_1", "web_search", '{"query":"first"}'),
                    ToolCall(
                        "fetch_1",
                        "web_fetch",
                        '{"url":"https://example.org","query":"focused"}',
                    ),
                ),
            ),
            AssistantTurn("Final researched answer", ()),
        )
    )
    tavily = Tavily()
    executor = ModelExecutor(gateway, tavily)

    answer = await executor.complete(
        HF_MODEL,
        Request(HF_MODEL.route, "Research question", "Answer with sources", _params()),
    )

    assert answer == "Final researched answer"
    assert [call[:2] for call in tavily.calls] == [
        ("search", "first"),
        ("extract", "https://example.org"),
    ]
    assert gateway.requests[0][2] == {"temperature": "0.2"}
    tool_names: set[object] = set()
    for tool in gateway.requests[0][3]:
        function = tool["function"]
        assert isinstance(function, dict)
        tool_names.add(function["name"])
    assert tool_names == {"web_search", "web_fetch"}
    messages = gateway.requests[1][1]
    assert messages[2] == {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "search_1",
                "type": "function",
                "function": {"name": "web_search", "arguments": '{"query":"first"}'},
            },
            {
                "id": "fetch_1",
                "type": "function",
                "function": {
                    "name": "web_fetch",
                    "arguments": '{"url":"https://example.org","query":"focused"}',
                },
            },
        ],
    }
    assert [message["tool_call_id"] for message in messages[3:]] == ["search_1", "fetch_1"]


@pytest.mark.asyncio
async def test_tool_free_request_is_one_gateway_turn_and_never_checks_tavily() -> None:
    gateway = Gateway((AssistantTurn("Direct answer", ()),))
    tavily = Tavily(connected=False)
    executor = ModelExecutor(gateway, tavily)

    answer = await executor.complete(
        TOOL_FREE_MODEL,
        Request(TOOL_FREE_MODEL.route, "Question", "Answer", {"max_tokens": "8"}),
    )

    assert answer == "Direct answer"
    assert len(gateway.requests) == 1
    assert gateway.requests[0][3] == ()
    assert tavily.calls == []


@pytest.mark.asyncio
async def test_missing_tavily_and_unsupported_route_fail_before_gateway_spend() -> None:
    gateway = Gateway(())
    disconnected = ModelExecutor(gateway, Tavily(connected=False))
    with pytest.raises(ResolutionError) as missing:
        await disconnected.complete(
            HF_MODEL,
            Request(HF_MODEL.route, "Q", "A", _params(tools="web_search")),
        )
    assert missing.value.code == "authentication_required"

    unsupported = ModelExecutor(gateway, Tavily())
    with pytest.raises(ResolutionError) as capability:
        await unsupported.complete(
            TOOL_FREE_MODEL,
            Request(TOOL_FREE_MODEL.route, "Q", "A", _params(tools="web_search")),
        )
    assert capability.value.code == "unsupported_tool"
    assert gateway.requests == []


@pytest.mark.asyncio
async def test_invalid_model_arguments_return_safe_tool_errors_for_correction() -> None:
    gateway = Gateway(
        (
            AssistantTurn(None, (ToolCall("bad", "web_search", "not-json"),)),
            AssistantTurn("Recovered answer", ()),
        )
    )
    tavily = Tavily()
    executor = ModelExecutor(gateway, tavily)

    answer = await executor.complete(
        HF_MODEL,
        Request(HF_MODEL.route, "Q", "A", _params(tools="web_search")),
    )

    assert answer == "Recovered answer"
    assert tavily.calls == []
    content = gateway.requests[1][1][-1]["content"]
    assert isinstance(content, str)
    tool_result = json.loads(content)
    assert tool_result == {
        "error": {"code": "invalid_tool_arguments", "message": "Invalid JSON object."}
    }


@pytest.mark.asyncio
async def test_fetch_chunks_without_runtime_query_is_a_correctable_tool_error() -> None:
    params = _params(tools="web_fetch")
    params["tavily.extract.chunks_per_source"] = "3"
    gateway = Gateway(
        (
            AssistantTurn(
                None,
                (ToolCall("fetch", "web_fetch", '{"url":"https://example.org"}'),),
            ),
            AssistantTurn("Corrected", ()),
        )
    )
    tavily = Tavily()
    executor = ModelExecutor(gateway, tavily)

    assert (
        await executor.complete(HF_MODEL, Request(HF_MODEL.route, "Q", "A", params)) == "Corrected"
    )
    assert tavily.calls == []
    content = gateway.requests[1][1][-1]["content"]
    assert isinstance(content, str)
    assert "query" in content


@pytest.mark.asyncio
async def test_round_limit_includes_initial_and_final_gateway_turns() -> None:
    gateway = Gateway(
        (
            AssistantTurn(None, (ToolCall("one", "web_search", '{"query":"one"}'),)),
            AssistantTurn(None, (ToolCall("two", "web_search", '{"query":"two"}'),)),
        )
    )
    tavily = Tavily()
    executor = ModelExecutor(gateway, tavily)

    with pytest.raises(ResolutionError) as captured:
        await executor.complete(
            HF_MODEL,
            Request(HF_MODEL.route, "Q", "A", _params(tools="web_search", rounds=2)),
        )

    assert captured.value.code == "tool_budget_exhausted"
    assert len(gateway.requests) == 2
    assert [call[1] for call in tavily.calls] == ["one"]


@pytest.mark.asyncio
async def test_per_turn_and_total_call_limits_abort_without_partial_answer() -> None:
    per_turn = Gateway(
        (
            AssistantTurn(
                None,
                tuple(
                    ToolCall(str(index), "web_search", f'{{"query":"{index}"}}')
                    for index in range(9)
                ),
            ),
        )
    )
    tavily = Tavily()
    with pytest.raises(ResolutionError) as first:
        await ModelExecutor(per_turn, tavily).complete(
            HF_MODEL,
            Request(HF_MODEL.route, "Q", "A", _params(tools="web_search")),
        )
    assert first.value.code == "tool_budget_exhausted"
    assert tavily.calls == []

    total = Gateway(
        tuple(
            AssistantTurn(
                None,
                tuple(
                    ToolCall(f"{turn}-{index}", "web_search", f'{{"query":"{turn}-{index}"}}')
                    for index in range(4)
                ),
            )
            for turn in range(9)
        )
    )
    second_tavily = Tavily()
    with pytest.raises(ResolutionError) as second:
        await ModelExecutor(total, second_tavily).complete(
            HF_MODEL,
            Request(HF_MODEL.route, "Q", "A", _params(tools="web_search")),
        )
    assert second.value.code == "tool_budget_exhausted"
    assert len(second_tavily.calls) == 32
