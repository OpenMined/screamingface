"""Client facade tests — Client + Url4Result over a deterministic StaticIOLayer.

STORY: as an SDK user I build queries in Python (or raw url4 text), point them
at a node (or run them locally), and get back a result that carries the exact
canonical expression that ran (`.request`) — the protocol's audit artifact.
"""

from __future__ import annotations

import json

import pytest

from url4 import StaticIOLayer, build
from url4.builders import iterate, src
from url4.client import Client, Url4Result

pytestmark = pytest.mark.asyncio


@pytest.fixture()
def wire() -> list[tuple[str, str, str]]:
    """Captured (route, context, intent) triples for every routed call."""
    return []


@pytest.fixture()
def io(wire) -> StaticIOLayer:
    def route(name: str):
        def handler(context: str, intent: str) -> str:
            wire.append((name, context, intent))
            return f"{name.upper()}-RESULT"

        return handler

    return StaticIOLayer(
        fetch_map={
            "https://x": "ARTICLE",
            "https://data/rows": '["alpha", "beta"]',
        },
        routes={
            "/claude": route("/claude"),
            "/llama": route("/llama"),
            "url4://node.ai/v1": route("remote"),
        },
    )


# --- Url4Result --------------------------------------------------------------------


async def test_result_envelope_accessors():
    res = Url4Result(text='["a", "b"]', request="(x)!'go'")
    assert str(res) == '["a", "b"]'
    assert res.data == ["a", "b"]
    assert res.elements == ["a", "b"]
    scalar = Url4Result(text='{"k": 1}', request="(x)!'go'")
    assert scalar.data == {"k": 1}
    with pytest.raises(ValueError, match="list"):
        _ = scalar.elements
    prose = Url4Result(text="not json", request="(x)!'go'")
    with pytest.raises(ValueError, match="JSON"):
        _ = prose.data


# --- local execution ------------------------------------------------------------------


async def test_local_query_resolves_and_carries_request(io):
    async with Client(io) as client:
        res = await client.query(src("https://x", name="a"), intent="Summarize $a")
    assert "ARTICLE" in res.text
    assert res.request == "(a=https://x)!'Summarize $a'"
    assert build(res.request) is not None  # the request is valid canonical url4


async def test_local_query_accepts_raw_strings(io):
    async with Client(io) as client:
        res = await client.query("a=https://x", intent="Summarize $a")
    assert "ARTICLE" in res.text


async def test_evaluate_raw_expression_and_env(io):
    async with Client(io) as client:
        res = await client.evaluate("(a=https://x)!'[$who] Summarize $a'", env={"who": "junior"})
    assert "junior" in res.text
    assert "ARTICLE" in res.text


async def test_local_iterate_returns_elements(io):
    async with Client(io) as client:
        res = await client.iterate("https://data/rows", intent="Echo $item")
    assert res.elements == ["Echo alpha", "Echo beta"]
    assert res.request == "https://data/rows*()!'Echo $item'"


async def test_local_broadcast_produces_per_source_results(io):
    async with Client(io) as client:
        res = await client.broadcast("https://x", "https://x", intent="Extract")
    assert len(res.elements) == 2


async def test_local_reduce_dispatches_calls_and_reducer(io, wire):
    async with Client(io) as client:
        res = await client.reduce(
            ["/claude(https://x)!'Go'", "/llama(https://x)!'Go'"], "Merge $1 and $2"
        )
    routes = [name for name, _, _ in wire]
    assert "/claude" in routes and "/llama" in routes
    # the reducer instruction itself is dispatched to the default processor
    assert routes.count("/claude") == 2
    assert res.text == "/CLAUDE-RESULT"


async def test_local_query_params_ride_the_expression(io):
    # AIDEV-NOTE: quorum is ENFORCED by the executor (not just carried) — the
    # value must be satisfiable by the source list.
    async with Client(io) as client:
        res = await client.query("https://x", intent="go", quorum=1, triggers=(1, 2), t=60)
    assert res.request == "(https://x)!'go';quorum=1;triggers=1,2;t=60"


# --- remote execution --------------------------------------------------------------------


async def test_remote_query_sends_context_and_intent(io, wire):
    async with Client(io, node="url4://node.ai") as client:
        res = await client.query(src("https://x", name="a"), intent="Summarize $a")
    assert res.text == "REMOTE-RESULT"
    assert wire == [("remote", "a=https://x", "Summarize $a")]
    # the request is the parenthesized remote expression (intent stays remote)
    assert res.request == "(url4://node.ai/v1(a=https://x)!'Summarize $a')"


async def test_remote_target_forms(io, wire):
    async with Client(io) as client:
        await client.query("https://x", intent="go", node="node.ai", path="/v1")
        await client.query("https://x", intent="go", node="url4://node.ai/v1")
    assert [name for name, _, _ in wire] == ["remote", "remote"]


async def test_remote_broadcast_rides_as_param(io, wire):
    async with Client(io, node="url4://node.ai/v1") as client:
        res = await client.broadcast("https://a.com", "https://b.com", intent="Extract")
    assert "?broadcast&q=" in res.request
    # the remote node's envelope decode folds the param back into !*
    _, context, _ = wire[0]
    assert context == "https://a.com, https://b.com"


async def test_remote_iterate_reduce_is_canonical_reduce_over_iteration(io, wire):
    async with Client(io, node="url4://node.ai/v1") as client:
        it = iterate("https://data/rows", "x=$item", intent="per row", reduce="agg")
        res = await client.execute(it)
    _, context, intent = wire[0]
    assert context == "https://data/rows*(x=$item)!'per row'"
    assert intent == "agg"
    assert res.text == "REMOTE-RESULT"


async def test_remote_protocol_params_precede_q(io):
    async with Client(io, node="url4://node.ai/v1") as client:
        res = await client.query("https://x", intent="go", quorum=2)
    assert "?quorum=2&q=" in res.request


# --- lifecycle -----------------------------------------------------------------------------


async def test_injected_io_is_never_closed(io):
    client = Client(io)
    await client.query("https://x", intent="go")
    await client.aclose()  # no-op for injected io; must not raise
    # io still usable
    res = await Client(io).query("https://x", intent="go")
    assert "ARTICLE" in res.text


async def test_owned_io_lifecycle_without_use():
    # No network: the owned HttpIOLayer is created lazily, so an unused client
    # closes cleanly.
    async with Client() as client:
        assert client is not None


async def test_result_is_json_roundtrippable():
    res = Url4Result(text=json.dumps({"ok": True}), request="()!'x'")
    assert res.data == {"ok": True}
