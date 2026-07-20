from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

import pytest
from model_fixtures import MODEL_ROUTES
from url4 import Request, ResolutionError

from screamingface_engine.catalog import ModelRoute
from screamingface_engine.executor import ModelExecutor
from screamingface_engine.gateway import AssistantTurn, ToolCall
from screamingface_engine.web_research import SearchResult


class _Gateway:
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


class _Research:
    def __init__(self) -> None:
        self.searches: list[str] = []
        self.fetches: list[str] = []

    async def search(self, query: str) -> tuple[SearchResult, ...]:
        self.searches.append(query)
        return (SearchResult("NVIDIA", "https://docs.nvidia.com/page", "Snippet"),)

    async def fetch(self, url: str) -> str:
        self.fetches.append(url)
        return "Full documentation"


@pytest.mark.asyncio
async def test_executor_runs_multiple_tools_then_returns_final_plaintext() -> None:
    gateway = _Gateway(
        (
            AssistantTurn(
                None,
                (
                    ToolCall("search_1", "web_search", '{"query":"Jetson Orin"}'),
                    ToolCall("fetch_1", "web_fetch", '{"url":"https://docs.nvidia.com/page"}'),
                ),
            ),
            AssistantTurn("Final researched answer", ()),
        )
    )
    research = _Research()
    executor = ModelExecutor(gateway, research, max_tool_calls=4)
    request = Request(
        "/claude/sonnet-4.6",
        "Research question",
        "Answer with sources",
        {"tools": "web_search", "temperature": "0"},
    )

    answer = await executor.complete(MODEL_ROUTES[2], request)

    assert answer == "Final researched answer"
    assert research.searches == ["Jetson Orin"]
    assert research.fetches == ["https://docs.nvidia.com/page"]
    assert gateway.requests[0][2] == {"temperature": "0"}
    names: set[object] = set()
    for tool in gateway.requests[0][3]:
        function = tool["function"]
        assert isinstance(function, dict)
        names.add(function["name"])
        parameters = function["parameters"]
        assert isinstance(parameters, dict)
        assert "additionalProperties" not in parameters
    assert names == {"web_search", "web_fetch"}
    follow_up = gateway.requests[1][1]
    assert follow_up[0] == {"role": "system", "content": "Answer with sources"}
    assert follow_up[1] == {"role": "user", "content": "Research question"}
    assert follow_up[2]["role"] == "assistant"
    assert follow_up[3] == {
        "role": "tool",
        "tool_call_id": "search_1",
        "name": "web_search",
        "content": json.dumps(
            {
                "results": [
                    {
                        "title": "NVIDIA",
                        "url": "https://docs.nvidia.com/page",
                        "snippet": "Snippet",
                    }
                ]
            },
            separators=(",", ":"),
        ),
    }
    assert follow_up[4]["name"] == "web_fetch"
    assert follow_up[4]["content"] == json.dumps(
        {"url": "https://docs.nvidia.com/page", "content": "Full documentation"},
        separators=(",", ":"),
    )


@pytest.mark.asyncio
async def test_executor_keeps_tool_free_requests_to_one_gateway_turn() -> None:
    gateway = _Gateway((AssistantTurn("Direct answer", ()),))
    executor = ModelExecutor(gateway, None, max_tool_calls=4)

    answer = await executor.complete(
        MODEL_ROUTES[0],
        Request("/codex/gpt-5.5", "Question", "Answer", {"max_tokens": "8"}),
    )

    assert answer == "Direct answer"
    assert gateway.requests[0][2] == {"max_tokens": "8"}
    assert gateway.requests[0][3] == ()


@pytest.mark.asyncio
async def test_executor_rejects_unavailable_and_unsupported_tools_before_gateway() -> None:
    gateway = _Gateway(())
    unavailable = ModelExecutor(gateway, None, max_tool_calls=4)
    with pytest.raises(ResolutionError, match="not configured"):
        await unavailable.complete(
            MODEL_ROUTES[2],
            Request("/claude/sonnet-4.6", "Q", "A", {"tools": "web_search"}),
        )

    research = _Research()
    unsupported = ModelExecutor(gateway, research, max_tool_calls=4)
    with pytest.raises(ResolutionError, match="does not support"):
        await unsupported.complete(
            MODEL_ROUTES[0],
            Request("/codex/gpt-5.5", "Q", "A", {"tools": "web_search"}),
        )
    with pytest.raises(ResolutionError, match="unsupported tool"):
        await unsupported.complete(
            MODEL_ROUTES[1],
            Request("/gemini/2.5-flash", "Q", "A", {"tools": "code_execution"}),
        )

    assert gateway.requests == []


@pytest.mark.asyncio
async def test_executor_rejects_malformed_calls_and_enforces_total_call_limit() -> None:
    malformed_gateway = _Gateway((AssistantTurn(None, (ToolCall("x", "web_search", "not-json"),)),))
    research = _Research()
    malformed = ModelExecutor(malformed_gateway, research, max_tool_calls=2)
    with pytest.raises(ResolutionError, match="valid JSON object"):
        await malformed.complete(
            MODEL_ROUTES[2],
            Request("/claude/sonnet-4.6", "Q", "A", {"tools": "web_search"}),
        )

    limited_gateway = _Gateway(
        (
            AssistantTurn(
                None,
                (
                    ToolCall("1", "web_search", '{"query":"one"}'),
                    ToolCall("2", "web_search", '{"query":"two"}'),
                ),
            ),
        )
    )
    limited = ModelExecutor(limited_gateway, research, max_tool_calls=1)
    with pytest.raises(ResolutionError, match="tool-call limit"):
        await limited.complete(
            MODEL_ROUTES[2],
            Request("/claude/sonnet-4.6", "Q", "A", {"tools": "web_search"}),
        )


@pytest.mark.asyncio
async def test_executor_validates_tool_names_and_arguments() -> None:
    cases = (
        (ToolCall("1", "shell", "{}"), "undeclared tool"),
        (ToolCall("1", "web_search", "{}"), "non-empty query"),
        (ToolCall("1", "web_search", '{"query":"x","extra":1}'), "exactly"),
        (ToolCall("1", "web_fetch", "{}"), "non-empty URL"),
    )
    for tool_call, message in cases:
        gateway = _Gateway((AssistantTurn(None, (tool_call,)),))
        executor = ModelExecutor(gateway, _Research(), max_tool_calls=2)
        with pytest.raises(ResolutionError, match=message):
            await executor.complete(
                MODEL_ROUTES[2],
                Request("/claude/sonnet-4.6", "Q", "A", {"tools": "web_search"}),
            )


@pytest.mark.asyncio
async def test_executor_returns_transient_fetch_failure_to_model_but_rejects_unsafe_url() -> None:
    class FailingResearch(_Research):
        def __init__(self, *, permanent: bool) -> None:
            super().__init__()
            self.permanent = permanent

        async def fetch(self, url: str) -> str:
            self.fetches.append(url)
            raise ResolutionError(
                "page unavailable",
                code="malformed_source" if self.permanent else None,
                permanent=self.permanent,
            )

    request = Request("/claude/sonnet-4.6", "Q", "A", {"tools": "web_search"})
    transient_gateway = _Gateway(
        (
            AssistantTurn(
                None,
                (ToolCall("fetch_1", "web_fetch", '{"url":"https://example.org"}'),),
            ),
            AssistantTurn("Answer from remaining evidence", ()),
        )
    )
    transient = ModelExecutor(
        transient_gateway,
        FailingResearch(permanent=False),
        max_tool_calls=2,
    )

    answer = await transient.complete(MODEL_ROUTES[2], request)

    assert answer == "Answer from remaining evidence"
    assert transient_gateway.requests[1][1][-1] == {
        "role": "tool",
        "tool_call_id": "fetch_1",
        "name": "web_fetch",
        "content": '{"url":"https://example.org","error":"page unavailable"}',
    }

    permanent_gateway = _Gateway(
        (
            AssistantTurn(
                None,
                (ToolCall("fetch_1", "web_fetch", '{"url":"http://127.0.0.1"}'),),
            ),
        )
    )
    permanent = ModelExecutor(
        permanent_gateway,
        FailingResearch(permanent=True),
        max_tool_calls=2,
    )

    with pytest.raises(ResolutionError, match="page unavailable"):
        await permanent.complete(MODEL_ROUTES[2], request)
