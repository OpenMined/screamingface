from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

import pytest
from url4 import Request, ResolutionError

from screamingface_engine.catalog import ModelRoute
from screamingface_engine.executor import ModelExecutor
from screamingface_engine.gateway import AssistantTurn, ToolCall
from screamingface_engine.tool_policy import TOOL_POLICY_SCHEMA, FetchPolicy, SearchPolicy

HF_MODEL = ModelRoute(
    "huggingface/deepseek-ai/DeepSeek-V4-Pro~deepinfra",
    "huggingface/deepseek-ai/DeepSeek-V4-Pro:deepinfra",
    "huggingface",
    ("web_search", "web_fetch"),
    "tavily",
)
OPENROUTER_MODEL = ModelRoute(
    "openrouter/google/gemini-3.1-pro-preview",
    "openrouter/google/gemini-3.1-pro-preview",
    "openrouter",
    ("web_search", "web_fetch"),
    "openrouter",
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
        self, url: str, policy: FetchPolicy, *, query: str | None
    ) -> dict[str, object]:
        self.calls.append(("fetch", url, query))
        return {"url": url, "content": "Evidence", "truncated": False}


def _params(*, tools: str = "web_search:web_fetch", calls: int = 12) -> dict[str, str]:
    values = {
        "tools": tools,
        "tools.max_calls": str(calls),
        "temperature": "0.2",
    }
    if "web_search" in tools:
        values["web_search.max_results"] = "5"
        values["web_search.exclude_domain.1"] = "blocked.example"
    return values


def _referenced_context(question: str = "Research question") -> str:
    return json.dumps(
        {
            "schema": "screamingface.model-input.v1",
            "question": question,
            "tool_policy": json.dumps(
                {
                    "schema": TOOL_POLICY_SCHEMA,
                    "tools": ["web_search", "web_fetch"],
                    "max_calls": 3,
                    "web_search": {
                        "max_results": 5,
                        "include_domains": [],
                        "exclude_domains": ["blocked.example"],
                    },
                }
            ),
        }
    )


@pytest.mark.asyncio
async def test_tavily_agent_loop_executes_calls_and_returns_plaintext() -> None:
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

    answer = await ModelExecutor(gateway, tavily).complete(
        HF_MODEL,
        Request(HF_MODEL.route, "Research question", "Answer with sources", _params()),
    )

    assert answer == "Final researched answer"
    assert [call[:2] for call in tavily.calls] == [
        ("search", "first"),
        ("fetch", "https://example.org"),
    ]
    assert gateway.requests[0][2] == {"temperature": "0.2"}
    assert {
        tool["function"]["name"]  # type: ignore[index]
        for tool in gateway.requests[0][3]
    } == {"web_search", "web_fetch"}
    assert [message["tool_call_id"] for message in gateway.requests[1][1][3:]] == [
        "search_1",
        "fetch_1",
    ]


@pytest.mark.asyncio
async def test_openrouter_uses_managed_tools_without_tavily() -> None:
    gateway = Gateway((AssistantTurn("Managed answer", ()),))
    tavily = Tavily(connected=False)

    answer = await ModelExecutor(gateway, tavily).complete(
        OPENROUTER_MODEL,
        Request(OPENROUTER_MODEL.route, "Question", "Research", _params(calls=3)),
    )

    assert answer == "Managed answer"
    assert tavily.calls == []
    assert gateway.requests[0][3] == (
        {
            "type": "openrouter:web_search",
            "parameters": {
                "engine": "auto",
                "max_results": 5,
                "max_total_results": 15,
                "excluded_domains": ["blocked.example"],
            },
        },
        {
            "type": "openrouter:web_fetch",
            "parameters": {
                "engine": "native",
                "max_uses": 3,
                "blocked_domains": ["blocked.example"],
            },
        },
    )


@pytest.mark.asyncio
async def test_openrouter_resolves_versioned_policy_envelope_without_inline_tool_params() -> None:
    gateway = Gateway((AssistantTurn("Managed answer", ()),))
    tavily = Tavily(connected=False)

    answer = await ModelExecutor(gateway, tavily).complete(
        OPENROUTER_MODEL,
        Request(
            OPENROUTER_MODEL.route,
            _referenced_context(),
            "Research",
            {"temperature": "0.2"},
        ),
    )

    assert answer == "Managed answer"
    assert gateway.requests[0][1][-1] == {"role": "user", "content": "Research question"}
    assert gateway.requests[0][2] == {"temperature": "0.2"}
    assert gateway.requests[0][3][0]["type"] == "openrouter:web_search"
    assert tavily.calls == []


@pytest.mark.asyncio
async def test_model_input_rejects_ambiguous_inline_and_referenced_policy() -> None:
    gateway = Gateway(())
    with pytest.raises(ResolutionError) as captured:
        await ModelExecutor(gateway, Tavily()).complete(
            OPENROUTER_MODEL,
            Request(OPENROUTER_MODEL.route, _referenced_context(), "Research", _params()),
        )
    assert captured.value.code == "malformed_tool_policy"
    assert gateway.requests == []


@pytest.mark.asyncio
async def test_model_input_rejects_duplicate_envelope_fields() -> None:
    gateway = Gateway(())
    context = (
        '{"schema":"screamingface.model-input.v1",'
        '"schema":"screamingface.model-input.v1",'
        '"question":"Question","tool_policy":{}}'
    )

    with pytest.raises(ResolutionError, match="unique JSON fields") as captured:
        await ModelExecutor(gateway, Tavily()).complete(
            OPENROUTER_MODEL,
            Request(OPENROUTER_MODEL.route, context, "Research", {}),
        )

    assert captured.value.code == "malformed_tool_policy"
    assert gateway.requests == []


@pytest.mark.asyncio
async def test_tool_free_request_never_checks_tavily() -> None:
    gateway = Gateway((AssistantTurn("Direct answer", ()),))
    tavily = Tavily(connected=False)
    answer = await ModelExecutor(gateway, tavily).complete(
        TOOL_FREE_MODEL,
        Request(TOOL_FREE_MODEL.route, "Question", "Answer", {"max_tokens": "8"}),
    )
    assert answer == "Direct answer"
    assert gateway.requests[0][3] == ()
    assert tavily.calls == []


@pytest.mark.asyncio
async def test_missing_tavily_and_unsupported_route_fail_before_spend() -> None:
    gateway = Gateway(())
    with pytest.raises(ResolutionError) as missing:
        await ModelExecutor(gateway, Tavily(connected=False)).complete(
            HF_MODEL,
            Request(HF_MODEL.route, "Q", "A", _params(tools="web_search")),
        )
    assert missing.value.code == "authentication_required"

    with pytest.raises(ResolutionError) as unsupported:
        await ModelExecutor(gateway, Tavily()).complete(
            TOOL_FREE_MODEL,
            Request(TOOL_FREE_MODEL.route, "Q", "A", _params(tools="web_search")),
        )
    assert unsupported.value.code == "unsupported_tool"
    assert gateway.requests == []


@pytest.mark.asyncio
async def test_invalid_arguments_are_returned_to_the_model_for_correction() -> None:
    gateway = Gateway(
        (
            AssistantTurn(None, (ToolCall("bad", "web_search", "not-json"),)),
            AssistantTurn("Recovered answer", ()),
        )
    )
    tavily = Tavily()
    answer = await ModelExecutor(gateway, tavily).complete(
        HF_MODEL,
        Request(HF_MODEL.route, "Q", "A", _params(tools="web_search")),
    )
    assert answer == "Recovered answer"
    content = gateway.requests[1][1][-1]["content"]
    assert isinstance(content, str)
    assert json.loads(content)["error"]["code"] == "invalid_tool_arguments"


@pytest.mark.asyncio
async def test_tool_call_budget_is_counted_as_calls_not_model_turns() -> None:
    gateway = Gateway(
        (
            AssistantTurn(
                None,
                (
                    ToolCall("one", "web_search", '{"query":"one"}'),
                    ToolCall("two", "web_search", '{"query":"two"}'),
                ),
            ),
        )
    )
    tavily = Tavily()
    with pytest.raises(ResolutionError) as captured:
        await ModelExecutor(gateway, tavily).complete(
            HF_MODEL,
            Request(HF_MODEL.route, "Q", "A", _params(tools="web_search", calls=1)),
        )
    assert captured.value.code == "tool_budget_exhausted"
    assert tavily.calls == []
