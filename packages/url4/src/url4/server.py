"""The node-side SDK — :class:`Url4Node`: registries, evaluation, and ASGI serving.

A node IS an :class:`~url4.io_layer.IOLayer`: it implements ``fetch`` (routing
relative targets to its own endpoints / eval path / data routes and delegating
absolute URIs outbound), ``fetch_ex``, and ``fetch_holdings`` (``@`` and
``@identity``, spec §5.6). In-process evaluation is therefore just
``run(expression, io=self)`` — and the ASGI shim reuses the same dispatch, so
HTTP behavior and in-process behavior can never diverge.

Dispatch contract (mirrors the engine's wire conventions):

- **Endpoint paths are intent processors.** ``GET /claude?[params&]q=(ctx)!i``
  calls the registered handler with :class:`Request` — ``context`` is *opaque,
  already-resolved data* (engine-internal dispatches wire-escape resolved
  text; re-evaluating it would mis-parse). Handlers never receive unresolved
  expressions.
- **The eval path is the protocol surface** (default ``/v1``). Its ``q=`` is a
  full url4 expression: the node reconstructs it, re-attaches non-transport
  protocol params as the ``;``-chain (so ``broadcast``/``quorum`` keep their
  spec meaning, §6.1.1/§9), and evaluates it against itself — sources resolve
  HERE (§5.6.3 pass-through), the intent dispatches to ``default_processor``.
- **Data routes** serve plain reads (`/api/rows`) for sources and collections.
- **GET is the only verb** (url4-engine doctrine N1: the expression is the
  address, so the transactional call is an idempotent GET).

Deferred by design: response envelopes, streaming delivery, requestor
authentication and consent hooks (they need the URL4-Auth-Token / Part C
transport spec); identity handlers may raise the spec error codes themselves.
"""

from __future__ import annotations

import importlib
import json
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from inspect import isawaitable

from url4.client import Url4Result
from url4.context import Context
from url4.dag import DEFAULT_PROCESSOR, DEFAULT_RUN_CONCURRENCY, ExecutionContext, run
from url4.dag.node import ProcessFn, default_process
from url4.errors import ResolutionError, Url4Error
from url4.io_layer import FetchRequest, FetchResult, IOLayer, fetch_result
from url4.nodes import Node
from url4.render import render
from url4.subrequest import (
    decode_expression_http,
    decode_subrequest_http,
    extract_expression_params,
)

# WHY: \w+ matches the grammar's identity-name production (grammar._IDENTITY_RE
# is r"@(\w+)") — one rule for what counts as a principal name.
_IDENTITY_NAME_RE = re.compile(r"\w+")

# Transport-level query params a node consumes itself rather than re-attaching
# to the expression (spec §11.6.3); `processor` is expression-bearing and its
# delegation semantics (§27.3) are not implemented yet.
_TRANSPORT_PARAMS = frozenset({"delivery", "rid", "resume", "cb", "meta", "v", "processor"})

# HTTP status by spec error code; unlisted codes fall back by exception shape.
_STATUS_BY_CODE = {
    "malformed_source": 400,
    "unbound_reference": 400,
    "endpoint_not_found": 404,
    "unknown_identity": 404,
    "identity_unavailable": 404,
    "identity_access_denied": 403,
    "consent_required": 403,
    "consent_withheld": 403,
}


@dataclass(frozen=True)
class Request:
    """One decoded intent-processor call: ``GET <path>?[params&]q=(context)!intent``.

    ``context`` is opaque resolved data (see the module contract); ``params``
    are the decoded protocol params that preceded ``q=``.
    """

    path: str
    context: str
    intent: str
    params: Mapping[str, str]


EndpointHandler = Callable[[Request], str | Awaitable[str]]
HoldingsHandler = Callable[[str | None], str | Awaitable[str]]
DataProvider = str | Callable[[], str | Awaitable[str]]


class Url4Node:
    """A url4 protocol node: endpoint/holdings/identity registries + dispatch.

    ``outbound`` is the IOLayer for absolute (``https://``, ``url4://``, …)
    sources; omitted, an httpx adapter is created lazily and owned. The node
    itself is the io layer for everything relative.
    """

    def __init__(
        self,
        name: str = "node",
        *,
        eval_path: str = "/v1",
        default_processor: str = DEFAULT_PROCESSOR,
        process: ProcessFn = default_process,
        outbound: IOLayer | None = None,
        data: Mapping[str, DataProvider] | None = None,
        concurrency: int | None = DEFAULT_RUN_CONCURRENCY,
        strict_fields: bool = False,
    ) -> None:
        self.name = name
        self._eval_path = eval_path
        self._processor = default_processor
        self._process = process
        self._outbound = outbound
        self._owned_outbound: IOLayer | None = None
        self._concurrency = concurrency
        self._strict_fields = strict_fields
        self._endpoints: dict[str, EndpointHandler] = {}
        self._data: dict[str, DataProvider] = {}
        self._self_holdings: dict[str | None, HoldingsHandler] = {}
        self._identities: dict[str, HoldingsHandler] = {}
        for path, provider in (data or {}).items():
            self.data_route(path, provider)

    # --- registration ----------------------------------------------------------

    def endpoint(self, path: str) -> Callable[[EndpointHandler], EndpointHandler]:
        """Register an intent processor at ``path`` (decorator)."""
        self._check_routable(path)

        def register(handler: EndpointHandler) -> EndpointHandler:
            self._endpoints[path] = handler
            return handler

        return register

    def data_route(self, path: str, provider: DataProvider) -> None:
        """Serve a plain data read at ``path`` — static text or a callable."""
        self._check_routable(path)
        self._data[path] = provider

    def holdings(
        self, collection: str | None = None
    ) -> Callable[[HoldingsHandler], HoldingsHandler]:
        """Register the node's own ``@`` holdings (optionally per collection)."""
        if collection in self._self_holdings:
            raise ValueError(f"holdings for collection {collection!r} already registered")

        def register(handler: HoldingsHandler) -> HoldingsHandler:
            self._self_holdings[collection] = handler
            return handler

        return register

    def identity(self, name: str) -> Callable[[HoldingsHandler], HoldingsHandler]:
        """Register a principal's ``@name`` holdings (§5.6.2).

        The handler receives the requested collection and may raise
        :class:`~url4.errors.ResolutionError` with the spec's codes
        (``identity_access_denied``, ``consent_required``, …) to gate access.
        """
        if not _IDENTITY_NAME_RE.fullmatch(name) or name in self._identities:
            raise ValueError(f"invalid or duplicate identity name {name!r}")

        def register(handler: HoldingsHandler) -> HoldingsHandler:
            self._identities[name] = handler
            return handler

        return register

    def _check_routable(self, path: str) -> None:
        if not path.startswith("/"):
            raise ValueError(f"route path {path!r} must start with '/'")
        if path == self._eval_path:
            raise ValueError(f"{path!r} is the eval path — it is dispatched by the node itself")
        if path in self._endpoints or path in self._data:
            raise ValueError(f"path {path!r} is already registered")

    # --- the IOLayer ports (a node IS an io layer) ----------------------------------

    async def fetch(self, target: str, *, relative: bool) -> str:
        if relative or target.startswith("/"):
            return await self._dispatch(target)
        return await self._outbound_io().fetch(target, relative=False)

    async def fetch_ex(self, request: FetchRequest) -> FetchResult:
        if request.relative or request.target.startswith("/"):
            return FetchResult(await self._dispatch(request.target), None)
        return await fetch_result(self._outbound_io(), request)

    async def fetch_holdings(self, identity: str | None, collection: str | None) -> str:
        if identity is None:
            handler = self._self_holdings.get(collection) or self._self_holdings.get(None)
            if handler is None:
                raise ResolutionError(
                    f"node {self.name!r} serves no self holdings for {collection!r}"
                )
            return await _text(handler(collection))
        named = self._identities.get(identity)
        if named is None:
            raise ResolutionError(
                f"unknown identity {identity!r} on node {self.name!r}",
                code="unknown_identity",
                permanent=True,
            )
        return await _text(named(collection))

    # --- dispatch -----------------------------------------------------------------

    async def _dispatch(self, target: str) -> str:
        path, sep, query = target.partition("?")
        params, q = extract_expression_params(query) if sep else ({}, None)
        if q is not None:
            if path in self._endpoints:
                return await self._call_endpoint(path, q, params)
            if path == self._eval_path:
                return await self._run_text(_reassemble(q, params))
        provider = self._data.get(target, self._data.get(path))
        if provider is not None:
            return await _text(provider() if callable(provider) else provider)
        raise ResolutionError(
            f"node {self.name!r} has no endpoint, eval path, or data route at {path!r}",
            code="endpoint_not_found",
            permanent=True,
        )

    async def _call_endpoint(self, path: str, q: str, params: Mapping[str, str]) -> str:
        context, intent = decode_subrequest_http(q)
        request = Request(path=path, context=context, intent=intent, params=params)
        return await _text(self._endpoints[path](request))

    async def _run_text(self, text: str, env: Mapping[str, object] | None = None) -> str:
        ctx = ExecutionContext(
            self,
            processor=self._processor,
            process=self._process,
            scope=Context(bindings=dict(env)) if env else None,
            strict_fields=self._strict_fields,
        )
        return await run(text, ctx=ctx, concurrency=self._concurrency)

    # --- evaluation and serving --------------------------------------------------------

    async def evaluate(
        self, expression: str | Node, *, env: Mapping[str, object] | None = None
    ) -> Url4Result:
        """Evaluate a url4 expression in-process, with this node as its world."""
        request = expression if isinstance(expression, str) else render(expression)
        text = await self._run_text(request, env)
        return Url4Result(text=text, request=request)

    def asgi(self):
        """The node as a plain ASGI application (framework-free by construction)."""

        async def app(scope: Mapping, receive, send) -> None:
            if scope["type"] == "lifespan":
                await _lifespan(receive, send)
            elif scope["type"] == "http":
                await self._handle_http(scope, send)

        return app

    def serve(self, host: str = "127.0.0.1", port: int = 4404, **uvicorn_kwargs) -> None:
        """Serve :meth:`asgi` with uvicorn (requires the ``url4[server]`` extra)."""
        try:
            uvicorn = importlib.import_module("uvicorn")
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "serving a Url4Node over HTTP requires uvicorn — install url4[server]"
            ) from exc
        uvicorn.run(self.asgi(), host=host, port=port, **uvicorn_kwargs)

    async def aclose(self) -> None:
        """Close the lazily-owned outbound adapter (injected outbound is left alone)."""
        owned = self._owned_outbound
        self._owned_outbound = None
        if owned is not None:
            await owned.aclose()  # type: ignore[attr-defined]  # always HttpIOLayer

    async def __aenter__(self) -> Url4Node:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    def _outbound_io(self) -> IOLayer:
        if self._outbound is not None:
            return self._outbound
        if self._owned_outbound is None:
            from url4.io_http import HttpIOLayer  # composition root: lazy transport import

            self._owned_outbound = HttpIOLayer()
        return self._owned_outbound

    async def _handle_http(self, scope: Mapping, send) -> None:
        if scope["method"] != "GET":
            # Doctrine N1: the url4 expression is the address; the
            # transactional call is an idempotent, cacheable GET.
            await _send_error(send, 405, "method_not_allowed", "url4 nodes speak GET")
            return
        query = scope.get("query_string", b"").decode("latin-1")
        target = scope["path"] + (f"?{query}" if query else "")
        try:
            body = await self.fetch(target, relative=True)
        except Url4Error as exc:
            await _send_error(send, _status_for(exc), exc.code, str(exc))
            return
        await _send(send, 200, "text/plain; charset=utf-8", body.encode())


# --- module helpers ------------------------------------------------------------------


def _reassemble(q: str, params: Mapping[str, str]) -> str:
    """Rebuild the eval-path expression, re-attaching non-transport params.

    The dual-convention decode lives with the wire codec
    (:func:`url4.subrequest.decode_expression_http` — one owner, spec §3.4).
    ``broadcast`` and friends keep their §9 semantics by riding the trailing
    ``;`` chain the envelope decode reads (a flag param decodes to value "").
    """
    text = decode_expression_http(q)
    for key, value in params.items():
        if key not in _TRANSPORT_PARAMS:
            text += f";{key}" if value == "" else f";{key}={value}"
    return text


async def _text(result: str | Awaitable[str]) -> str:
    return await result if isawaitable(result) else result


def _status_for(exc: Url4Error) -> int:
    status = _STATUS_BY_CODE.get(exc.code)
    if status is not None:
        return status
    if isinstance(exc, ResolutionError) and not exc.permanent:
        return 502  # transient upstream/source failure
    return 500


async def _lifespan(receive, send) -> None:
    while True:
        message = await receive()
        if message["type"] == "lifespan.startup":
            await send({"type": "lifespan.startup.complete"})
        elif message["type"] == "lifespan.shutdown":
            await send({"type": "lifespan.shutdown.complete"})
            return


async def _send(send, status: int, content_type: str, body: bytes) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", content_type.encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})


async def _send_error(send, status: int, code: str, message: str) -> None:
    payload = json.dumps({"error": {"code": code, "message": message}})
    await _send(send, status, "application/json", payload.encode())


__all__ = ["DataProvider", "EndpointHandler", "HoldingsHandler", "Request", "Url4Node"]
