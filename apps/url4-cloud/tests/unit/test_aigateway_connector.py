"""``build_aigateway_world`` — the aigateway connector (plan §5.2/§7 Batch 2).

Every test drives the real ``url4.dag.run``/``Url4Node`` machinery against a stubbed
aigateway (``httpx.MockTransport``, injected via ``build_aigateway_world``'s ``client=``
param) — no mocking of the engine or of ``Url4Node`` itself.

**Processor-selection tests (`;processor=` forms).** There is no in-expression ``;processor=``
surface token: `packages/url4/tests/spec/test_processor_delegation.py` confirms
``processor`` is either a top-level ``url4.dag.run(text, io=, processor=...)`` kwarg or the
HTTP wire query param ``?processor=...&q=...`` a node consumes at its eval path — both feed
the same ``ctx.processor``, consulted only by a fan-out **reduce** dispatch
(``FanoutReduceNode`` / ``resolve_processor_target``). So the three selection-form tests here
drive a genuine one-source fan-out+reduce expression (mirroring ``test_processor_delegation``'s
own ``_FANOUT`` shape) and pass ``processor=`` the way that spec suite does; a bare single
relative call (no wrapping parens) never consults ``ctx.processor`` at all, and is used for the
route-explicit tests (handler return value, usage, error mapping) instead.
"""

from __future__ import annotations

import json
from unittest import mock

import httpx
import pytest
from url4.core.errors import ResolutionError
from url4.dag import run as url4_run
from url4.observe import ObservationEvent, Usage

from url4_cloud_runner.aigateway_connector import AigatewayConfig, build_aigateway_world

pytestmark = pytest.mark.asyncio

_TOKEN = "test-token"  # noqa: S105 - not a real credential
_TAVILY_TOKEN = "tvly-test"  # noqa: S105 - not a real credential

# A single-source fan-out+reduce expression (mirrors test_processor_delegation.py's _FANOUT):
# the source itself calls openrouter/gpt-4o; the reduce step is where `processor=` (or the
# node's default_processor, for the bare-intent test) picks the target model.
_FANOUT = "(/openrouter/gpt-4o(ctx)!probe)!combine"


class _Recorder:
    """A minimal ``Observer`` that records every event (esp. ``Usage``)."""

    def __init__(self) -> None:
        self.events: list[ObservationEvent] = []

    def on_event(self, event: ObservationEvent) -> None:
        self.events.append(event)


class _MockAigateway:
    """A stub aigateway: ``GET /v1/models`` + ``POST /v1/chat/completions`` over a
    ``httpx.MockTransport``. ``responses`` maps a model id to one of:

    - a canned completion string — 200, with the standard usage block;
    - an ``(status, detail)`` pair — an error response;
    - a raw ``dict`` — returned verbatim as the 200 JSON body (F2/F5: malformed shapes,
      or a response with no ``usage`` key at all).
    """

    def __init__(
        self,
        models: tuple[str, ...],
        *,
        responses: dict[str, str | tuple[int, dict] | dict | list] | None = None,
    ) -> None:
        self.models = models
        self.responses = responses or {}
        self.requests: list[httpx.Request] = []
        # Per-model cursor for list-valued ``responses`` (consumed in order; the web-tools
        # agentic loop needs round 1 = tool_calls, round 2 = final content).
        self._seq_index: dict[str, int] = {}

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.headers["authorization"] == f"Bearer {_TOKEN}"
        if request.url.path == "/v1/models":
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": [{"id": m, "owned_by": "test"} for m in self.models],
                },
            )
        assert request.url.path == "/v1/chat/completions"
        return self._chat_completion_response(request)

    def _chat_completion_response(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        model = body["model"]
        outcome = self.responses.get(model, "default completion")
        # A list outcome is consumed in order across the loop's round-trips; once
        # exhausted it repeats the last entry (so a constant-tool-call model drives
        # the max-iterations test without a separate fixture).
        if isinstance(outcome, list):
            idx = self._seq_index.get(model, 0)
            if idx >= len(outcome):
                idx = len(outcome) - 1
            else:
                self._seq_index[model] = idx + 1
            outcome = outcome[idx]
        if isinstance(outcome, tuple):
            status, detail = outcome
            return httpx.Response(status, json={"detail": detail})
        if isinstance(outcome, dict):
            return httpx.Response(200, json=outcome)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": outcome}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
            },
        )

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.MockTransport(self._handle), base_url="http://aigateway.test"
        )

    def posts_to(self, model: str) -> list[httpx.Request]:
        return [
            r
            for r in self.requests
            if r.url.path == "/v1/chat/completions" and json.loads(r.content)["model"] == model
        ]


def _tool_call(name: str, arguments: dict, *, id_: str = "call_1") -> dict:
    """An OpenAI-shape tool_calls entry: id/type/function{name, arguments-as-JSON}."""
    return {
        "id": id_,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }


def _tool_calls_body(
    tool_calls: list[dict], *, content: str | None = None, usage: dict | None = None
) -> dict:
    """A 200 chat-completion response whose assistant message wants tool calls."""
    return {
        "choices": [
            {"message": {"role": "assistant", "content": content, "tool_calls": tool_calls}}
        ],
        "usage": usage or {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
    }


class _MockTavily:
    """A stub Tavily: ``POST /search`` + ``POST /extract`` over a ``httpx.MockTransport``.

    ``search_results`` / ``extract_results`` / ``search_status`` / ``extract_status`` drive
    the canned responses; every request is recorded so tests assert the query, body, and
    the bearer key. ``base_url`` matches the connector's default Tavily base.
    """

    BASE_URL = "https://api.tavily.com"

    def __init__(
        self,
        *,
        search_results: list[dict] | None = None,
        extract_results: list[dict] | None = None,
        extract_failed: list[dict] | None = None,
        search_status: int = 200,
        extract_status: int = 200,
        search_error: str = "boom",
        extract_error: str = "boom",
    ) -> None:
        self.search_results = search_results if search_results is not None else []
        self.extract_results = extract_results if extract_results is not None else []
        self.extract_failed = extract_failed if extract_failed is not None else []
        self.search_status = search_status
        self.extract_status = extract_status
        self.search_error = search_error
        self.extract_error = extract_error
        self.requests: list[httpx.Request] = []

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.headers["authorization"] == f"Bearer {_TAVILY_TOKEN}"
        if request.url.path == "/search":
            return self._search_response()
        assert request.url.path == "/extract"
        return self._extract_response()

    def _search_response(self) -> httpx.Response:
        if self.search_status != 200:
            return httpx.Response(self.search_status, json={"detail": {"error": self.search_error}})
        return httpx.Response(200, json={"results": self.search_results, "response_time": 0.1})

    def _extract_response(self) -> httpx.Response:
        if self.extract_status != 200:
            return httpx.Response(
                self.extract_status, json={"detail": {"error": self.extract_error}}
            )
        return httpx.Response(
            200,
            json={
                "results": self.extract_results,
                "failed_results": self.extract_failed,
                "response_time": 0.1,
            },
        )

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.MockTransport(self._handle), base_url=self.BASE_URL
        )

    def posts_to(self, path: str) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path == path]


# --- 1. catalog fetch + route registration; models= override skips GET /v1/models -------------


async def test_build_world_fetches_catalog_and_registers_routes_plus_unique_aliases() -> None:
    gw = _MockAigateway(("anthropic/claude-haiku-4-5", "openrouter/gpt-4o"))
    cfg = AigatewayConfig(default_model="anthropic/claude-haiku-4-5")
    async with gw.client() as client:
        world = await build_aigateway_world(cfg, token=_TOKEN, client=client)

        assert set(world.node.processor_routes()) == {
            "/anthropic/claude-haiku-4-5",
            "/openrouter/gpt-4o",
            "/claude-haiku-4-5",
            "/gpt-4o",
        }
        assert any(r.url.path == "/v1/models" for r in gw.requests)


async def test_models_override_skips_the_v1_models_fetch() -> None:
    gw = _MockAigateway(("anthropic/claude-haiku-4-5",))  # never consulted by the override
    cfg = AigatewayConfig(
        default_model="anthropic/claude-haiku-4-5",
        models=("anthropic/claude-haiku-4-5",),
    )
    async with gw.client() as client:
        world = await build_aigateway_world(cfg, token=_TOKEN, client=client)

        assert set(world.node.processor_routes()) == {
            "/anthropic/claude-haiku-4-5",
            "/claude-haiku-4-5",
        }
        assert not any(r.url.path == "/v1/models" for r in gw.requests)


# --- 2. all three `processor=` forms drive the reduce to the same named model -----------------


@pytest.mark.parametrize(
    "processor_value",
    ["/anthropic/claude-haiku-4-5", "anthropic/claude-haiku-4-5", "claude-haiku-4-5"],
)
async def test_all_three_processor_forms_select_the_named_model(processor_value: str) -> None:
    gw = _MockAigateway(("anthropic/claude-haiku-4-5", "openrouter/gpt-4o"))
    cfg = AigatewayConfig(default_model="anthropic/claude-haiku-4-5")
    async with gw.client() as client:
        world = await build_aigateway_world(cfg, token=_TOKEN, client=client)

        await url4_run(_FANOUT, io=world.node, processor=processor_value)

        assert len(gw.posts_to("anthropic/claude-haiku-4-5")) == 1  # the reduce call
        assert len(gw.posts_to("openrouter/gpt-4o")) == 1  # the fan-out's own source call


# --- 3. a bare `!intent` (no processor=) uses default_model -----------------------------------


async def test_bare_reduce_with_no_processor_uses_the_default_model() -> None:
    gw = _MockAigateway(("anthropic/claude-haiku-4-5", "openrouter/gpt-4o"))
    cfg = AigatewayConfig(default_model="anthropic/claude-haiku-4-5")
    async with gw.client() as client:
        world = await build_aigateway_world(cfg, token=_TOKEN, client=client)

        await url4_run(_FANOUT, io=world.node)  # no processor= — falls back to default_processor

        assert len(gw.posts_to("anthropic/claude-haiku-4-5")) == 1


# --- 4. the handler returns choices[0].message.content -----------------------------------------


async def test_handler_returns_the_completion_content() -> None:
    gw = _MockAigateway(
        ("anthropic/claude-haiku-4-5",),
        responses={"anthropic/claude-haiku-4-5": "hello there"},
    )
    cfg = AigatewayConfig(default_model="anthropic/claude-haiku-4-5")
    async with gw.client() as client:
        world = await build_aigateway_world(cfg, token=_TOKEN, client=client)

        result = await url4_run("/anthropic/claude-haiku-4-5(ctx)!go", io=world.node)

        assert result == "hello there"


# --- 5. usage is reported via the engine's usage sink, attributed to this route ----------------


async def test_usage_is_reported_for_this_route_via_the_engine_observer() -> None:
    gw = _MockAigateway(("anthropic/claude-haiku-4-5",))
    cfg = AigatewayConfig(default_model="anthropic/claude-haiku-4-5")
    recorder = _Recorder()
    async with gw.client() as client:
        world = await build_aigateway_world(cfg, token=_TOKEN, client=client)

        await url4_run("/anthropic/claude-haiku-4-5(ctx)!go", io=world.node, observer=recorder)

    usage_events = [e for e in recorder.events if isinstance(e, Usage)]
    assert len(usage_events) == 1
    usage = usage_events[0]
    assert usage.provider == "anthropic"
    assert usage.model == "anthropic/claude-haiku-4-5"
    assert usage.input_tokens == 11  # prompt_tokens
    assert usage.output_tokens == 7  # completion_tokens


async def test_usage_provider_is_anthropic_for_a_bare_unprefixed_model() -> None:
    # Regression: aigateway's catalog convention leaves Anthropic entries bare (no
    # `<provider>/` prefix, see AigatewayConfig.default_model) — the connector's own default
    # model is exactly this shape, so `provider` must not fall back to splitting on "/" and
    # misattributing the whole bare model id as its own provider.
    gw = _MockAigateway(("claude-haiku-4-5",))
    cfg = AigatewayConfig(default_model="claude-haiku-4-5")
    recorder = _Recorder()
    async with gw.client() as client:
        world = await build_aigateway_world(cfg, token=_TOKEN, client=client)

        await url4_run("/claude-haiku-4-5(ctx)!go", io=world.node, observer=recorder)

    usage_events = [e for e in recorder.events if isinstance(e, Usage)]
    assert len(usage_events) == 1
    assert usage_events[0].provider == "anthropic"
    assert usage_events[0].model == "claude-haiku-4-5"


# --- 6. a colliding bare name across two providers registers NO alias -------------------------


async def test_colliding_bare_name_registers_no_alias_and_bare_id_is_unknown() -> None:
    gw = _MockAigateway(("anthropic/x", "openrouter/x"))
    cfg = AigatewayConfig(default_model="anthropic/x")
    async with gw.client() as client:
        world = await build_aigateway_world(cfg, token=_TOKEN, client=client)

        assert set(world.node.processor_routes()) == {"/anthropic/x", "/openrouter/x"}

        fanout = "(/anthropic/x(ctx)!probe)!combine"
        with pytest.raises(ResolutionError) as exc_info:
            await url4_run(fanout, io=world.node, processor="x")

    assert exc_info.value.code == "unknown_processor"


# --- 7. a model NOT in the catalog fails at resolve time, before any completion POST for it ---


async def test_unregistered_model_id_fails_before_any_completion_call() -> None:
    gw = _MockAigateway(("anthropic/claude-haiku-4-5",))
    cfg = AigatewayConfig(default_model="anthropic/claude-haiku-4-5")
    async with gw.client() as client:
        world = await build_aigateway_world(cfg, token=_TOKEN, client=client)

        fanout = "(/anthropic/claude-haiku-4-5(ctx)!probe)!combine"
        with pytest.raises(ResolutionError) as exc_info:
            await url4_run(fanout, io=world.node, processor="not-a-real-model")

    assert exc_info.value.code == "unknown_processor"
    assert gw.posts_to("not-a-real-model") == []
    # The fan-out's own source call is a real dependency and DOES run; the invalid processor
    # target itself is classified/looked-up before any I/O and never reaches the transport —
    # so only that one (valid) source call is ever posted.
    assert len(gw.posts_to("anthropic/claude-haiku-4-5")) == 1


# --- 8. aigateway HTTP errors map to ResolutionError with the right permanence ------------------


@pytest.mark.parametrize(
    ("status", "detail", "expected_permanent"),
    [
        (401, {"code": "invalid_credential", "message": "bad token"}, True),
        (402, {"code": "quota_exceeded", "message": "no budget"}, True),
        (429, {"code": "rate_limited", "message": "slow down"}, False),
        (503, {"code": "upstream_unavailable", "message": "down"}, False),
    ],
)
async def test_aigateway_http_errors_map_to_resolution_error(
    status: int, detail: dict, expected_permanent: bool
) -> None:
    gw = _MockAigateway(
        ("anthropic/claude-haiku-4-5",),
        responses={"anthropic/claude-haiku-4-5": (status, detail)},
    )
    cfg = AigatewayConfig(default_model="anthropic/claude-haiku-4-5")
    async with gw.client() as client:
        world = await build_aigateway_world(cfg, token=_TOKEN, client=client)

        with pytest.raises(ResolutionError) as exc_info:
            await url4_run("/anthropic/claude-haiku-4-5(ctx)!go", io=world.node)

    assert exc_info.value.code == detail["code"]
    assert exc_info.value.permanent is expected_permanent


# --- 9. default_model not in the catalog -> ValueError at world-build time ---------------------


async def test_default_model_not_in_catalog_raises_value_error() -> None:
    gw = _MockAigateway(("openrouter/gpt-4o",))
    cfg = AigatewayConfig(default_model="anthropic/claude-haiku-4-5", models=("openrouter/gpt-4o",))
    async with gw.client() as client:
        with pytest.raises(ValueError, match="anthropic/claude-haiku-4-5"):
            await build_aigateway_world(cfg, token=_TOKEN, client=client)


# --- 10. F1: owned vs. injected client teardown (design review) --------------------------------


async def test_owned_client_is_created_and_closed_by_aclose() -> None:
    # No client= given: build_aigateway_world creates + owns one itself. `models=` skips the
    # /v1/models fetch, so no real network I/O happens before we assert on close bookkeeping.
    cfg = AigatewayConfig(
        default_model="anthropic/claude-haiku-4-5", models=("anthropic/claude-haiku-4-5",)
    )

    world = await build_aigateway_world(cfg, token=_TOKEN)

    assert world._owns_client is True
    assert world._client.is_closed is False

    await world.aclose()

    assert world._client.is_closed is True


async def test_injected_client_is_not_closed_by_aclose() -> None:
    gw = _MockAigateway(("anthropic/claude-haiku-4-5",))
    cfg = AigatewayConfig(default_model="anthropic/claude-haiku-4-5")
    async with gw.client() as client:
        world = await build_aigateway_world(cfg, token=_TOKEN, client=client)

        assert world._owns_client is False

        await world.aclose()

        assert client.is_closed is False


async def test_owned_client_is_closed_when_default_model_is_missing_from_catalog() -> None:
    # F1: the ValueError path (no AigatewayWorld is ever returned to introspect) must still
    # close the client it created — spy on AsyncClient.aclose to prove it fires.
    cfg = AigatewayConfig(default_model="not/in-catalog", models=("anthropic/claude-haiku-4-5",))
    closed: list[bool] = []
    real_aclose = httpx.AsyncClient.aclose

    async def _spy_aclose(self: httpx.AsyncClient) -> None:
        closed.append(True)
        await real_aclose(self)

    with (
        mock.patch.object(httpx.AsyncClient, "aclose", _spy_aclose),
        pytest.raises(ValueError, match="not/in-catalog"),
    ):
        await build_aigateway_world(cfg, token=_TOKEN)

    assert closed == [True]


# --- 11. F2: a malformed 200 response maps to ResolutionError, not a raw builtin exception ------


async def test_malformed_completion_response_raises_resolution_error() -> None:
    gw = _MockAigateway(
        ("anthropic/claude-haiku-4-5",), responses={"anthropic/claude-haiku-4-5": {}}
    )
    cfg = AigatewayConfig(default_model="anthropic/claude-haiku-4-5")
    async with gw.client() as client:
        world = await build_aigateway_world(cfg, token=_TOKEN, client=client)

        with pytest.raises(ResolutionError) as exc_info:
            await url4_run("/anthropic/claude-haiku-4-5(ctx)!go", io=world.node)

    assert exc_info.value.code == "aigateway_bad_response"
    assert exc_info.value.permanent is True


async def test_malformed_models_list_response_raises_resolution_error() -> None:
    class _BadCatalogGateway(_MockAigateway):
        def _handle(self, request: httpx.Request) -> httpx.Response:
            if request.url.path == "/v1/models":
                self.requests.append(request)
                return httpx.Response(200, json={"object": "list", "data": [{"no_id": "x"}]})
            return super()._handle(request)

    gw = _BadCatalogGateway(())
    cfg = AigatewayConfig(default_model="anthropic/claude-haiku-4-5")
    async with gw.client() as client:
        with pytest.raises(ResolutionError) as exc_info:
            await build_aigateway_world(cfg, token=_TOKEN, client=client)

    assert exc_info.value.code == "aigateway_bad_response"
    assert exc_info.value.permanent is True


# --- 12. F5: no usage block in the response -> no Usage event, completion still returned -------


async def test_no_usage_block_reports_no_usage_event_but_still_returns_content() -> None:
    gw = _MockAigateway(
        ("anthropic/claude-haiku-4-5",),
        responses={
            "anthropic/claude-haiku-4-5": {"choices": [{"message": {"content": "no usage here"}}]}
        },
    )
    cfg = AigatewayConfig(default_model="anthropic/claude-haiku-4-5")
    recorder = _Recorder()
    async with gw.client() as client:
        world = await build_aigateway_world(cfg, token=_TOKEN, client=client)

        result = await url4_run(
            "/anthropic/claude-haiku-4-5(ctx)!go", io=world.node, observer=recorder
        )

    assert result == "no usage here"
    assert [e for e in recorder.events if isinstance(e, Usage)] == []


# ============================================================================
# Web tools (Tavily): web_search / web_fetch — spec 2026-07-23 (RED-first)
# A connector-side bounded agentic loop: declare the tools when a Tavily key is
# present, execute the model's tool_calls against Tavily Search/Extract, feed the
# results back as role:"tool" messages, and re-call until a final answer or the
# iteration cap. No key -> no tools -> byte-identical to today (deny-by-default).
# ============================================================================

_MODEL = "anthropic/claude-haiku-4-5"


# --- W1. deny-by-default: no TAVILY_API_KEY -> no tools in the request body -----------


async def test_no_tools_when_tavily_key_absent() -> None:
    gw = _MockAigateway((_MODEL,), responses={_MODEL: "plain answer"})
    cfg = AigatewayConfig(default_model=_MODEL)
    async with gw.client() as client:
        world = await build_aigateway_world(cfg, token=_TOKEN, client=client)

        assert world.web_tools_enabled is False
        await url4_run(f"/{_MODEL}(ctx)!go", io=world.node)

    body = json.loads(gw.posts_to(_MODEL)[0].content)
    assert "tools" not in body
    assert "tool_choice" not in body


# --- W2. with a Tavily key, tools are declared + tool_choice=auto ---------------------


async def test_tools_declared_when_tavily_key_present() -> None:
    gw = _MockAigateway((_MODEL,), responses={_MODEL: "plain answer"})
    tvly = _MockTavily()
    cfg = AigatewayConfig(default_model=_MODEL)
    async with gw.client() as client, tvly.client() as tclient:
        world = await build_aigateway_world(
            cfg, token=_TOKEN, client=client, tavily_api_key=_TAVILY_TOKEN, tavily_client=tclient
        )

        assert world.web_tools_enabled is True
        await url4_run(f"/{_MODEL}(ctx)!go", io=world.node)

    body = json.loads(gw.posts_to(_MODEL)[0].content)
    tool_names = {t["function"]["name"] for t in body["tools"]}
    assert tool_names == {"web_search", "web_fetch"}
    assert body["tool_choice"] == "auto"
    # Tavily was never hit (the model returned content on round 1).
    assert tvly.requests == []


# --- W3. web_search loop: tool_calls round 1 -> Tavily -> final answer round 2 ---------


async def test_web_search_loop_executes_tavily_search_then_answers() -> None:
    gw = _MockAigateway(
        (_MODEL,),
        responses={
            _MODEL: [
                _tool_calls_body([_tool_call("web_search", {"query": "who is leo"})]),
                "Leo is a footballer.",
            ]
        },
    )
    tvly = _MockTavily(
        search_results=[
            {"title": "Messi", "url": "https://w/M", "content": "Leo plays football."},
            {"title": "Wiki", "url": "https://w/L", "content": "Born 1987."},
        ]
    )
    cfg = AigatewayConfig(default_model=_MODEL)
    async with gw.client() as client, tvly.client() as tclient:
        world = await build_aigateway_world(
            cfg, token=_TOKEN, client=client, tavily_api_key=_TAVILY_TOKEN, tavily_client=tclient
        )

        result = await url4_run(f"/{_MODEL}(ctx)!go", io=world.node)

    assert result == "Leo is a footballer."
    # Two aigateway POSTs (tool-call turn + final turn), one Tavily /search.
    assert len(gw.posts_to(_MODEL)) == 2
    assert len(tvly.posts_to("/search")) == 1
    tavily_body = json.loads(tvly.posts_to("/search")[0].content)
    assert tavily_body["query"] == "who is leo"
    assert tavily_body["search_depth"] == "advanced"
    assert tavily_body["max_results"] == 5
    # The 2nd aigateway POST threaded the assistant tool-call turn + a role:"tool" result.
    round2_messages = json.loads(gw.posts_to(_MODEL)[1].content)["messages"]
    assert round2_messages[-1]["role"] == "tool"
    assert round2_messages[-1]["tool_call_id"] == "call_1"
    assert "Messi" in round2_messages[-1]["content"]
    assert round2_messages[-2]["role"] == "assistant"
    assert round2_messages[-2]["tool_calls"][0]["function"]["name"] == "web_search"


# --- W4. web_fetch loop: tool_calls round 1 -> Tavily /extract -> final answer ----------


async def test_web_fetch_loop_executes_tavily_extract_then_answers() -> None:
    gw = _MockAigateway(
        (_MODEL,),
        responses={
            _MODEL: [
                _tool_calls_body([_tool_call("web_fetch", {"url": "https://x/page"})]),
                "The page is about cats.",
            ]
        },
    )
    tvly = _MockTavily(extract_results=[{"url": "https://x/page", "raw_content": "# Cats"}])
    cfg = AigatewayConfig(default_model=_MODEL)
    async with gw.client() as client, tvly.client() as tclient:
        world = await build_aigateway_world(
            cfg, token=_TOKEN, client=client, tavily_api_key=_TAVILY_TOKEN, tavily_client=tclient
        )

        result = await url4_run(f"/{_MODEL}(ctx)!go", io=world.node)

    assert result == "The page is about cats."
    assert len(tvly.posts_to("/extract")) == 1
    extract_body = json.loads(tvly.posts_to("/extract")[0].content)
    assert extract_body["urls"] == "https://x/page"
    assert extract_body["format"] == "markdown"
    # The tool result fed back is the extracted raw_content.
    round2_messages = json.loads(gw.posts_to(_MODEL)[1].content)["messages"]
    assert round2_messages[-1]["content"] == "# Cats"


# --- W5. parallel tool calls are executed concurrently (both Tavily endpoints hit) -----


async def test_parallel_tool_calls_both_executed_in_one_turn() -> None:
    gw = _MockAigateway(
        (_MODEL,),
        responses={
            _MODEL: [
                _tool_calls_body(
                    [
                        _tool_call("web_search", {"query": "q1"}, id_="c_search"),
                        _tool_call("web_fetch", {"url": "https://x"}, id_="c_fetch"),
                    ]
                ),
                "merged answer",
            ]
        },
    )
    tvly = _MockTavily(
        search_results=[{"title": "S", "url": "https://s", "content": "sc"}],
        extract_results=[{"url": "https://x", "raw_content": "xc"}],
    )
    cfg = AigatewayConfig(default_model=_MODEL)
    async with gw.client() as client, tvly.client() as tclient:
        world = await build_aigateway_world(
            cfg, token=_TOKEN, client=client, tavily_api_key=_TAVILY_TOKEN, tavily_client=tclient
        )

        result = await url4_run(f"/{_MODEL}(ctx)!go", io=world.node)

    assert result == "merged answer"
    assert len(tvly.posts_to("/search")) == 1
    assert len(tvly.posts_to("/extract")) == 1
    # Both tool results are threaded, in the order of the tool_calls.
    round2_messages = json.loads(gw.posts_to(_MODEL)[1].content)["messages"]
    tool_results = [m for m in round2_messages if m.get("role") == "tool"]
    assert [t["tool_call_id"] for t in tool_results] == ["c_search", "c_fetch"]


# --- W6. usage accumulates across round-trips on the SAME span -------------------------


async def test_usage_accumulates_across_round_trips_on_same_span() -> None:
    gw = _MockAigateway(
        (_MODEL,),
        responses={
            _MODEL: [
                _tool_calls_body(
                    [_tool_call("web_search", {"query": "q"})],
                    usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                ),
                {
                    "choices": [{"message": {"content": "done"}}],
                    "usage": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28},
                },
            ]
        },
    )
    tvly = _MockTavily(search_results=[{"title": "S", "url": "https://s", "content": "c"}])
    cfg = AigatewayConfig(default_model=_MODEL)
    recorder = _Recorder()
    async with gw.client() as client, tvly.client() as tclient:
        world = await build_aigateway_world(
            cfg, token=_TOKEN, client=client, tavily_api_key=_TAVILY_TOKEN, tavily_client=tclient
        )

        await url4_run(f"/{_MODEL}(ctx)!go", io=world.node, observer=recorder)

    usage_events = [e for e in recorder.events if isinstance(e, Usage)]
    assert len(usage_events) == 2
    assert {e.span_id for e in usage_events} == {usage_events[0].span_id}  # same span
    assert sum(e.input_tokens for e in usage_events) == 30
    assert sum(e.output_tokens for e in usage_events) == 13


# --- W7. a Tavily HTTP failure is fed back to the model (dec:W2), not a hard fail ------


async def test_tavily_http_failure_fed_back_to_model_not_raised() -> None:
    gw = _MockAigateway(
        (_MODEL,),
        responses={
            _MODEL: [
                _tool_calls_body([_tool_call("web_search", {"query": "q"})]),
                "I could not find anything.",
            ]
        },
    )
    tvly = _MockTavily(search_status=500, search_error="upstream down")
    cfg = AigatewayConfig(default_model=_MODEL)
    async with gw.client() as client, tvly.client() as tclient:
        world = await build_aigateway_world(
            cfg, token=_TOKEN, client=client, tavily_api_key=_TAVILY_TOKEN, tavily_client=tclient
        )

        result = await url4_run(f"/{_MODEL}(ctx)!go", io=world.node)

    assert result == "I could not find anything."
    # The model saw the failure as the tool result text and still answered.
    round2_messages = json.loads(gw.posts_to(_MODEL)[1].content)["messages"]
    assert round2_messages[-1]["role"] == "tool"
    assert "web_search failed" in round2_messages[-1]["content"]


# --- W8. unknown tool name + invalid arguments are fed back, not raised ----------------


async def test_unknown_tool_name_fed_back_to_model() -> None:
    gw = _MockAigateway(
        (_MODEL,),
        responses={
            _MODEL: [
                _tool_calls_body([_tool_call("calc", {"x": 1})]),
                "I can't calculate.",
            ]
        },
    )
    tvly = _MockTavily()
    cfg = AigatewayConfig(default_model=_MODEL)
    async with gw.client() as client, tvly.client() as tclient:
        world = await build_aigateway_world(
            cfg, token=_TOKEN, client=client, tavily_api_key=_TAVILY_TOKEN, tavily_client=tclient
        )

        result = await url4_run(f"/{_MODEL}(ctx)!go", io=world.node)

    assert result == "I can't calculate."
    round2_messages = json.loads(gw.posts_to(_MODEL)[1].content)["messages"]
    assert round2_messages[-1]["content"] == "unknown tool: calc"


async def test_invalid_tool_arguments_fed_back_to_model() -> None:
    bad_call = {
        "id": "call_1",
        "type": "function",
        "function": {"name": "web_search", "arguments": "not-json"},
    }
    gw = _MockAigateway(
        (_MODEL,),
        responses={_MODEL: [_tool_calls_body([bad_call]), "recovered."]},
    )
    tvly = _MockTavily()
    cfg = AigatewayConfig(default_model=_MODEL)
    async with gw.client() as client, tvly.client() as tclient:
        world = await build_aigateway_world(
            cfg, token=_TOKEN, client=client, tavily_api_key=_TAVILY_TOKEN, tavily_client=tclient
        )

        result = await url4_run(f"/{_MODEL}(ctx)!go", io=world.node)

    assert result == "recovered."
    round2_messages = json.loads(gw.posts_to(_MODEL)[1].content)["messages"]
    assert round2_messages[-1]["content"] == "invalid arguments for web_search"


# --- W9. exceeding the iteration cap raises ResolutionError(web_tool_loop_limit) -------


async def test_max_iterations_exceeded_raises_resolution_error() -> None:
    gw = _MockAigateway(
        (_MODEL,),
        # The model ALWAYS wants a tool call; the list repeats the last entry once exhausted.
        responses={_MODEL: [_tool_calls_body([_tool_call("web_search", {"query": "q"})])]},
    )
    tvly = _MockTavily(search_results=[{"title": "S", "url": "https://s", "content": "c"}])
    cfg = AigatewayConfig(default_model=_MODEL, web_tool_max_iterations=2)
    async with gw.client() as client, tvly.client() as tclient:
        world = await build_aigateway_world(
            cfg, token=_TOKEN, client=client, tavily_api_key=_TAVILY_TOKEN, tavily_client=tclient
        )

        with pytest.raises(ResolutionError) as exc_info:
            await url4_run(f"/{_MODEL}(ctx)!go", io=world.node)

    assert exc_info.value.code == "web_tool_loop_limit"
    assert exc_info.value.permanent is False
    # Exactly web_tool_max_iterations aigateway POSTs were made.
    assert len(gw.posts_to(_MODEL)) == 2


# --- W10. _extract_content tolerates content=None + tool_calls (regression guard) -------


async def test_extract_content_tolerates_content_none_with_tool_calls() -> None:
    body_with_tools = {
        "choices": [
            {"message": {"content": None, "tool_calls": [_tool_call("web_search", {"query": "q"})]}}
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
    gw = _MockAigateway((_MODEL,), responses={_MODEL: [body_with_tools, "final."]})
    tvly = _MockTavily(search_results=[{"title": "S", "url": "https://s", "content": "c"}])
    cfg = AigatewayConfig(default_model=_MODEL)
    async with gw.client() as client, tvly.client() as tclient:
        world = await build_aigateway_world(
            cfg, token=_TOKEN, client=client, tavily_api_key=_TAVILY_TOKEN, tavily_client=tclient
        )

        result = await url4_run(f"/{_MODEL}(ctx)!go", io=world.node)

    assert result == "final."


async def test_malformed_neither_content_nor_tool_calls_still_raises() -> None:
    gw = _MockAigateway((_MODEL,), responses={_MODEL: {"choices": [{"message": {}}]}})
    cfg = AigatewayConfig(default_model=_MODEL)
    async with gw.client() as client:
        world = await build_aigateway_world(cfg, token=_TOKEN, client=client)

        with pytest.raises(ResolutionError) as exc_info:
            await url4_run(f"/{_MODEL}(ctx)!go", io=world.node)

    assert exc_info.value.code == "aigateway_bad_response"
    assert exc_info.value.permanent is True


# --- W11. Tavily client teardown parity (owned closed / injected not / aigateway independent) -


async def test_owned_tavily_client_closed_on_aclose() -> None:
    cfg = AigatewayConfig(default_model=_MODEL, models=(_MODEL,))
    world = await build_aigateway_world(cfg, token=_TOKEN, tavily_api_key=_TAVILY_TOKEN)

    assert world._owns_tavily_client is True
    assert world._tavily_client is not None
    assert world._tavily_client.is_closed is False

    await world.aclose()

    assert world._tavily_client.is_closed is True
    assert world._client.is_closed is True  # aigateway client closed too


async def test_injected_tavily_client_not_closed_on_aclose() -> None:
    gw = _MockAigateway((_MODEL,))
    tvly = _MockTavily()
    cfg = AigatewayConfig(default_model=_MODEL)
    async with gw.client() as client, tvly.client() as tclient:
        world = await build_aigateway_world(
            cfg, token=_TOKEN, client=client, tavily_api_key=_TAVILY_TOKEN, tavily_client=tclient
        )

        assert world._owns_tavily_client is False

        await world.aclose()

        assert tclient.is_closed is False
        assert client.is_closed is False  # injected aigateway client also untouched


# --- W12. Tavily search formats results; extract returns raw_content; failed URLs reported ---


async def test_tavily_search_formats_results_as_title_url_content_blocks() -> None:
    gw = _MockAigateway(
        (_MODEL,),
        responses={
            _MODEL: [
                _tool_calls_body([_tool_call("web_search", {"query": "q"})]),
                "done",
            ]
        },
    )
    tvly = _MockTavily(
        search_results=[
            {"title": "T1", "url": "https://u1", "content": "C1"},
            {"title": "T2", "url": "https://u2", "content": "C2"},
        ]
    )
    cfg = AigatewayConfig(default_model=_MODEL)
    async with gw.client() as client, tvly.client() as tclient:
        world = await build_aigateway_world(
            cfg, token=_TOKEN, client=client, tavily_api_key=_TAVILY_TOKEN, tavily_client=tclient
        )

        await url4_run(f"/{_MODEL}(ctx)!go", io=world.node)

    tool_result = json.loads(gw.posts_to(_MODEL)[1].content)["messages"][-1]["content"]
    assert "Title: T1\nURL: https://u1\nContent: C1" in tool_result
    assert "Title: T2\nURL: https://u2\nContent: C2" in tool_result


async def test_tavily_extract_reports_failed_urls_in_tool_result() -> None:
    gw = _MockAigateway(
        (_MODEL,),
        responses={
            _MODEL: [
                _tool_calls_body([_tool_call("web_fetch", {"url": "https://blocked"})]),
                "give up.",
            ]
        },
    )
    tvly = _MockTavily(
        extract_results=[],
        extract_failed=[{"url": "https://blocked", "error": "403 forbidden"}],
    )
    cfg = AigatewayConfig(default_model=_MODEL)
    async with gw.client() as client, tvly.client() as tclient:
        world = await build_aigateway_world(
            cfg, token=_TOKEN, client=client, tavily_api_key=_TAVILY_TOKEN, tavily_client=tclient
        )

        await url4_run(f"/{_MODEL}(ctx)!go", io=world.node)

    tool_result = json.loads(gw.posts_to(_MODEL)[1].content)["messages"][-1]["content"]
    assert "https://blocked" in tool_result
    assert "403 forbidden" in tool_result


async def test_tavily_key_never_sent_to_aigateway() -> None:
    # Credential hygiene (dec:W4): the Tavily bearer is attached only to Tavily requests
    # and never appears in any aigateway request header.
    gw = _MockAigateway(
        (_MODEL,),
        responses={
            _MODEL: [
                _tool_calls_body([_tool_call("web_search", {"query": "q"})]),
                "done",
            ]
        },
    )
    tvly = _MockTavily(search_results=[{"title": "S", "url": "https://s", "content": "c"}])
    cfg = AigatewayConfig(default_model=_MODEL)
    async with gw.client() as client, tvly.client() as tclient:
        world = await build_aigateway_world(
            cfg, token=_TOKEN, client=client, tavily_api_key=_TAVILY_TOKEN, tavily_client=tclient
        )

        await url4_run(f"/{_MODEL}(ctx)!go", io=world.node)

    for req in gw.posts_to(_MODEL):
        # The aigateway request carries the aigateway token, never the Tavily key.
        assert req.headers["authorization"] == f"Bearer {_TOKEN}"
        assert _TAVILY_TOKEN not in str(req.headers) + req.content.decode("utf-8", errors="ignore")
