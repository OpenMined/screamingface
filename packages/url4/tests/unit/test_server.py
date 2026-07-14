"""Node SDK tests — Url4Node registries, dispatch, holdings, and the ASGI shim.

STORY: as a data owner I stand up a url4 node with decorator-registered intent
processors and holdings, evaluate expressions in-process, and serve the same
dispatch over HTTP GET (url4-engine doctrine N1: the expression is the address,
GET is the transactional verb).

INVARIANT: a Url4Node IS an IOLayer — in-process evaluation, engine-internal
sub-request dispatch, and the ASGI shim all flow through the same fetch().
"""

from __future__ import annotations

import json

import httpx
import pytest

from url4 import StaticIOLayer
from url4.builders import src
from url4.client import Client
from url4.errors import ResolutionError, Url4Error
from url4.io_http import HttpIOLayer
from url4.server import Request, Url4Node

pytestmark = pytest.mark.asyncio


@pytest.fixture()
def wire() -> list[Request]:
    return []


@pytest.fixture()
def node(wire) -> Url4Node:
    n = Url4Node(
        name="testnode",
        outbound=StaticIOLayer(fetch_map={"https://x": "ARTICLE"}),
    )

    @n.endpoint("/claude")
    async def claude(request: Request) -> str:
        wire.append(request)
        return f"CLAUDE({request.intent})"

    @n.holdings()
    def own(collection: str | None) -> str:
        return f"SELF[{collection}]"

    @n.identity("emily")
    def emily(collection: str | None) -> str:
        if collection == "secret":
            raise ResolutionError(
                "emily denies access", code="identity_access_denied", permanent=True
            )
        return f"EMILY[{collection}]"

    n.data_route("/api/rows", '["alpha", "beta"]')
    return n


# --- in-process evaluation (the node as its own execution engine) ----------------------


async def test_evaluate_resolves_outbound_sources(node):
    res = await node.evaluate("(a=https://x)!'Summarize $a'")
    assert "ARTICLE" in res.text
    assert res.request == "(a=https://x)!'Summarize $a'"


async def test_evaluate_env_seeds_scope(node):
    res = await node.evaluate("()!'Hello $who'", env={"who": "world"})
    assert "world" in res.text


async def test_self_holdings_and_identity_resolution(node):
    assert "SELF[None]" in (await node.evaluate("(@)!'science'")).text
    assert "EMILY[notes]" in (await node.evaluate("(@emily/notes)!'thoughts'")).text


async def test_unknown_identity_fails_permanently(node):
    with pytest.raises(Url4Error) as err:
        await node.evaluate("(@bob)!'x'")
    assert err.value.code == "unknown_identity"
    assert err.value.permanent is True


async def test_identity_handler_can_deny_access(node):
    with pytest.raises(Url4Error) as err:
        await node.evaluate("(@emily/secret)!'x'")
    assert err.value.code == "identity_access_denied"


async def test_endpoint_dispatch_from_engine_internals(node, wire):
    # A relative expression source dispatches to the registered endpoint with
    # the wire-decoded (context, intent) pair — context is opaque data.
    res = await node.evaluate("(/claude(https://x)!'Go')")
    assert res.text.startswith("CLAUDE(")
    assert wire[0].path == "/claude"
    assert wire[0].context == "https://x"
    assert wire[0].intent == "Go"


async def test_default_processor_receives_local_intents(node, wire):
    # A flat fan-out+reduce dispatches its reducer to the default processor.
    await node.evaluate("(/claude(https://x)!'A', /claude(https://x)!'B')!'Merge'")
    assert any("Merge" in request.intent for request in wire)


async def test_node_as_client_io(node):
    async with Client(node) as client:
        res = await client.query(src("https://x", name="a"), intent="Summarize $a")
    assert "ARTICLE" in res.text


# --- the eval path (protocol surface) -----------------------------------------------------


async def test_eval_path_evaluates_full_expressions(node):
    body = await node.fetch("/v1?q=(a=https://x)!'Summarize $a'", relative=True)
    assert "ARTICLE" in body


async def test_eval_path_reattaches_protocol_params(node):
    # ;broadcast has spec-equivalent standing as a protocol param (§6.1.1)
    body = await node.fetch("/v1?broadcast&q=('a', 'b')!'x'", relative=True)
    assert isinstance(json.loads(body), list)


async def test_unknown_path_fails(node):
    with pytest.raises(Url4Error) as err:
        await node.fetch("/nope?q=()!'x'", relative=True)
    assert err.value.code == "endpoint_not_found"


async def test_data_routes_serve_reads(node):
    assert await node.fetch("/api/rows", relative=True) == '["alpha", "beta"]'
    # …which makes them iterable collections
    res = await node.evaluate("/api/rows*()!'Echo $item'")
    assert json.loads(res.text) == ["Echo alpha", "Echo beta"]


# --- ASGI shim ------------------------------------------------------------------------------


def _http(node: Url4Node) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=node.asgi())
    return httpx.AsyncClient(transport=transport, base_url="http://testnode")


async def test_asgi_get_evaluates(node):
    async with _http(node) as http:
        response = await http.get("/v1", params={"q": "(a=https://x)!'Summarize $a'"})
    assert response.status_code == 200
    assert "ARTICLE" in response.text


async def test_asgi_full_client_loop(node, wire):
    # Client → url4://testnode/v1 → HTTP GET (ASGI) → node evaluates → the
    # intent dispatches to the /claude processor endpoint → result flows back.
    async with _http(node) as http:
        client = Client(HttpIOLayer(client=http), node="url4://testnode/v1")
        res = await client.query(src("https://x", name="a"), intent="Summarize $a")
    assert "ARTICLE" in res.text or res.text.startswith("CLAUDE(")
    assert res.request.startswith("(url4://testnode/v1")


@pytest.mark.parametrize(
    ("path", "params", "status", "code"),
    [
        ("/v1", {"q": "(a::)!'x'"}, 400, "malformed_source"),
        ("/nope", {"q": "()!'x'"}, 404, "endpoint_not_found"),
        ("/v1", {"q": "(@bob)!'x'"}, 404, "unknown_identity"),
        ("/v1", {"q": "(@emily/secret)!'x'"}, 403, "identity_access_denied"),
    ],
)
async def test_asgi_error_mapping(node, path, params, status, code):
    async with _http(node) as http:
        response = await http.get(path, params=params)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code


async def test_asgi_get_only(node):
    async with _http(node) as http:
        response = await http.post("/v1", content=b"q=()!'x'")
    assert response.status_code == 405


async def test_asgi_serves_data_routes(node):
    async with _http(node) as http:
        response = await http.get("/api/rows")
    assert response.status_code == 200
    assert response.json() == ["alpha", "beta"]


# --- registration validation -----------------------------------------------------------------


async def test_registration_validation(node):
    with pytest.raises(ValueError):
        node.endpoint("no-slash")
    with pytest.raises(ValueError):
        node.endpoint("/v1")  # the eval path is reserved
    with pytest.raises(ValueError):
        node.endpoint("/claude")  # duplicate


async def test_serve_requires_uvicorn(node):
    with pytest.raises(RuntimeError, match=r"url4\[server\]"):
        node.serve()


async def test_constructor_data_param():
    n = Url4Node("d", data={"/api/x": "payload"})
    assert await n.fetch("/api/x", relative=True) == "payload"


async def test_dual_wire_conventions_are_codec_owned():
    # WHY: spec §3.4 — a node MUST accept url4's raw-structural escaping AND a
    # standard client's full percent-encoding; the codec module owns both.
    from url4.subrequest import decode_expression_http, decode_subrequest_http

    raw = "(a=https://x)!'go'"
    encoded = "%28a%3Dhttps%3A%2F%2Fx%29%21%27go%27"
    assert decode_subrequest_http(raw) == ("a=https://x", "'go'")
    assert decode_subrequest_http(encoded) == ("a=https://x", "'go'")
    assert decode_expression_http(raw) == raw
    assert decode_expression_http(encoded) == raw


# --- holdings / identity registration errors ---------------------------------------------


async def test_holdings_duplicate_registration_raises():
    n = Url4Node("dup")

    @n.holdings(collection="notes")
    def notes(collection: str | None) -> str:
        return "x"

    with pytest.raises(ValueError, match="already registered"):

        @n.holdings(collection="notes")
        def notes2(collection: str | None) -> str:
            return "y"


async def test_identity_invalid_name_raises():
    n = Url4Node("badid")

    with pytest.raises(ValueError, match="invalid or duplicate identity name"):

        @n.identity("bad-name")
        def handler(collection: str | None) -> str:
            return "x"


async def test_identity_duplicate_registration_raises():
    n = Url4Node("dupid")

    @n.identity("emily")
    def emily(collection: str | None) -> str:
        return "x"

    with pytest.raises(ValueError, match="invalid or duplicate identity name"):

        @n.identity("emily")
        def emily2(collection: str | None) -> str:
            return "y"


# --- the IOLayer ports, directly -----------------------------------------------------------


async def test_fetch_absolute_delegates_to_outbound(node):
    # relative=False with an absolute target skips node dispatch entirely and
    # delegates to the injected outbound io layer.
    assert await node.fetch("https://x", relative=False) == "ARTICLE"


async def test_fetch_holdings_self_with_no_handler_registered_raises():
    n = Url4Node("noholdings")
    with pytest.raises(ResolutionError, match="serves no self holdings"):
        await n.fetch_holdings(None, "notes")


# --- ASGI lifespan -------------------------------------------------------------------------


async def test_asgi_lifespan_startup_and_shutdown(node):
    app = node.asgi()
    sent = []
    messages = iter([{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}])

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    await app({"type": "lifespan"}, receive, send)

    assert sent == [
        {"type": "lifespan.startup.complete"},
        {"type": "lifespan.shutdown.complete"},
    ]


async def test_lifespan_helper_directly_sends_complete_messages():
    from url4.server import _lifespan

    sent = []
    messages = iter([{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}])

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    await _lifespan(receive, send)

    assert sent == [
        {"type": "lifespan.startup.complete"},
        {"type": "lifespan.shutdown.complete"},
    ]


# --- lazy-owned outbound lifecycle ----------------------------------------------------------


async def test_outbound_io_creates_and_caches_http_layer():
    n = Url4Node("cache")
    first = n._outbound_io()
    assert isinstance(first, HttpIOLayer)
    second = n._outbound_io()
    assert second is first


async def test_aclose_closes_lazily_created_outbound():
    n = Url4Node("lazy")
    first = n._outbound_io()
    assert n._owned_outbound is first
    await n.aclose()
    assert n._owned_outbound is None
    # a fresh call after close creates a new instance, not the closed one
    second = n._outbound_io()
    assert second is not first


async def test_aenter_returns_self(node):
    async with node as n:
        assert n is node


async def test_aexit_closes_lazily_created_outbound():
    n = Url4Node("lazy2")
    async with n:
        n._outbound_io()
        assert n._owned_outbound is not None
    assert n._owned_outbound is None


# --- error-to-status mapping -----------------------------------------------------------------


async def test_status_for_transient_resolution_error_is_502():
    from url4.server import _status_for

    exc = ResolutionError("upstream hiccup")
    assert exc.permanent is False
    assert _status_for(exc) == 502


async def test_status_for_unmapped_code_falls_back_to_500():
    from url4.server import _status_for

    exc = Url4Error("something odd", code="something_else")
    assert _status_for(exc) == 500
