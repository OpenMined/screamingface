"""Builds the aigateway-backed :class:`~url4.io.layer.IOLayer` world: a `Url4Node` whose
endpoints are declared models routed to aigateway's chat-completions API, plus an optional
Tavily-backed web-search/web-fetch tool loop. This is the world `executor.Url4Executor`
resolves and runs an expression against.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass

import httpx

from url4.core.errors import ResolutionError
from url4.io.static import StaticIOLayer
from url4.observe import current_response_sink, current_usage_sink
from url4.peer.server import Request, Url4Node
from url4.streaming.protocol import CachePolicy
from url4_cloud.runner.cache import policy_to_body_field
from url4_cloud.runner.cache_readback import CacheOutcome, read_cache_outcome, requires_revalidation
from url4_cloud.runner.config import ModelSpec, RunnerConfigError, routes_for

_COMPLETIONS_PATH = "/v1/chat/completions"

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
    """The resolved aigateway world settings a run needs — routes, timeouts, and the optional
    Tavily tool loop."""

    base_url: str = "http://127.0.0.1:9105"
    default_model: str = "claude-haiku-4-5"
    # WHY: DECLARED, never discovered — see `config.routes_for`. Empty is a config error, not a
    # signal to go ask the gateway what it serves. Each entry carries its own capabilities
    # (`web_tools`), so a route's behavior is declared beside the route.
    models: tuple[ModelSpec, ...] = ()
    # WHY: absolute-URL sources are a real url4 feature, so the default preserves the behavior a
    # `Url4Node` world has always had. Set False to hand the node a denying outbound layer.
    allow_outbound: bool = True
    timeout_s: float = 60.0
    tavily_base_url: str = "https://api.tavily.com"
    tavily_search_depth: str = "advanced"
    tavily_max_results: int = 5
    tavily_timeout_s: float = 30.0
    web_tool_max_iterations: int = 5
    # INVARIANT: the iteration count alone does NOT bound this loop's cost. Two other dimensions
    # have to be bounded or a single expression can run away:
    #
    # - a tool result is appended to `messages` and RE-SENT on every later iteration, so an
    #   uncapped `raw_content` from one `web_fetch` is paid for repeatedly and can exceed the
    #   model's context window outright (a 400 the loop turns into a permanent failure);
    # - the model chooses how many tool calls one turn contains, and they are dispatched
    #   concurrently, so an unbounded fan-out is an unbounded burst of upstream requests.
    web_tool_max_result_bytes: int = 32_768
    web_tool_max_calls_per_turn: int = 8


@dataclass
class AigatewayWorld:
    """The resolved world: the `Url4Node` plus the HTTP client(s) `aclose` must tear down."""

    node: Url4Node
    _client: httpx.AsyncClient
    _owns_client: bool
    _tavily_client: httpx.AsyncClient | None = None
    _owns_tavily_client: bool = False

    @property
    def web_tools_enabled(self) -> bool:
        """Whether this world CAN serve web tools at all — i.e. a Tavily key was configured.

        Derived, not stored: a Tavily client exists exactly when a key was configured, so a
        separate flag could only ever agree with `_tavily_client` — or drift from it.

        This is the world-level capability, NOT a promise that any given call sends tools:
        a route sends them only when its own `ModelSpec.web_tools` is true. Both must hold.
        """
        return self._tavily_client is not None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
        if self._tavily_client is not None and self._owns_tavily_client:
            await self._tavily_client.aclose()


class _ModelEndpoint:
    """The handler registered on every declared route.

    A class rather than a closure: the node holds this for the whole run either way, so the
    `__slots__` fields below are retained for the run's duration just as a closure would retain
    them; that is not what the class buys. What it avoids is pinning
    `build_aigateway_world`'s *other* frame locals along with them — e.g. `owns_client`,
    `client`, `tavily_client` — which a closure would keep alive for the whole run even though
    `__call__` never touches them, but this class holds only the fields it actually needs.
    """

    __slots__ = (
        "_cache",
        "_cfg",
        "_http_client",
        "_identity_headers",
        "_profile",
        "_routes",
        "_tavily_api_key",
        "_tavily_http",
    )

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        cfg: AigatewayConfig,
        profile: str | None,
        routes: dict[str, ModelSpec],
        tavily_http: httpx.AsyncClient | None,
        tavily_api_key: str | None,
        identity_headers: Mapping[str, str] | None = None,
        cache: CachePolicy,
    ) -> None:
        self._http_client = http_client
        self._cfg = cfg
        self._profile = profile
        self._routes = routes
        self._tavily_http = tavily_http
        self._tavily_api_key = tavily_api_key
        self._identity_headers = identity_headers
        # INVARIANT: held HERE and not on `cfg`. This object is built once per RUN, while `cfg` is
        # the world every run in the process shares — and in local mode those runs share an event
        # loop, so a policy parked on `cfg` is the previous caller's answer applied to this one.
        self._cache = cache

    async def __call__(self, request: Request) -> str:
        # The route resolves to its whole spec, so the id and the capabilities it was declared
        # with travel together — the call can never run one route's model under another's flags.
        spec = self._routes[request.path]
        return await _chat_completion_loop(
            http_client=self._http_client,
            cfg=self._cfg,
            profile=self._profile,
            model=spec.id,
            messages=_messages(request.context, request.intent),
            tavily_http=self._tavily_http,
            tavily_api_key=self._tavily_api_key,
            web_tools=spec.web_tools,
            identity_headers=self._identity_headers,
            cache=self._cache,
        )


async def build_aigateway_world(
    cfg: AigatewayConfig,
    *,
    profile: str | None = None,
    client: httpx.AsyncClient | None = None,
    tavily_api_key: str | None = None,
    tavily_client: httpx.AsyncClient | None = None,
    identity_headers: Mapping[str, str] | None = None,
    cache: CachePolicy | None = None,
) -> AigatewayWorld:
    """Build the `Url4Node` world: one endpoint per declared model, routed to aigateway.

    ``identity_headers`` is the caller's verified identity (canonical header name → value, see
    `url4_cloud.job_env.IDENTITY_HEADER_ENV`), rendered onto every chat-completions request this
    world makes. It is per-RUN rather than per-call: one run has exactly one caller, so the
    endpoint holds it for the run's duration exactly as it holds `profile`.

    ``cache`` is that run's cache policy, and it is a PARAMETER of this call rather than a field of
    `cfg` for exactly one reason: `cfg` is the world, one description of the gateway shared by
    every run in the process, and a per-run value there is a value one run reads out of another's.
    ``None`` means nothing was stated, which reaches the wire as no `cache` field at all — the
    gateway's own default — so this half never has to re-decide what silence means.

    Raises:
        RunnerConfigError: no models are declared, or `default_model` is not among them.
    """
    if not cfg.models:
        raise RunnerConfigError(
            "aigateway declares no models — the runner's endpoints are declared in url4.toml, "
            "not discovered from the gateway catalog"
        )
    declared_ids = [model.id for model in cfg.models]
    if cfg.default_model not in declared_ids:
        raise RunnerConfigError(
            f"default_model {cfg.default_model!r} is not a declared model {declared_ids!r}"
        )

    owns_client = client is None
    http_client = (
        client
        if client is not None
        else httpx.AsyncClient(base_url=cfg.base_url, timeout=cfg.timeout_s)
    )
    routes = routes_for(cfg.models)

    tavily_http, owns_tavily_client = _build_tavily_client(cfg, tavily_api_key, tavily_client)

    call_model = _ModelEndpoint(
        http_client=http_client,
        cfg=cfg,
        profile=profile,
        routes=routes,
        tavily_http=tavily_http,
        tavily_api_key=tavily_api_key,
        identity_headers=identity_headers or None,
        # `is not None`, not `or`: a policy is a pydantic model and always truthy, but spelling the
        # fallback explicitly says what it is — an unstated policy, not a stated default.
        cache=cache if cache is not None else CachePolicy(),
    )

    # WHY: `outbound=StaticIOLayer()` denies every absolute-URL fetch: an unmapped target raises
    # instead of reaching HttpIOLayer. Left None, the node lazily builds HttpIOLayer and can
    # fetch any URL — which is what a token-bearing run has always been able to do.
    node = Url4Node(
        "aigateway",
        default_processor="/" + cfg.default_model,
        outbound=None if cfg.allow_outbound else StaticIOLayer(),
    )
    for path in routes:
        node.endpoint(path)(call_model)
    return AigatewayWorld(
        node=node,
        _client=http_client,
        _owns_client=owns_client,
        _tavily_client=tavily_http,
        _owns_tavily_client=owns_tavily_client,
    )


def _provider_of(model: str) -> str:
    if "/" in model:
        return model.split("/", 1)[0]
    return "anthropic"


def _report_response(choice: _Choice, cache: CacheOutcome) -> None:
    """Report how one model round trip ended — and whether the gateway served it from its
    response cache — onto the currently-resolving node's span.

    Null-safe exactly like `_report_usage`: outside a run, or with no observer attached, the
    sink is absent and this is a no-op.

    INVARIANT: reported BESIDE `_report_usage`, for the same call, or the two disagree. A hit
    costs nothing upstream while `_report_usage` bills it as a fresh call, so a span that
    carries the tokens without the outcome states a cost that was never paid — an error in the
    direction that hides savings, and therefore one nobody reports.
    """
    sink = current_response_sink()
    if sink is None:
        return
    sink(
        finish_reason=choice.finish_reason,
        refusal=choice.refusal,
        cache_status=cache.status,
        cache_reason=cache.reason,
    )


def _report_usage(model: str, usage: dict | None) -> None:
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


@dataclass(frozen=True, slots=True)
class _Choice:
    """One chat-completions choice, reduced to what this connector consumes."""

    content: str | None
    tool_calls: list[dict] | None
    finish_reason: str | None
    refusal: str | None


def _parse_choice(data: dict) -> _Choice:
    """Pull the first choice out of a chat-completions response.

    Extraction only — whether the choice is *usable* is `_raise_if_unusable`'s call. The split
    is load-bearing: the caller reports the finish reason between the two, so a refused turn is
    still observable even though it goes on to fail (dec: OME-745).

    Raises:
        ResolutionError: the response shape is unparsable — there is nothing to report either.
    """
    try:
        choice = data["choices"][0]
        message = choice["message"]
        content = message.get("content")
        tool_calls = message.get("tool_calls")
        finish_reason = choice.get("finish_reason")
        refusal = message.get("refusal")
    except (KeyError, IndexError, TypeError) as exc:
        raise ResolutionError(
            "malformed aigateway response", code="aigateway_bad_response", permanent=True
        ) from exc
    return _Choice(
        content=content,
        tool_calls=tool_calls,
        finish_reason=finish_reason if isinstance(finish_reason, str) else None,
        refusal=refusal if isinstance(refusal, str) and refusal.strip() else None,
    )


def _raise_if_unusable(choice: _Choice) -> None:
    """Reject a choice that carries no answer, distinguishing a REFUSAL from a malformed reply.

    WHY the distinction: these used to collapse into one `aigateway_bad_response`, so a model
    that declined on safety grounds was indistinguishable from a broken payload — and downstream
    a refusal was scored as if the model had answered badly (FEATURE: OME-679).

    Raises:
        ResolutionError: ``provider_refusal`` when the provider declined, else
            ``aigateway_bad_response`` when there is neither content nor a tool call.
    """
    # INVARIANT: the refusal check precedes the emptiness check. A content_filter turn normally
    # carries null content, so testing emptiness first would classify every refusal as malformed.
    if choice.finish_reason == "content_filter" or choice.refusal is not None:
        # `permanent=True`: a refusal is deterministic, so a retry spends budget to be refused
        # again. This is the wire signal a client maps to a refusal-kind failure.
        raise ResolutionError(
            "provider refused the request", code="provider_refusal", permanent=True
        )
    if not choice.tool_calls and choice.content is None:
        raise ResolutionError(
            "malformed aigateway response", code="aigateway_bad_response", permanent=True
        )


def _build_tavily_client(
    cfg: AigatewayConfig,
    tavily_api_key: str | None,
    tavily_client: httpx.AsyncClient | None,
) -> tuple[httpx.AsyncClient | None, bool]:
    """Resolve the optional Tavily client.

    Returns:
        ``(client, owns_client)`` — ``client`` is ``None`` when no API key is configured, which
        IS the "web tools are off" signal (see `AigatewayWorld.web_tools_enabled`);
        ``owns_client`` says whether the caller must close it (``False`` when an existing client
        was passed in).
    """
    if tavily_api_key is None:
        return None, False
    owns = tavily_client is None
    client = (
        tavily_client
        if tavily_client is not None
        else httpx.AsyncClient(base_url=cfg.tavily_base_url, timeout=cfg.tavily_timeout_s)
    )
    return client, owns


async def _fetch_completion(
    http_client: httpx.AsyncClient,
    *,
    headers: dict[str, str],
    body: dict,
    cache: CachePolicy,
) -> tuple[httpx.Response, CacheOutcome]:
    """One chat-completions round trip under this run's cache policy, plus what the gateway
    reported about the cache — re-issued without the cache when the answer cannot be served.

    The re-issue is D11's honouring half (spec §3.5). A caller that stated `max-age` gets an
    answer it can trust: a hit whose age the gateway cannot establish is refused rather than
    served, since the corpus is global and never expires, so "how old is this" has no bound at
    all. It costs one extra round trip and a discarded body, and ONLY on a hit — a miss or a
    bypass was generated just now and satisfies every bound already (`requires_revalidation`).

    INVARIANT: the discarded response is read for its headers and nothing else. Its usage is
    never reported, or the turn would be billed twice — the exact error class this read-back
    exists to prevent.

    Returns:
        The response to consume, and the cache outcome of the round trip that produced IT — not
        of the one that was discarded, whose only remaining trace is that it happened.
    """
    resp = await http_client.post(
        _COMPLETIONS_PATH,
        headers=headers,
        # `policy_to_body_field` yields an EMPTY dict for a run that participates, so an ordinary
        # run's body is byte-identical to the one this connector has always sent — which is also
        # the smallest surface exposed to the gateway's closed cache grammar, where one
        # unrecognised key silently costs every hit (spec §1.0).
        json={**body, **policy_to_body_field(cache)},
    )
    _raise_for_status(resp)
    outcome = read_cache_outcome(resp.headers)
    if not requires_revalidation(cache, outcome):
        return resp, outcome
    # An explicit opt-out, built here rather than derived from `cache`: the run's own policy
    # PARTICIPATES (a bound is not a refusal), and the re-issue must state the one thing the
    # closed grammar understands — `use-cache: false` — and nothing else.
    resp = await http_client.post(
        _COMPLETIONS_PATH,
        headers=headers,
        json={**body, **policy_to_body_field(CachePolicy(participate=False))},
    )
    _raise_for_status(resp)
    return resp, read_cache_outcome(resp.headers)


async def _chat_completion_loop(
    *,
    http_client: httpx.AsyncClient,
    cfg: AigatewayConfig,
    profile: str | None,
    model: str,
    messages: list[dict],
    tavily_http: httpx.AsyncClient | None,
    tavily_api_key: str | None,
    web_tools: bool,
    identity_headers: Mapping[str, str] | None = None,
    cache: CachePolicy,
) -> str:
    """Drive one `_ModelEndpoint` call: post to aigateway, execute any requested tool calls,
    and repeat until the model answers with content instead of another tool call.

    Tools are offered only when the ROUTE opted in (`web_tools`) AND the world can serve them
    (a Tavily client exists). Both conditions are load-bearing: without the route's opt-in a
    configured key would silently change every model's request payload, and without the client
    the model could call a tool nothing can execute.

    INVARIANT: the cache policy is re-applied on EVERY round trip, not merged once before the
    loop. One turn is several independently-keyed gateway calls, and a policy that lapsed after
    the first would serve the tool-augmented continuation — the most context-specific call of the
    turn — from a shared corpus the caller had just refused.

    Raises:
        ResolutionError: the loop exceeds `cfg.web_tool_max_iterations` without a final
            answer — the model keeps calling tools instead of returning content.
    """
    offer_tools = web_tools and tavily_http is not None
    extra = {"tools": _WEB_TOOLS, "tool_choice": "auto"} if offer_tools else {}
    headers = _headers(profile, identity_headers)
    for _ in range(cfg.web_tool_max_iterations):
        body = {"model": model, "messages": messages, **extra}
        resp, outcome = await _fetch_completion(
            http_client, headers=headers, body=body, cache=cache
        )
        data = _json_or_raise(resp)
        _report_usage(model, data.get("usage"))
        choice = _parse_choice(data)
        # INVARIANT: report BEFORE classifying. A refused turn is the case a reviewer most needs
        # to audit, and raising first would lose exactly the event OME-679 exists to capture.
        _report_response(choice, outcome)
        _raise_if_unusable(choice)
        content, tool_calls = choice.content, choice.tool_calls
        if not tool_calls:
            return content or ""
        # Cap the fan-out BEFORE dispatching: the model decides how many calls a turn carries, and
        # they all run concurrently. The dropped ones still get a tool message, because the API
        # requires one reply per tool_call_id — omitting them makes the next request malformed.
        served, dropped = (
            tool_calls[: cfg.web_tool_max_calls_per_turn],
            tool_calls[cfg.web_tool_max_calls_per_turn :],
        )
        messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})
        results = await asyncio.gather(
            *(_execute_tool(tc, tavily_http, cfg, tavily_api_key) for tc in served)
        )
        for tc, result in zip(served, results, strict=True):
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": tc["function"]["name"],
                    "content": _truncate_tool_result(result, cfg.web_tool_max_result_bytes),
                }
            )
        for tc in dropped:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": tc.get("function", {}).get("name", ""),
                    "content": (
                        f"error: not executed — at most {cfg.web_tool_max_calls_per_turn} tool "
                        f"calls are served per turn; request fewer"
                    ),
                }
            )
    raise ResolutionError(
        f"web tool loop exceeded {cfg.web_tool_max_iterations} iterations",
        code="web_tool_loop_limit",
        permanent=False,
    )


_TOOL_TRUNCATION_MARKER = "\n…[truncated]"


def _truncate_tool_result(result: str, cap: int) -> str:
    """Bound one tool result to `cap` UTF-8 bytes, marking that it was cut.

    Cuts on a byte boundary (`errors="ignore"` drops a partial trailing character rather than
    raising), mirroring `_RunState.build_result`. The marker matters: a silently truncated web
    page reads to the model as a complete one, and it will answer confidently from the fragment.
    """
    encoded = result.encode("utf-8")
    if len(encoded) <= cap:
        return result
    marker = _TOOL_TRUNCATION_MARKER.encode("utf-8")
    if len(marker) >= cap:
        return marker[:cap].decode("utf-8", errors="ignore")
    kept = encoded[: cap - len(marker)]
    return kept.decode("utf-8", errors="ignore") + _TOOL_TRUNCATION_MARKER


def _tool_args(tool_call: dict) -> tuple[str, dict | None]:
    """The call's tool name plus its parsed arguments, or ``None`` args when they are unusable —
    the caller renders the one error message both failure modes produce."""
    name = tool_call.get("function", {}).get("name", "")
    raw = tool_call.get("function", {}).get("arguments")
    try:
        args = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except (TypeError, json.JSONDecodeError):
        return name, None
    return (name, args) if isinstance(args, dict) else (name, None)


async def _dispatch_tool(
    name: str,
    args: dict,
    tavily_client: httpx.AsyncClient | None,
    cfg: AigatewayConfig,
    tavily_api_key: str | None,
) -> str:
    if name not in ("web_search", "web_fetch"):
        return f"unknown tool: {name}"
    if tavily_client is None or tavily_api_key is None:
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
    name, args = _tool_args(tool_call)
    if args is None:
        return f"invalid arguments for {name}"
    try:
        return await _dispatch_tool(name, args, tavily_client, cfg, tavily_api_key)
    except Exception as exc:  # noqa: BLE001 — fed back to the model, not raised (dec:W2)
        return f"{name} failed: {exc}"


async def _tavily_search(
    client: httpx.AsyncClient,
    cfg: AigatewayConfig,
    api_key: str,
    args: dict,
) -> str:
    query = args.get("query")
    if not isinstance(query, str) or not query:
        raise ValueError("web_search requires a non-empty 'query'")
    resp = await client.post(
        "/search",
        headers=_tavily_headers(api_key),
        json={
            "query": query,
            "search_depth": cfg.tavily_search_depth,
            "max_results": cfg.tavily_max_results,
        },
    )
    resp.raise_for_status()
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
    client: httpx.AsyncClient,
    cfg: AigatewayConfig,
    api_key: str,
    args: dict,
) -> str:
    url = args.get("url")
    if not isinstance(url, str) or not url:
        raise ValueError("web_fetch requires a non-empty 'url'")
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


def _messages(context: str | None, intent: str | None) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if intent:
        messages.append({"role": "system", "content": intent})
    messages.append({"role": "user", "content": context or ""})
    return messages


def _headers(
    profile: str | None, identity_headers: Mapping[str, str] | None = None
) -> dict[str, str]:
    """The outgoing aigateway headers: the caller's identity, then the values this world owns.

    INVARIANT: the gateway-owned header is written LAST. `identity_headers` reaches here from an
    inbound request, and although Envoy guarantees a client cannot forge the identity header
    itself, nothing guarantees the mapping holds ONLY that key — so `X-Profile` is applied over it
    rather than under it, and no inbound value can displace this run's routing choice. Same
    ordering rule the aigateway provider plugins apply to their own gateway-owned headers.

    WHY no `Authorization`: aigateway runs `cloudflare_headers` when deployed and `disabled`
    locally. Neither mode reads a bearer token, and a deployed caller cannot obtain one, so the
    run carries none at all.
    """
    headers = dict(identity_headers or {})
    if profile is not None:
        headers["X-Profile"] = profile
    return headers


def _json_or_raise(resp: httpx.Response) -> dict:
    """Decode a 2xx body, naming the failure when it is not JSON at all.

    A fronting access proxy (CF Access) answers with an HTML login page under a 200, which
    `resp.json()` would surface as a bare JSONDecodeError — an unnamed `internal_error` in the
    run's terminal frame instead of something an operator can act on.
    """
    try:
        return resp.json()
    except ValueError as exc:
        raise ResolutionError(
            "aigateway returned a non-JSON response body — a proxy or access gateway in front "
            "of aigateway is intercepting the request",
            code="aigateway_bad_response",
            permanent=True,
        ) from exc


def _raise_for_status(resp: httpx.Response) -> None:
    """Turn a non-2xx (or redirected) aigateway response into a `ResolutionError`.

    A redirect is treated as an interception by a fronting proxy, not a real aigateway response.
    For a 4xx/5xx, the error `code`/`message` prefer the response's own `detail` payload when
    present; `permanent` is `False` only for 429 and 5xx, so those (and only those) are
    eligible for retry upstream.
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
