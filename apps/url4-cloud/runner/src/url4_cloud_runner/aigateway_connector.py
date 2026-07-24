"""The aigateway connector — a :class:`~url4.peer.server.Url4Node` world that turns url4
processor selection into real ``POST /v1/chat/completions`` calls against aigateway
(D2, `docs/plans/aigateway-connector/plan.md` §5.2).

The **2nd** module in ``url4-cloud`` allowed to import ``url4`` (contract C6 widens to a
2-file allowlist: :mod:`url4_cloud_runner.url4_executor` + this module).

:func:`build_aigateway_world` mirrors aigateway's model catalog (``GET /v1/models``, or a
static override for tests/offline) as one ``Url4Node`` endpoint per model — ``/<provider>/
<model>``, plus a bare-name alias ``/<model>`` when that name is unique across the catalog.
Every route shares one handler: it builds a chat-completion request from the caller's
(context, intent), posts it to aigateway, reports real token usage on the current node's
span via :func:`url4.observe.current_usage_sink`, and returns the completion text. aigateway
HTTP errors are mapped to :class:`~url4.core.errors.ResolutionError` with the aigateway
error code (or a synthesized ``aigateway_http_<status>``) and a permanence flag derived from
the status (429/5xx are transient; everything else is permanent) — see plan §5.2.

Deny-by-default is preserved: only the catalog's model routes are registered, no holdings,
no data routes.

**Web tools (spec 2026-07-23).** When a Tavily API key is passed to
:func:`build_aigateway_world`, ``call_model`` declares ``web_search``/``web_fetch`` to the
model and runs a **bounded agentic tool-calling loop** (dec:W1): the model's ``tool_calls``
are executed against Tavily's ``/search`` and ``/extract`` (parallel via ``asyncio.gather``),
their results are appended as ``role:"tool"`` messages, and the model is re-called until a
final answer or :attr:`AigatewayConfig.web_tool_max_iterations` (then
``ResolutionError(code="web_tool_loop_limit")``). Tavily failures are fed back to the model
as tool-result text (dec:W2), not raised. With no key, ``web_tools_enabled`` is ``False`` and
the request body is byte-identical to today (deny-by-default, dec:W5).
"""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from dataclasses import dataclass

import httpx
from url4.core.errors import ResolutionError
from url4.observe import current_usage_sink
from url4.peer.server import Request, Url4Node

# Web tools declared to the model (dec:W6) when a Tavily key is present at world-build.
# OpenAI function-calling shape — the exact format aigateway forwards and LiteLLM translates
# per provider. `web_search` -> Tavily `/search`; `web_fetch` -> Tavily `/extract`.
_WEB_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web for current or real-time information. Use when the answer "
                "needs up-to-date data not in your training."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "The search query."}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch and extract the main content of a web page from a known URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The absolute URL to fetch."}
                },
                "required": ["url"],
            },
        },
    },
]


@dataclass(frozen=True)
class AigatewayConfig:
    """World-build configuration (plan §5.2)."""

    base_url: str = "http://127.0.0.1:9105"
    # MUST be in the catalog. WHY unprefixed: aigateway's own model-id convention leaves
    # Anthropic entries bare (`claude-haiku-4-5`) — only non-Anthropic providers are
    # `<provider>/`-prefixed (`openrouter/...`, `codex/...`, ...). Observed live on a real
    # aigateway catalog; every unit test here injects its own self-consistent mock catalog, so
    # a wrong prefix here was invisible until a real Runner boot with a forwarded credential.
    default_model: str = "claude-haiku-4-5"
    models: tuple[str, ...] | None = None  # static override; skips GET /v1/models
    timeout_s: float = 60.0
    # --- web tools (Tavily) — spec 2026-07-23. Non-secret tuning only; the Tavily API key is
    # passed to build_aigateway_world (a secret, like `token`), never stored on the config.
    tavily_base_url: str = "https://api.tavily.com"
    tavily_search_depth: str = "advanced"  # advanced|basic|fast|ultra-fast (Tavily Search docs)
    tavily_max_results: int = 5
    tavily_timeout_s: float = 30.0
    web_tool_max_iterations: int = 5  # dec:W3 — bounded agentic loop cap


@dataclass
class AigatewayWorld:
    """A built world: the ``Url4Node`` to use as an ``Executor``'s ``io``, plus explicit,
    typed client teardown — kept separate from ``Url4Node`` itself so the engine type stays
    free of any httpx coupling (design review F1).

    When web tools are enabled (a Tavily key was given at build), a second owned-or-injected
    ``httpx.AsyncClient`` for Tavily is held here and closed alongside the aigateway client.
    """

    node: Url4Node
    _client: httpx.AsyncClient
    _owns_client: bool  # True only when build_aigateway_world created the client itself
    _tavily_client: httpx.AsyncClient | None = None  # None ⇔ web tools disabled (dec:W5)
    _owns_tavily_client: bool = False
    web_tools_enabled: bool = False

    async def aclose(self) -> None:
        """Close the clients this world created; injected clients are left for their owner.
        Teardown failures are not raised (mirrors ``Url4Executor._aclose_world``'s discipline —
        this may run from a finally already unwinding the run's real exception)."""
        if self._owns_client:
            await self._client.aclose()
        if self._tavily_client is not None and self._owns_tavily_client:
            await self._tavily_client.aclose()


async def build_aigateway_world(
    cfg: AigatewayConfig,
    *,
    token: str,
    profile: str | None = None,
    client: httpx.AsyncClient | None = None,
    tavily_api_key: str | None = None,
    tavily_client: httpx.AsyncClient | None = None,
) -> AigatewayWorld:
    """Build a ``Url4Node`` world with one route per aigateway model (plan §5.2).

    ``client`` is injectable (tests, or a caller that wants to control pooling/lifecycle);
    when omitted, one ``httpx.AsyncClient`` is created for this world and owned by the
    returned :class:`AigatewayWorld` — call ``await world.aclose()`` on teardown (Batch 3/4
    wires this into the run's teardown, mirroring ``HttpIOLayer``'s ``aclose``). An injected
    client is never closed by ``aclose()`` — its owner remains responsible for it.

    Web tools (spec 2026-07-23): when ``tavily_api_key`` is given, the connector declares
    ``web_search``/``web_fetch`` to the model and runs a bounded tool-calling loop (dec:W1)
    executing them against Tavily's ``/search`` and ``/extract`` via a second owned-or-injected
    ``httpx.AsyncClient``. Absent -> ``world.web_tools_enabled`` is ``False`` and the request
    body is byte-identical to today (deny-by-default, dec:W5). ``tavily_client`` is injectable
    for headless tests, with the same ownership rule as ``client``.

    Raises ``ValueError`` if ``cfg.default_model`` is not present in the resolved catalog.
    """
    owns_client = client is None
    http_client = (
        client
        if client is not None
        else httpx.AsyncClient(base_url=cfg.base_url, timeout=cfg.timeout_s)
    )
    catalog = (
        cfg.models if cfg.models is not None else await _list_models(http_client, token, profile)
    )
    if cfg.default_model not in catalog:
        if owns_client:
            await http_client.aclose()
        raise ValueError(
            f"default_model {cfg.default_model!r} is not in the aigateway catalog {list(catalog)!r}"
        )

    routes = _routes_for_catalog(catalog)

    # Web tools: built AFTER the catalog/default-model validation so the ValueError path
    # never has a Tavily client to close (its cleanup stays aigateway-client only).
    tavily_http, owns_tavily_client, web_tools_enabled = _build_tavily_client(
        cfg, tavily_api_key, tavily_client
    )

    async def call_model(request: Request) -> str:
        return await _chat_completion_loop(
            http_client=http_client,
            cfg=cfg,
            token=token,
            profile=profile,
            model=routes[request.path],
            messages=_messages(request.context, request.intent),
            web_tools_enabled=web_tools_enabled,
            tavily_http=tavily_http,
            tavily_api_key=tavily_api_key,
        )

    node = Url4Node("aigateway", default_processor="/" + cfg.default_model)
    for path in routes:
        node.endpoint(path)(call_model)
    return AigatewayWorld(
        node=node,
        _client=http_client,
        _owns_client=owns_client,
        _tavily_client=tavily_http,
        _owns_tavily_client=owns_tavily_client,
        web_tools_enabled=web_tools_enabled,
    )


def _routes_for_catalog(catalog: tuple[str, ...]) -> dict[str, str]:
    """The full ``/<provider>/<model>`` route per catalog entry, plus a bare-name
    ``/<model>`` alias when that name is unique across the catalog (plan §5.2)."""
    routes: dict[str, str] = {"/" + m: m for m in catalog}
    name_counts = Counter(m.split("/", 1)[-1] for m in catalog)
    for m in catalog:
        name = m.split("/", 1)[-1]
        alias = "/" + name
        if name_counts[name] == 1 and alias not in routes:
            routes[alias] = m
    return routes


def _provider_of(model: str) -> str:
    """The aigateway model id's provider (plan §5.2 catalog convention, see
    ``AigatewayConfig.default_model``): non-Anthropic entries are ``<provider>/<model>``;
    Anthropic entries are bare (no ``/``), so a model with no slash is Anthropic's."""
    if "/" in model:
        return model.split("/", 1)[0]
    return "anthropic"


def _report_usage(model: str, usage: dict | None) -> None:
    """Report token usage on the current node's span (F5: only when aigateway sent one)."""
    if usage is None:
        return
    sink = current_usage_sink()
    if sink is None:
        return
    sink(
        provider=_provider_of(model),
        model=model,
        input_tokens=usage.get("prompt_tokens", 0),
        output_tokens=usage.get("completion_tokens", 0),
    )


def _parse_choice(data: dict) -> tuple[str | None, list[dict] | None]:
    """Return ``(content, tool_calls)`` from ``choices[0].message``.

    Tolerates ``content is None`` when ``tool_calls`` is present (a valid tool-call turn) —
    unlike :func:`_extract_content`, which is the final-answer path and raises on a missing
    content. A shape with neither content nor tool_calls is ``aigateway_bad_response``.
    """
    try:
        message = data["choices"][0]["message"]
        content = message.get("content")
        tool_calls = message.get("tool_calls")
    except (KeyError, IndexError, TypeError) as exc:
        raise ResolutionError(
            "malformed aigateway response", code="aigateway_bad_response", permanent=True
        ) from exc
    if not tool_calls and content is None:
        raise ResolutionError(
            "malformed aigateway response", code="aigateway_bad_response", permanent=True
        )
    return content, tool_calls


def _build_tavily_client(
    cfg: AigatewayConfig,
    tavily_api_key: str | None,
    tavily_client: httpx.AsyncClient | None,
) -> tuple[httpx.AsyncClient | None, bool, bool]:
    """Build the Tavily client when web tools are enabled (dec:W5).

    Returns ``(tavily_http, owns_tavily_client, web_tools_enabled)``. No key ->
    ``(None, False, False)`` (deny-by-default: the request body stays ``{"model","messages"}``).
    An injected client is owned by its caller (``owns_tavily_client=False``).
    """
    if tavily_api_key is None:
        return None, False, False
    owns = tavily_client is None
    client = (
        tavily_client
        if tavily_client is not None
        else httpx.AsyncClient(base_url=cfg.tavily_base_url, timeout=cfg.tavily_timeout_s)
    )
    return client, owns, True


async def _chat_completion_loop(
    *,
    http_client: httpx.AsyncClient,
    cfg: AigatewayConfig,
    token: str,
    profile: str | None,
    model: str,
    messages: list[dict],
    web_tools_enabled: bool,
    tavily_http: httpx.AsyncClient | None,
    tavily_api_key: str | None,
) -> str:
    """The bounded agentic tool-calling loop (dec:W1/W3).

    Posts chat completions to aigateway; on a tool-call turn, executes the tool calls against
    Tavily (parallel via ``asyncio.gather``), appends the results as ``role:"tool"`` messages,
    and re-calls until a final answer or ``cfg.web_tool_max_iterations`` (then
    ``ResolutionError(code="web_tool_loop_limit")``). aigateway HTTP errors raise
    (``_raise_for_status``); Tavily/tool errors are fed back as tool-result text (dec:W2).
    """
    # dec:W6: tools declared only when the Tavily key is present, so the no-key request body
    # is exactly {"model", "messages"} (deny-by-default; existing tests stay green).
    extra = {"tools": _WEB_TOOLS, "tool_choice": "auto"} if web_tools_enabled else {}
    for _ in range(cfg.web_tool_max_iterations):  # dec:W3 — bounded agentic loop
        resp = await http_client.post(
            "/v1/chat/completions",
            headers=_headers(token, profile),
            json={"model": model, "messages": messages, **extra},
        )
        _raise_for_status(resp)  # aigateway HTTP error -> ResolutionError (hard fail)
        data = resp.json()
        _report_usage(model, data.get("usage"))  # per round-trip -> folds into same span
        content, tool_calls = _parse_choice(data)
        if not tool_calls:
            # Final answer. _parse_choice guarantees content is not None when there are no
            # tool_calls (a None content WITH no tool_calls is aigateway_bad_response).
            return content or ""
        # Thread the assistant tool-call turn, then execute + append each tool result.
        messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})
        results = await asyncio.gather(
            *(_execute_tool(tc, tavily_http, cfg, tavily_api_key) for tc in tool_calls)
        )
        for tc, result in zip(tool_calls, results, strict=True):
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": tc["function"]["name"],
                    "content": result,
                }
            )
    raise ResolutionError(
        f"web tool loop exceeded {cfg.web_tool_max_iterations} iterations",
        code="web_tool_loop_limit",
        permanent=False,
    )


def _tool_args(tool_call: dict) -> tuple[str, dict | None, str | None]:
    """Parse a tool_call's name + arguments. Returns ``(name, args, error)``.

    On a parse failure or a non-dict argument, ``args`` is ``None`` and ``error`` is a
    tool-result string fed back to the model (dec:W2 — never raised).
    """
    name = tool_call.get("function", {}).get("name", "")
    raw = tool_call.get("function", {}).get("arguments")
    try:
        args = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except (TypeError, json.JSONDecodeError):
        return name, None, f"invalid arguments for {name}"
    if not isinstance(args, dict):
        return name, None, f"invalid arguments for {name}"
    return name, args, None


async def _dispatch_tool(
    name: str,
    args: dict,
    tavily_client: httpx.AsyncClient | None,
    cfg: AigatewayConfig,
    tavily_api_key: str | None,
) -> str:
    """Dispatch a parsed tool call to the matching Tavily endpoint (dec:W1)."""
    if name not in ("web_search", "web_fetch"):
        return f"unknown tool: {name}"
    if (
        tavily_client is None or tavily_api_key is None
    ):  # defensive — web_tools_enabled gates this upstream
        raise RuntimeError(f"{name} requested but Tavily is not configured")
    if name == "web_search":
        return await _tavily_search(tavily_client, cfg, tavily_api_key, args)
    return await _tavily_extract(tavily_client, cfg, tavily_api_key, args)


async def _execute_tool(
    tool_call: dict,
    tavily_client: httpx.AsyncClient | None,
    cfg: AigatewayConfig,
    tavily_api_key: str | None,
) -> str:
    """Dispatch one model tool_call against Tavily, returning tool-result text.

    Failures are **fed back to the model as the tool-result text**, never raised (dec:W2) — a
    search-backend blip lets the model recover/retry/abandon rather than failing the run.
    Unknown tool names and invalid arguments are likewise fed back, not raised.
    """
    name, args, arg_err = _tool_args(tool_call)
    if arg_err is not None or args is None:
        # _tool_args returns args=None only alongside an error; the `or` covers both.
        return arg_err if arg_err is not None else f"invalid arguments for {name}"
    try:
        return await _dispatch_tool(name, args, tavily_client, cfg, tavily_api_key)
    except Exception as exc:  # noqa: BLE001 — fed back to the model, not raised (dec:W2)
        return f"{name} failed: {exc}"


async def _tavily_search(
    client: httpx.AsyncClient | None,
    cfg: AigatewayConfig,
    api_key: str | None,
    args: dict,
) -> str:
    """Tavily ``POST /search`` -> formatted ``Title/URL/Content`` blocks (dec:W1)."""
    query = args.get("query")
    if not isinstance(query, str) or not query:
        raise ValueError("web_search requires a non-empty 'query'")
    assert client is not None and api_key is not None  # _dispatch_tool guarantees this
    resp = await client.post(
        "/search",
        headers=_tavily_headers(api_key),
        json={
            "query": query,
            "search_depth": cfg.tavily_search_depth,
            "max_results": cfg.tavily_max_results,
        },
    )
    resp.raise_for_status()  # dec:W2: callers catch + feed back; never map to ResolutionError
    data = resp.json()
    results = data.get("results") or []
    if not results:
        return "no results"
    return "\n\n".join(
        f"Title: {r.get('title', '')}\nURL: {r.get('url', '')}\nContent: {r.get('content', '')}"
        for r in results
        if isinstance(r, dict)
    )


async def _tavily_extract(
    client: httpx.AsyncClient | None,
    cfg: AigatewayConfig,
    api_key: str | None,
    args: dict,
) -> str:
    """Tavily ``POST /extract`` -> ``raw_content`` for the URL (dec:W1).

    Honors ``failed_results`` (a URL Tavily could not process) by reporting it back to the
    model as the tool result, so the model can abandon that source.
    """
    url = args.get("url")
    if not isinstance(url, str) or not url:
        raise ValueError("web_fetch requires a non-empty 'url'")
    assert client is not None and api_key is not None  # _dispatch_tool guarantees this
    resp = await client.post(
        "/extract",
        headers=_tavily_headers(api_key),
        json={"urls": url, "format": "markdown", "extract_depth": "advanced"},
    )
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results") or []
    if results and isinstance(results[0], dict) and results[0].get("raw_content"):
        return str(results[0]["raw_content"])
    failed = data.get("failed_results") or []
    if failed and isinstance(failed[0], dict):
        failed_url = failed[0].get("url", url)
        failed_err = failed[0].get("error", "unknown")
        return f"{failed_url} could not be extracted: {failed_err}"
    return "no content extracted"


def _tavily_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


async def _list_models(
    client: httpx.AsyncClient, token: str, profile: str | None
) -> tuple[str, ...]:
    resp = await client.get("/v1/models", headers=_headers(token, profile))
    _raise_for_status(resp)
    try:
        data = resp.json()
    except ValueError as exc:
        # WHY: a transparent proxy can answer 200 with an HTML interstitial, which
        # `_raise_for_status` legitimately lets through — decode failures must still name the
        # cause rather than escaping as a raw JSONDecodeError.
        raise ResolutionError(
            "aigateway returned a non-JSON catalog response",
            code="aigateway_bad_response",
            permanent=True,
        ) from exc
    try:
        return tuple(entry["id"] for entry in data.get("data", []))
    except (KeyError, TypeError) as exc:
        raise ResolutionError(
            "malformed aigateway response", code="aigateway_bad_response", permanent=True
        ) from exc


def _messages(context: str | None, intent: str | None) -> list[dict[str, str]]:
    """The default chat-completion prompt template (plan §5.2/O1): ``system=intent`` when
    given, ``user=context`` (empty string when there is none)."""
    messages: list[dict[str, str]] = []
    if intent:
        messages.append({"role": "system", "content": intent})
    messages.append({"role": "user", "content": context or ""})
    return messages


def _headers(token: str, profile: str | None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if profile is not None:
        headers["X-Profile"] = profile
    return headers


def _raise_for_status(resp: httpx.Response) -> None:
    """Map an aigateway HTTP error to :class:`ResolutionError` (plan §5.2).

    ``code`` comes from the aigateway ``{detail: {code, message}}`` envelope when present,
    else a synthesized ``aigateway_http_<status>``; ``permanent`` is False for 429 and 5xx
    (transient — retryable) and True otherwise.

    INVARIANT: a 3xx is an error here. aigateway never redirects, so one means something is
    sitting IN FRONT of it (an access gateway, auth proxy, or mesh) answering with a login
    redirect instead. httpx does not follow redirects on this client, so without this branch the
    proxy's HTML body would reach ``resp.json()`` and escape as a bare ``JSONDecodeError`` —
    observed live against a Cloudflare-Access-fronted aigateway.
    """
    if 300 <= resp.status_code < 400:
        raise ResolutionError(
            f"aigateway returned an unexpected redirect (status {resp.status_code}) — a proxy "
            "or access gateway in front of aigateway is intercepting the request",
            code="aigateway_bad_response",
            permanent=True,
        )
    if resp.status_code < 400:
        return
    code = f"aigateway_http_{resp.status_code}"
    message = f"aigateway request failed with status {resp.status_code}"
    try:
        payload = resp.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, dict):
            code = detail.get("code", code)
            message = detail.get("message", message)
    permanent = not (resp.status_code == 429 or 500 <= resp.status_code < 600)
    raise ResolutionError(message, code=code, permanent=permanent)


__all__ = ["AigatewayConfig", "AigatewayWorld", "build_aigateway_world"]
