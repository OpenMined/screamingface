"""The retrieval policy is ENFORCED on the runner-driven Tavily (`web_tools`) path.

FEATURE: a declared blocklist guards every retrieving route, whichever mechanism searches.
STORY: as a benchmark author, a candidate answering through a Tavily route must not be able to
retrieve the rubric — or the paper — it is being graded against.

WHY this module exists at all: exclusion used to be a PROVIDER-side control, so
`_retrieval_exclusions` REFUSED a policy on a `web_tools` route on the grounds that the runner
could not enforce one. MEASURED 2026-08-02 against the live API, that premise is false — Tavily's
`/search` accepts `exclude_domains` and honours it. On a `web_tools` route the RUNNER is the
searcher, so the runner is exactly who must enforce the guard.

INVARIANT: `web_fetch` is the sharper of the two leaks. `/search` returns ranked snippets the
model may or may not use; `/extract` returns the document VERBATIM, so an unguarded fetch of the
DRACO paper hands over the answer key in full. Tavily's `/extract` has no exclusion parameter, so
that check has no home but this one.
"""

from __future__ import annotations

import json

import httpx
import pytest

from url4.core.errors import ResolutionError
from url4_cloud.runner.config import DataSpec, ModelSpec
from url4_cloud.runner.connector import AigatewayConfig, build_aigateway_world

_TAVILY = "claude-opus-4-8"
_PLAIN = "claude-haiku-4-5"

_POLICY_PATH = "/draco/policy/retrieval"
_BLOCKED = "leak.test"
_POLICY = json.dumps({"id": "draco/official", "excluded_domains": [_BLOCKED]})

_SEARCH_CALL = {
    "id": "call-1",
    "type": "function",
    "function": {"name": "web_search", "arguments": json.dumps({"query": "draco rubric"})},
}


def _fetch_call(url: str, call_id: str = "call-2") -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": "web_fetch", "arguments": json.dumps({"url": url})},
    }


def _policy_route(body: str = _POLICY, path: str = _POLICY_PATH) -> DataSpec:
    return DataSpec(path=path, value=body, media_type="application/json")


class _Rig:
    """A mock standing in for BOTH upstreams, routed by path.

    The gateway is scripted with a queue of tool-call turns; anything left over answers with
    content, which is what ends the loop. Tavily payloads are captured so the assertions can read
    what the runner actually SENT rather than what it meant to send — the distinction that the
    misspelled `excluded_domains` key made expensive.
    """

    def __init__(
        self,
        turns: list[list[dict]] | None = None,
        search_results: list[dict] | None = None,
    ) -> None:
        self.turns = list(turns or [])
        self.search_results = search_results or [
            {"title": "t", "url": "https://ok.test/a", "content": "c"}
        ]
        self.searches: list[dict] = []
        self.extracts: list[dict] = []
        self.tool_messages: list[dict] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        if request.url.path.endswith("/chat/completions"):
            return self._gateway(body)
        if request.url.path.endswith("/search"):
            self.searches.append(body)
            return httpx.Response(200, json={"results": self.search_results})
        self.extracts.append(body)
        return httpx.Response(200, json={"results": [{"raw_content": "PAGE"}]})

    def _gateway(self, body: dict) -> httpx.Response:
        # Every tool reply the runner fed back, so a refusal can be asserted as the model SAW it —
        # not merely as the absence of an upstream call.
        self.tool_messages.extend(
            message for message in body.get("messages", []) if message.get("role") == "tool"
        )
        if not self.turns:
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "final"}}], "usage": {}}
            )
        message = {"content": None, "tool_calls": self.turns.pop(0)}
        return httpx.Response(200, json={"choices": [{"message": message}], "usage": {}})


async def _run(
    chain: str,
    *,
    turns: list[list[dict]] | None = None,
    data: tuple[DataSpec, ...] = (),
    route: str = _TAVILY,
    search_results: list[dict] | None = None,
) -> _Rig:
    rig = _Rig(turns, search_results)
    config = AigatewayConfig(
        default_model=_PLAIN,
        models=(ModelSpec(id=_TAVILY, web_tools=True), ModelSpec(id=_PLAIN)),
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(rig.handle), base_url="http://aigateway.test"
    ) as client:
        world = await build_aigateway_world(
            config, client=client, data=data, tavily_client=client, tavily_api_key="tv-key"
        )
        try:
            # `anchor` keeps the all-calls rule from firing the per-row reduce onto default_route.
            await world.node.evaluate(
                f"(v:1.0:/{route}(a:1.0:'x')!'answer'{chain},anchor:1.0:'a')!'go'"
            )
        finally:
            await world.aclose()
    return rig


# --- /search carries the blocklist -------------------------------------------------


@pytest.mark.asyncio
async def test_a_policy_on_a_tavily_route_reaches_the_search_as_exclude_domains() -> None:
    """The inverse of the retired `test_naming_a_policy_on_a_tavily_route_is_loud`.

    `exclude_domains` is TAVILY's spelling and is deliberately not our `excluded_domains` — the
    translation boundary is this one call, exactly as `_apply_web_search` is for OpenRouter.
    """
    rig = await _run(
        f";web_search_policy={_POLICY_PATH}", turns=[[_SEARCH_CALL]], data=(_policy_route(),)
    )

    assert rig.searches, "the tool loop never reached Tavily"
    assert rig.searches[0]["exclude_domains"] == [_BLOCKED]


@pytest.mark.asyncio
async def test_no_policy_omits_the_field_rather_than_sending_an_empty_list() -> None:
    """INVARIANT: absent and "exclude nothing" must stay distinguishable upstream — the same rule
    `_native_web_search` follows for the gateway field."""
    rig = await _run("", turns=[[_SEARCH_CALL]])

    assert rig.searches
    assert "exclude_domains" not in rig.searches[0]


@pytest.mark.asyncio
async def test_ad_hoc_exclusions_union_with_the_policy_on_the_tavily_path() -> None:
    """A caller may TIGHTEN the guard and may never loosen it — the property the whole three-layer
    union exists to hold, asserted here on the mechanism that had no guard at all."""
    rig = await _run(
        f";web_search_policy={_POLICY_PATH};web_search_exclude=extra.test",
        turns=[[_SEARCH_CALL]],
        data=(_policy_route(),),
    )

    assert rig.searches[0]["exclude_domains"] == [_BLOCKED, "extra.test"]


@pytest.mark.asyncio
async def test_the_blocklist_still_holds_on_a_later_loop_iteration() -> None:
    """A tool-calling turn re-posts, and the guard must survive every hop.

    WHY this is not paranoia: the exclusions are resolved ONCE before the loop precisely so a
    later turn cannot escape them. A future refactor that resolved them per-iteration would pass
    every other test in this module and fail only here.
    """
    rig = await _run(
        f";web_search_policy={_POLICY_PATH}",
        turns=[[_SEARCH_CALL], [dict(_SEARCH_CALL, id="call-3")]],
        data=(_policy_route(),),
    )

    assert len(rig.searches) == 2
    assert all(search["exclude_domains"] == [_BLOCKED] for search in rig.searches)


# --- /extract is guarded by the runner, because Tavily offers no parameter ----------


@pytest.mark.asyncio
async def test_web_fetch_of_a_blocked_host_never_reaches_tavily() -> None:
    """INVARIANT: `/extract` returns the document VERBATIM, so this is the sharper leak of the
    two. Tavily has no exclusion parameter for it, so the runner refuses before the request
    leaves — asserted as "no upstream call", never merely as a message."""
    rig = await _run(
        f";web_search_policy={_POLICY_PATH}",
        turns=[[_fetch_call(f"https://{_BLOCKED}/rubric")]],
        data=(_policy_route(),),
    )

    assert rig.extracts == []


@pytest.mark.asyncio
async def test_the_refusal_is_reported_back_to_the_model() -> None:
    """Fed back as a tool message like every other tool failure. A silent empty result would read
    as "the page was empty" and invite a retry through a different URL."""
    rig = await _run(
        f";web_search_policy={_POLICY_PATH}",
        turns=[[_fetch_call(f"https://{_BLOCKED}/rubric")]],
        data=(_policy_route(),),
    )

    refusals = [
        m for m in rig.tool_messages if _BLOCKED in m["content"] or "excluded" in m["content"]
    ]
    assert refusals, f"no refusal reached the model: {rig.tool_messages}"


@pytest.mark.asyncio
async def test_an_allowed_host_is_still_fetched() -> None:
    """The guard is a blocklist, not a blanket denial — a `web_tools` route with a policy must
    still be able to research."""
    rig = await _run(
        f";web_search_policy={_POLICY_PATH}",
        turns=[[_fetch_call("https://allowed.test/page")]],
        data=(_policy_route(),),
    )

    assert len(rig.extracts) == 1


@pytest.mark.asyncio
async def test_a_path_shaped_entry_blocks_that_path_and_not_the_whole_host() -> None:
    """MEASURED 2026-08-02: our shipped blocklist is path-shaped (`arxiv.org/abs/2602.11685`), and
    blocking all of `arxiv.org` would strip a major legitimate source from a deep-research
    benchmark. So the match must be precise in BOTH directions."""
    policy = json.dumps({"id": "p", "excluded_domains": ["arxiv.org/abs/2602.11685"]})

    blocked = await _run(
        f";web_search_policy={_POLICY_PATH}",
        turns=[[_fetch_call("https://arxiv.org/abs/2602.11685")]],
        data=(_policy_route(policy),),
    )
    allowed = await _run(
        f";web_search_policy={_POLICY_PATH}",
        turns=[[_fetch_call("https://arxiv.org/abs/1234.56789")]],
        data=(_policy_route(policy),),
    )

    assert blocked.extracts == []
    assert len(allowed.extracts) == 1


@pytest.mark.asyncio
async def test_a_subdomain_of_a_blocked_host_is_blocked() -> None:
    """A bare-host entry covers subdomains, or `cdn.leak.test` walks straight around the guard."""
    rig = await _run(
        f";web_search_policy={_POLICY_PATH}",
        turns=[[_fetch_call(f"https://cdn.{_BLOCKED}/rubric")]],
        data=(_policy_route(),),
    )

    assert rig.extracts == []


@pytest.mark.asyncio
async def test_a_trailing_dot_cannot_bypass_the_blocked_host() -> None:
    rig = await _run(
        f";web_search_policy={_POLICY_PATH}",
        turns=[[_fetch_call(f"https://{_BLOCKED}./rubric")]],
        data=(_policy_route(),),
    )

    assert rig.extracts == []


@pytest.mark.asyncio
async def test_search_results_are_post_filtered_before_the_model_sees_them() -> None:
    rig = await _run(
        f";web_search_policy={_POLICY_PATH}",
        turns=[[_SEARCH_CALL]],
        data=(_policy_route(),),
        search_results=[
            {
                "title": "blocked",
                "url": f"https://cdn.{_BLOCKED}/answer-key",
                "content": "PRIVATE RUBRIC",
            },
            {"title": "allowed", "url": "https://ok.test/source", "content": "PUBLIC"},
        ],
    )

    tool_output = "\n".join(message["content"] for message in rig.tool_messages)
    assert "PRIVATE RUBRIC" not in tool_output
    assert "PUBLIC" in tool_output


# --- the invariant that did NOT change --------------------------------------------


@pytest.mark.asyncio
async def test_a_policy_on_a_route_that_retrieves_neither_way_is_still_loud() -> None:
    """Retiring the Tavily refusal did NOT weaken this: a policy on a route that never searches
    still reads as a guarded run while no retrieval happens at all."""
    with pytest.raises(ResolutionError):
        await _run(f";web_search_policy={_POLICY_PATH}", data=(_policy_route(),), route=_PLAIN)
