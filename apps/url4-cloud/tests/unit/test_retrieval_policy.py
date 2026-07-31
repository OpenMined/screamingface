"""The retrieval policy as an addressable `[data]` artifact, named by the expression.

FEATURE: a benchmark declares its blocklist at its own url4 address; an expression names that
address with `;web_search_policy=`, and the Runner dereferences it into the request.
STORY: as a benchmark author, the blocklist that keeps a candidate from retrieving the rubric it
is graded against must be PER BENCHMARK (the model routes are shared), tweakable for my own run,
and visible in the expression — because the scoreboard hashes the expression into a recipe
identity, and a blocklist hidden in operator config would let an unguarded run hash identically
to an honest one.

WHY an ADDRESS and not the list itself: protocol params are parse-time CONSTANTS (the compiler
copies `node.params` verbatim; `$` substitution reaches only `TextNode.template` and the packed
context), so a list interpolated from scope is not expressible. A path IS a constant, while its
contents are not — which is the whole trick.

INVARIANT: the policy never enters `context` or `intent`, so it never reaches the model. A
source-shaped spelling could not hold this: a weight-1.0 source packs into the prompt — handing
the candidate a pointer to the answer key — and a weight-0.0 source is excluded from the context
and therefore invisible to the Runner too.
"""

from __future__ import annotations

import json

import httpx
import pytest

from url4.core.errors import ResolutionError
from url4_cloud.runner.config import DataSpec, ModelSpec
from url4_cloud.runner.connector import AigatewayConfig, build_aigateway_world

_NATIVE = "openrouter/anthropic/claude-opus-4.8"
_TAVILY = "claude-opus-4-8"
_PLAIN = "claude-haiku-4-5"

_POLICY_PATH = "/draco/policy/retrieval"
_DOMAINS = ["answers.test", "leak.test"]
_POLICY = json.dumps({"id": "draco/official", "excluded_domains": _DOMAINS})


def _policy_route(body: str = _POLICY, path: str = _POLICY_PATH) -> DataSpec:
    return DataSpec(path=path, value=body, media_type="application/json")


async def _bodies(
    expression: str,
    *,
    cfg: AigatewayConfig | None = None,
    data: tuple[DataSpec, ...] = (),
) -> list[dict]:
    """Evaluate against a mock gateway; return every captured chat-completions body."""
    captured: list[dict] = []

    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}], "usage": {}})

    config = cfg or AigatewayConfig(
        default_model=_PLAIN,
        models=(
            ModelSpec(id=_NATIVE, native_web_search=True),
            ModelSpec(id=_TAVILY, web_tools=True),
            ModelSpec(id=_PLAIN),
        ),
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle), base_url="http://aigateway.test"
    ) as client:
        world = await build_aigateway_world(
            config, client=client, data=data, tavily_client=client, tavily_api_key="tv-key"
        )
        try:
            await world.node.evaluate(expression)
        finally:
            await world.aclose()
    return captured


def _call(route: str, chain: str = "") -> str:
    # `anchor` keeps the all-calls rule from firing the per-row reduce onto default_route.
    return f"(v:1.0:/{route}(a:1.0:'x')!'answer'{chain},anchor:1.0:'a')!'go'"


# --- the happy path ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_named_policy_reaches_the_request_as_excluded_domains() -> None:
    """The expression carries the ADDRESS; the Runner sends the CONTENTS."""
    body = (
        await _bodies(_call(_NATIVE, f";web_search_policy={_POLICY_PATH}"), data=(_policy_route(),))
    )[0]

    assert body["web_search"] is True
    assert body["web_search_excluded_domains"] == _DOMAINS


@pytest.mark.asyncio
async def test_the_policy_is_consumed_and_never_forwarded_as_a_param() -> None:
    """`web_search_policy` is the Runner's vocabulary, not the gateway's. Forwarded, it would be
    an unknown field and the gateway fails closed — a 400 on every retrieving call."""
    body = (
        await _bodies(_call(_NATIVE, f";web_search_policy={_POLICY_PATH}"), data=(_policy_route(),))
    )[0]

    assert "web_search_policy" not in body


@pytest.mark.asyncio
async def test_the_policy_never_reaches_the_model() -> None:
    """INVARIANT: the blocklist names the exact sources that hold the answer key. Packed into the
    prompt it would be a POINTER to them — worse than having no blocklist at all."""
    body = (
        await _bodies(_call(_NATIVE, f";web_search_policy={_POLICY_PATH}"), data=(_policy_route(),))
    )[0]

    rendered = json.dumps(body["messages"])
    for domain in _DOMAINS:
        assert domain not in rendered
    assert "excluded_domains" not in rendered


@pytest.mark.asyncio
async def test_absent_policy_leaves_existing_behaviour_unchanged() -> None:
    """The regression guard for every expression written before this parameter existed."""
    body = (await _bodies(_call(_NATIVE), data=(_policy_route(),)))[0]

    assert body["web_search"] is True
    assert "web_search_excluded_domains" not in body


# --- composition: three layers, union only ----------------------------------------


@pytest.mark.asyncio
async def test_none_drops_the_benchmark_list_but_keeps_the_deployment_one() -> None:
    """WHY `none` cannot mean "retrieve unguarded": the deployment's list is ENFORCEMENT and is
    unreachable from any expression, while the benchmark's is an attributable default. That split
    is what lets one mechanism serve a self-service run and a hosted leaderboard."""
    cfg = AigatewayConfig(
        default_model=_PLAIN,
        models=(ModelSpec(id=_NATIVE, native_web_search=True), ModelSpec(id=_PLAIN)),
        web_search_excluded_domains=("deployment.test",),
    )
    body = (
        await _bodies(_call(_NATIVE, ";web_search_policy=none"), cfg=cfg, data=(_policy_route(),))
    )[0]

    assert body["web_search_excluded_domains"] == ["deployment.test"]


@pytest.mark.asyncio
async def test_caller_domains_union_with_the_policy_rather_than_replacing_it() -> None:
    """INVARIANT: a caller can only ever TIGHTEN — the Runner unions the three layers and renders
    the gateway field itself."""
    body = (
        await _bodies(
            _call(_NATIVE, f";web_search_policy={_POLICY_PATH};web_search_exclude=extra.test"),
            data=(_policy_route(),),
        )
    )[0]

    assert body["web_search_excluded_domains"] == sorted([*_DOMAINS, "extra.test"])


@pytest.mark.asyncio
async def test_caller_domains_apply_with_no_policy_named() -> None:
    """The ad-hoc escape hatch stands alone — a run may add domains without a declared policy."""
    body = (
        await _bodies(_call(_NATIVE, ";web_search_exclude=a.test:b.test"), data=(_policy_route(),))
    )[0]

    assert body["web_search_excluded_domains"] == ["a.test", "b.test"]


@pytest.mark.asyncio
async def test_a_comma_separated_value_is_silently_truncated() -> None:
    """AIDEV-NOTE: pins a GRAMMAR trap, not desired behaviour — the reason the separator is `:`.

    A source list splits on `,` at depth 0 before a param value is read, so a comma truncates the
    value AND turns the remainder into an extra SOURCE of the ENCLOSING group (measured at the
    parser: the outer group gains a third source), where it reaches that group's join or reduce.
    The runner cannot detect any of this — the comma is gone by the time it sees the params.

    Only the runner-visible half is asserted here; the source injection belongs to the grammar
    and is pinned where the grammar is tested. Recorded so the next reader finds it documented
    rather than live.
    """
    body = (
        await _bodies(_call(_NATIVE, ";web_search_exclude=a.test,b.test"), data=(_policy_route(),))
    )[0]

    assert body["web_search_excluded_domains"] == ["a.test"]


@pytest.mark.asyncio
async def test_the_gateway_field_name_stays_runner_owned() -> None:
    """WHY a SEPARATE param name rather than reusing the gateway's field.

    `web_search_excluded_domains` is what the GATEWAY calls it, and an expression setting it
    would be overwritten by the Runner's own value on the body merge — accepted at parse, then
    silently discarded. That rejection is pinned by a prior test and stays exactly as it was.
    `web_search_exclude` is a different thing: a runner-INTERPRETED request for additional
    exclusions, which the Runner unions and then renders into the gateway field itself.
    """
    with pytest.raises(ResolutionError, match="web_search_excluded_domains"):
        await _bodies(
            _call(_NATIVE, ";web_search_excluded_domains=sneaky.test"), data=(_policy_route(),)
        )


# --- resolution is bounded to declared [data] routes -------------------------------


@pytest.mark.asyncio
async def test_an_undeclared_policy_path_is_loud() -> None:
    with pytest.raises(ResolutionError, match="web_search_policy"):
        await _bodies(_call(_NATIVE, ";web_search_policy=/nope/missing"), data=(_policy_route(),))


@pytest.mark.asyncio
async def test_a_model_route_is_not_addressable_as_a_policy() -> None:
    """INVARIANT: the resolver is built from the parsed `[data]` table, not from the node's
    router — so a model or command route is ABSENT rather than defended against, and the Runner
    never re-enters the node it is serving."""
    with pytest.raises(ResolutionError, match="web_search_policy"):
        await _bodies(_call(_NATIVE, f";web_search_policy=/{_NATIVE}"), data=(_policy_route(),))


# --- a failed resolution never degrades to "no guard" ------------------------------


@pytest.mark.asyncio
async def test_malformed_policy_json_is_loud_never_empty() -> None:
    """INVARIANT: an empty list is "retrieve unguarded", and the run would report success with an
    inflated score. Every failure here raises instead."""
    with pytest.raises(ResolutionError):
        await _bodies(
            _call(_NATIVE, f";web_search_policy={_POLICY_PATH}"),
            data=(_policy_route("{not json"),),
        )


@pytest.mark.asyncio
async def test_a_policy_without_excluded_domains_is_loud() -> None:
    with pytest.raises(ResolutionError, match="excluded_domains"):
        await _bodies(
            _call(_NATIVE, f";web_search_policy={_POLICY_PATH}"),
            data=(_policy_route(json.dumps({"id": "draco/official"})),),
        )


@pytest.mark.asyncio
async def test_non_string_domains_are_loud() -> None:
    """The list reaches a strictly-typed gateway schema; a non-string would fail closed there,
    one hop later and with a worse message."""
    with pytest.raises(ResolutionError, match="excluded_domains"):
        await _bodies(
            _call(_NATIVE, f";web_search_policy={_POLICY_PATH}"),
            data=(_policy_route(json.dumps({"excluded_domains": ["ok.test", 7]})),),
        )


@pytest.mark.asyncio
async def test_naming_a_policy_on_a_non_retrieving_route_is_loud() -> None:
    """A policy on a route that never searches reads as though retrieval were guarded when no
    retrieval happens at all — same silent shape as `web_search=true` on such a route."""
    with pytest.raises(ResolutionError):
        await _bodies(_call(_PLAIN, f";web_search_policy={_POLICY_PATH}"), data=(_policy_route(),))


@pytest.mark.asyncio
async def test_naming_a_policy_on_a_tavily_route_is_loud() -> None:
    """WHY the Tavily loop is not a home for this: domain exclusion is a PROVIDER-side control,
    honoured by the provider running the search. On a `web_tools` route the RUNNER searches, so a
    declared policy would be accepted and never enforced — which is the failure this closes, not
    a case of it."""
    with pytest.raises(ResolutionError):
        await _bodies(_call(_TAVILY, f";web_search_policy={_POLICY_PATH}"), data=(_policy_route(),))


@pytest.mark.asyncio
async def test_ad_hoc_exclusions_on_a_non_retrieving_route_are_loud() -> None:
    with pytest.raises(ResolutionError):
        await _bodies(_call(_PLAIN, ";web_search_exclude=a.test"), data=(_policy_route(),))


# --- caching --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_policy_is_read_once_per_world(tmp_path) -> None:
    """WHY memoized: a benchmark image is immutable, so staleness is unreachable in production,
    and a DRACO run would otherwise re-read the file on every answering call.

    TRADEOFF this pins: a LOCAL run that edits a policy file needs a restart. `file` providers
    are otherwise re-read per request, so that difference is surprising and is asserted here
    rather than left to be discovered.
    """
    path = tmp_path / "policy.json"
    path.write_text(_POLICY, encoding="utf-8")
    data = (DataSpec(path=_POLICY_PATH, file=str(path), media_type="application/json"),)

    captured: list[dict] = []

    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}], "usage": {}})

    config = AigatewayConfig(
        default_model=_PLAIN,
        models=(ModelSpec(id=_NATIVE, native_web_search=True), ModelSpec(id=_PLAIN)),
    )
    call = _call(_NATIVE, f";web_search_policy={_POLICY_PATH}")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle), base_url="http://aigateway.test"
    ) as client:
        world = await build_aigateway_world(config, client=client, data=data)
        try:
            await world.node.evaluate(call)
            path.write_text(json.dumps({"excluded_domains": ["changed.test"]}), encoding="utf-8")
            await world.node.evaluate(call)
        finally:
            await world.aclose()

    assert [body["web_search_excluded_domains"] for body in captured] == [_DOMAINS, _DOMAINS]
