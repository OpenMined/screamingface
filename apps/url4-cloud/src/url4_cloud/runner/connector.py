"""Builds the aigateway-backed :class:`~url4.io.layer.IOLayer` world: a `Url4Node` whose
endpoints are declared models routed to aigateway's chat-completions API, plus an optional
Tavily-backed web-search/web-fetch tool loop. This is the world `executor.Url4Executor`
resolves and runs an expression against.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import httpx

# AIDEV-NOTE: `_serve` is a PRIVATE CLI module in `packages/url4` and this reaches into it
# deliberately. `make_command_handler` is in that module's own `__all__`, so the symbol is stable
# even though the module path is not — and duplicating it here would fork a subprocess-exec
# factory whose invariants (argv list never a shell string; single-pass token substitution over
# the operator's template only) must not exist in two copies. This mirrors the note in
# `config.py`: the Runner is the SECOND consumer of `_serve`, and the agreed threshold for
# promoting a shared public module is a THIRD. Promote this import then, not before.
from url4.cli._serve import ProviderSpec, make_command_handler, make_data_provider
from url4.core.errors import ResolutionError
from url4.io.static import StaticIOLayer
from url4.observe import current_usage_sink
from url4.peer.server import Request, Url4Node
from url4_cloud.runner.config import (
    CommandSpec,
    DataSpec,
    ModelSpec,
    RunnerConfigError,
    routes_for,
)

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


WEB_SEARCH_PARAM = "web_search"
"""The expression-level retrieval toggle: ``…!'answer';web_search=false``.

INTERPRETED by the runner, never copied through. The gateway has a `web_search` field of its
own and the names deliberately match — but the expression's value decides WHETHER this call
retrieves, while the gateway's field is set by `_native_web_search` only after the route's
declared mechanism has been resolved. Forwarding the raw string would send `"false"`, which is
a truthy JSON string, and switch retrieval ON where the expression asked for it off.

It OVERRIDES the route's declaration rather than replacing it: absent means "whatever the route
declares", so an expression that says nothing about retrieval behaves exactly as it did before
this existed.

Asking a route that declares NO mechanism to search is an error, not a silent no-op — the
alternative is an expression that reads as though it retrieved and an answer written from
weights alone, which is indistinguishable in the result.
"""


def _native_web_search(cfg: AigatewayConfig) -> dict[str, object]:
    """Ask the GATEWAY for provider-side retrieval — nothing provider-specific here.

    `web_search` is aigateway's provider-agnostic vocabulary: the gateway decides which
    provider can retrieve and translates the flag into that provider's own spelling. Building a
    provider's payload here instead would put OpenRouter knowledge in the runner and duplicate a
    contract the gateway already owns — the layering rule this repo states as core-defines-ports.

    `web_search_excluded_domains` is UNIONed with the deployment's own list by the gateway, so
    this can only ever tighten the guard. It is operator config, never expression-supplied: the
    motivating case is a benchmark candidate that must not retrieve the rubric it is graded
    against, and a blocklist a caller can rewrite is not a blocklist.
    """
    body: dict[str, object] = {"web_search": True}
    if cfg.web_search_excluded_domains:
        body["web_search_excluded_domains"] = list(cfg.web_search_excluded_domains)
    return body


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
    # --- native (provider-side) web search, for `native_web_search = true` routes ------------
    # INVARIANT: OPERATOR-owned, never expression-supplied. This is a leak guard — a benchmark
    # candidate must not be able to retrieve the rubric it is graded against — and a guard a
    # caller can rewrite is not a guard. The gateway UNIONs it with the deployment's own list,
    # so this can only tighten. Empty omits the field entirely rather than sending an empty
    # list, which would read as "exclude nothing" instead of "use the deployment's".
    #
    # WHY no engine/max_results here: those are the PROVIDER's own options, and aigateway owns
    # them. A runner that set them would be re-specifying one provider's envelope through a
    # flag whose whole point is that it names no provider.
    web_search_excluded_domains: tuple[str, ...] = ()


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
    ) -> None:
        self._http_client = http_client
        self._cfg = cfg
        self._profile = profile
        self._routes = routes
        self._tavily_http = tavily_http
        self._tavily_api_key = tavily_api_key
        self._identity_headers = identity_headers

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
            params=request.params,
            spec=spec,
            tavily_http=self._tavily_http,
            tavily_api_key=self._tavily_api_key,
            web_tools=spec.web_tools,
            identity_headers=self._identity_headers,
        )


def register_commands(node: Url4Node, commands: Sequence[CommandSpec]) -> None:
    """Register each declared `[commands]` route as a subprocess endpoint on ``node``.

    INVARIANT: the ENGINE owns which paths are registrable (the eval path is dispatched by the
    node itself; a path cannot be claimed twice). Restating those rules in `config.py` would let
    the two drift, so the engine's `ValueError` is translated here instead — the operator gets a
    `RunnerConfigError` naming the offending route either way.
    """
    for command in commands:
        try:
            node.endpoint(command.path)(make_command_handler(command.argv, command.timeout_s))
        except ValueError as exc:
            raise RunnerConfigError(
                f"[commands] {command.path!r} is not registrable: {exc}"
            ) from exc


def register_data(node: Url4Node, data: Sequence[DataSpec]) -> None:
    """Register each declared `[data]` route as a read-only artifact on ``node``.

    Provider construction reuses `_serve`'s tested factory rather than reimplementing
    per-request file reads and subprocess handling — those behaviours are the contract
    (`file` is live; `command` gets empty stdin), and a second copy would drift from it.

    INVARIANT: registrability is the ENGINE's rule, as in `register_commands` — the eval path is
    the node's own, and a path cannot be claimed twice. Its `ValueError` is translated so the
    operator sees a `RunnerConfigError` naming the route.
    """
    for spec in data:
        provider = make_data_provider(
            ProviderSpec(
                value=spec.value,
                file=spec.file,
                command=spec.command,
                media_type=spec.media_type,
            ),
            spec.timeout_s,
        )
        try:
            node.data(spec.path, provider, media_type=spec.media_type)
        except ValueError as exc:
            raise RunnerConfigError(f"[data] {spec.path!r} is not registrable: {exc}") from exc


def build_local_world(
    commands: Sequence[CommandSpec] = (), data: Sequence[DataSpec] = ()
) -> Url4Node:
    """A world with declared routes and nothing else — no models, no outbound fetches.

    WHY this exists: a config declaring only `[commands]` and/or `[data]` is legitimate (a Job
    that shells out or serves artifacts and never calls a model), and before those tables were
    parsed the absence of `[aigateway]` could only mean "deny everything". `StaticIOLayer` keeps
    the deny-by-default outbound posture, so the ONLY thing this world adds over
    `deny_by_default_world` is the declared routes.
    """
    node = Url4Node("local", outbound=StaticIOLayer())
    register_commands(node, commands)
    register_data(node, data)
    return node


async def build_aigateway_world(
    cfg: AigatewayConfig,
    *,
    profile: str | None = None,
    client: httpx.AsyncClient | None = None,
    tavily_api_key: str | None = None,
    tavily_client: httpx.AsyncClient | None = None,
    identity_headers: Mapping[str, str] | None = None,
    commands: Sequence[CommandSpec] = (),
    data: Sequence[DataSpec] = (),
) -> AigatewayWorld:
    """Build the `Url4Node` world: one endpoint per declared model, routed to aigateway.

    ``identity_headers`` is the caller's verified identity (canonical header name → value, see
    `url4_cloud.job_env.IDENTITY_HEADER_ENV`), rendered onto every chat-completions request this
    world makes. It is per-RUN rather than per-call: one run has exactly one caller, so the
    endpoint holds it for the run's duration exactly as it holds `profile`.

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
    # INVARIANT: commands are registered AFTER the model routes, so a path claimed by both is
    # rejected by the engine here rather than silently shadowing a model. `config` already
    # rejects that pair with a better message; this is the backstop for a world built directly.
    register_commands(node, commands)
    register_data(node, data)
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


def _report_usage(model: str, usage: dict | None, response_model: object = None) -> None:
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
        # The gateway echoes the model that actually served the call, which may be a dated
        # snapshot behind the alias we asked for. Only a string is forwarded: this comes off an
        # upstream JSON body, and a non-string here would otherwise reach the wire schema.
        response_model=response_model if isinstance(response_model, str) else None,
    )


def _parse_choice(data: dict) -> tuple[str | None, list[dict] | None]:
    """Pull ``(content, tool_calls)`` out of a chat-completions response.

    Raises:
        ResolutionError: the response shape is unparsable, or it has neither content nor a
            tool call — either way there is nothing usable to return.
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


RUNNER_OWNED_FIELDS = frozenset(
    {"model", "messages", "tools", "tool_choice", "stream", "web_search_excluded_domains"}
)
"""Request fields an EXPRESSION may never set — they belong to the runner, not the caller.

``model`` would let an expression address one route and run another, breaking the "a route path
is exactly '/' + the gateway id" invariant that `url4.toml` and
`test_declared_models_match_aigateway.py` exist to hold. ``tools``/``tool_choice`` would bypass
the per-route ``web_tools`` opt-in, which is what keeps a configured Tavily key from silently
changing every model's payload. ``stream`` would break `_parse_choice`.

``web_search_excluded_domains`` is the runner's because it is set from operator config on a
retrieving call, and the payload merge puts the runner's value last — so a caller's copy would
be accepted at parse and then silently discarded. The gateway would union a caller list safely
enough, but "accepted and ignored" is the failure shape this whole file exists to avoid.

Everything else is forwarded: the GATEWAY is the authority on which parameters exist and which
values are legal (`core/standard_parameters.py` plus each provider's rules), and it fails closed
on an unknown field. A second allowlist here would be a copy of that contract, free to drift
from it — the same reason `register_commands` translates the engine's error instead of
restating its rules.
"""


def _wants_web_search(params: Mapping[str, str], spec: ModelSpec | None) -> bool:
    """Whether THIS call retrieves — the route's declaration, overridden by the expression.

    The route declares what it CAN do; the expression decides whether to use it. Absent means
    "as declared", so an expression that never mentions retrieval keeps the behavior it had
    before this parameter existed.

    Raises:
        ResolutionError: the expression asked a route that declares no mechanism to search.
            Loud, because the silent alternative is an answer written from weights alone that
            reads exactly like a retrieved one.
    """
    declared = bool(spec and (spec.web_tools or spec.native_web_search))
    raw = params.get(WEB_SEARCH_PARAM)
    if raw is None:
        return declared
    wanted = _coerce_param(raw) is True
    if wanted and not declared:
        raise ResolutionError(
            f"{WEB_SEARCH_PARAM}=true but route {'/' + spec.id if spec else '?'} declares no web "
            "search — add `web_tools` (runner-driven) or `native_web_search` (provider-driven) "
            "to its [[aigateway.models]] entry"
        )
    return wanted


def _model_params(params: Mapping[str, str]) -> dict[str, object]:
    """The caller's `;k=v` chain as a JSON-typed request fragment.

    INVARIANT: values are COERCED, not passed through as text. url4 hands params over as
    ``Mapping[str, str]``, while the gateway's schemas are strictly typed
    (``isinstance(v, (int, float)) and not isinstance(v, bool)``), so a forwarded ``"0.2"``
    would fail closed against ``TEMPERATURE_SCHEMA`` — no better than dropping it.

    JSON is the coercion rule rather than a per-field type table, so enabling a parameter stays
    a gateway-local edit. A value that is not JSON stays the string it was, which is what a
    scalar ``stop`` or any enum-valued field needs.

    Raises:
        ResolutionError: the expression set a runner-owned field. Loud on purpose — dropping it
            silently would let the expression read as though it had pinned something it had not.
    """
    params = {k: v for k, v in params.items() if k != WEB_SEARCH_PARAM}
    owned = sorted(set(params) & RUNNER_OWNED_FIELDS)
    if owned:
        raise ResolutionError(
            f"expression may not set {', '.join(owned)} — "
            f"{'it is' if len(owned) == 1 else 'they are'} owned by the runner's declared world"
        )
    return {key: _coerce_param(value) for key, value in params.items()}


def _coerce_param(value: str) -> object:
    try:
        return json.loads(value)
    except ValueError:
        return value


async def _chat_completion_loop(
    *,
    http_client: httpx.AsyncClient,
    cfg: AigatewayConfig,
    profile: str | None,
    model: str,
    messages: list[dict],
    params: Mapping[str, str] = {},  # noqa: B006 - read-only, never mutated
    spec: ModelSpec | None = None,
    tavily_http: httpx.AsyncClient | None,
    tavily_api_key: str | None,
    web_tools: bool,
    identity_headers: Mapping[str, str] | None = None,
) -> str:
    """Drive one `_ModelEndpoint` call: post to aigateway, execute any requested tool calls,
    and repeat until the model answers with content instead of another tool call.

    Tools are offered only when the ROUTE opted in (`web_tools`) AND the world can serve them
    (a Tavily client exists). Both conditions are load-bearing: without the route's opt-in a
    configured key would silently change every model's request payload, and without the client
    the model could call a tool nothing can execute.

    Raises:
        ResolutionError: the loop exceeds `cfg.web_tool_max_iterations` without a final
            answer — the model keeps calling tools instead of returning content.
    """
    # Which mechanism serves this call. `web_tools` needs a Tavily client because the RUNNER
    # executes the search; native needs nothing extra because the PROVIDER does. Both conditions
    # stay load-bearing: without the route's opt-in a configured key would silently change every
    # model's request payload, and without the client the model could call a tool nothing can
    # execute.
    wants_search = _wants_web_search(params, spec)
    native = wants_search and bool(spec and spec.native_web_search)
    offer_tools = wants_search and web_tools and tavily_http is not None
    if native:
        # A gateway-level flag, not a tools payload: no `tool_choice` (the OpenAI selection
        # control does not govern provider-run retrieval) and no collision with function calling.
        extra: dict[str, object] = _native_web_search(cfg)
    elif offer_tools:
        extra = {"tools": _WEB_TOOLS, "tool_choice": "auto"}
    else:
        extra = {}
    # Coerced ONCE, outside the loop: the value is turn-invariant, and a tool-calling turn
    # re-posts — sampling parameters must hold on every hop, or the final answer is produced
    # under different settings from the ones the expression pinned.
    sampling = _model_params(params)
    headers = _headers(profile, identity_headers)
    for _ in range(cfg.web_tool_max_iterations):
        resp = await http_client.post(
            "/v1/chat/completions",
            headers=headers,
            # `extra` LAST: the route's declared tools are not the caller's to override.
            # `_model_params` already rejects them, so this is defense in depth.
            json={"model": model, "messages": messages, **sampling, **extra},
        )
        _raise_for_status(resp)
        data = _json_or_raise(resp)
        _report_usage(model, data.get("usage"), data.get("model"))
        content, tool_calls = _parse_choice(data)
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
