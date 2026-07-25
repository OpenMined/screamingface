"""Phase 6b (OME-479 §4.2/§5.1/§5.3): OpenRouter async discovery — live fetch.

FEATURE: OpenRouter P0 observation overlay, DYNAMIC source. Bridges the bounded
transport (§5.2) to the pure catalog parser (§6.1): fetch the FIXED public
/api/v1/models catalog through the INJECTED client, parse the matching model's
supported_parameters into per-model evidence, return a ProviderDiscoverySnapshot.

INVARIANT (§5.3): three outcomes, three signals — a snapshot means the source was
REACHED (an empty one means reached-but-unlisted), a sanitized DiscoveryError means
the attempt FAILED, and None means NO ATTEMPT was made. Discovery never fabricates
support, and a raw upstream fault never propagates out.
INVARIANT (§5.2): discovery only ever dials the FIXED public catalog URL; the
gateway model id is stripped to its upstream form before the catalog is queried.
"""

from __future__ import annotations

import json

import pytest

from aigateway.core.chat_parameters import ProviderDiscoverySnapshot
from aigateway.core.parameter_discovery import (
    DiscoveryError,
    DiscoveryHttpClient,
    RawResponse,
)
from aigateway.core.parameter_discovery_cache import CacheLimits, ObservationCache
from aigateway.core.plugin_base import ProviderPluginBase
from aigateway.plugins.openrouter_provider.discovery import (
    MODELS_URL,
    discover_openrouter_snapshot,
)
from aigateway.plugins.openrouter_provider.plugin import OpenRouterProviderPlugin

_UPSTREAM = "google/gemini-2.0-flash-001"
_CATALOG = {
    "data": [
        {
            "id": _UPSTREAM,
            "supported_parameters": ["temperature", "top_p", "top_k", "max_tokens"],
        },
        {"id": "z/other", "supported_parameters": ["temperature"]},
    ]
}


class _FakeClock:
    """Deterministic monotonic seam for the cache's TTL math."""

    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def now(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


class _RoutingClient(DiscoveryHttpClient):
    """Canned JSON body per URL; records dialed URLs; optional pre-sanitized error."""

    def __init__(
        self,
        bodies: dict[str, object] | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self._bodies = bodies or {}
        self._error = error
        self.calls: list[str] = []

    async def get(self, url: str, *, timeout_s: float, max_bytes: int) -> RawResponse:
        self.calls.append(url)
        if self._error is not None:
            raise self._error
        return RawResponse(
            status=200, content_type="application/json", body=json.dumps(self._bodies[url])
        )


@pytest.mark.asyncio
async def test_live_snapshot_carries_per_model_evidence() -> None:
    client = _RoutingClient({MODELS_URL: _CATALOG})
    snap = await discover_openrouter_snapshot(_UPSTREAM, client=client)
    assert isinstance(snap, ProviderDiscoverySnapshot)
    paths = {o.request_path for o in snap.model_observations}
    # standard fields keep identity; the native top_k maps to its wrapper path so
    # the overlay lines it up with the provider_params.top_k rule.
    assert {"temperature", "top_p", "max_tokens", "provider_params.top_k"} <= paths
    assert "top_k" not in paths
    assert all(o.source == "openrouter:models" for o in snap.model_observations)
    # only the FIXED public catalog URL was dialed.
    assert client.calls == [MODELS_URL]


@pytest.mark.asyncio
async def test_live_model_evidence_is_kept_out_of_the_endpoint_field() -> None:
    # §5.1: live per-model evidence must never masquerade as endpoint evidence.
    client = _RoutingClient({MODELS_URL: _CATALOG})
    snap = await discover_openrouter_snapshot(_UPSTREAM, client=client)
    assert snap is not None
    assert snap.endpoint_observations == ()


@pytest.mark.asyncio
async def test_successful_fetch_missing_model_is_empty_but_present() -> None:
    # discovery REACHED the source but the model is absent: honest empty evidence,
    # distinct from a fetch failure (None). Never fabricated support.
    client = _RoutingClient({MODELS_URL: _CATALOG})
    snap = await discover_openrouter_snapshot("nope/absent", client=client)
    assert isinstance(snap, ProviderDiscoverySnapshot)
    assert snap.model_observations == ()


@pytest.mark.asyncio
async def test_fetch_failure_raises_for_the_cache_to_degrade() -> None:
    # OME-606 (supersedes the earlier failure→None contract): swallowing the error
    # made "the fetch failed" indistinguishable from "there is nothing to discover",
    # and the cache reads any normal return as a SUCCESSFUL refresh — so an outage
    # would have been stored labelled fresh. Raising is what routes it to
    # stale/degraded. The sanitized reason survives; the raw fault still does not.
    client = _RoutingClient(error=DiscoveryError("unreachable"))
    with pytest.raises(DiscoveryError) as exc:
        await discover_openrouter_snapshot(_UPSTREAM, client=client)
    assert exc.value.reason == "unreachable"
    assert client.calls == [MODELS_URL]  # attempted exactly once, no retry storm


@pytest.mark.asyncio
async def test_plugin_hook_strips_gateway_prefix_to_query_upstream() -> None:
    # the detail route knows only the canonical gateway id; the plugin owns the
    # strip to the upstream id the public catalog is keyed by.
    plugin = OpenRouterProviderPlugin()
    client = _RoutingClient({MODELS_URL: _CATALOG})
    snap = await plugin.discover_chat_parameter_snapshot(
        model="openrouter/" + _UPSTREAM, client=client
    )
    assert snap is not None
    assert {"temperature", "provider_params.top_k"} <= {
        o.request_path for o in snap.model_observations
    }


@pytest.mark.asyncio
async def test_plugin_hook_rejects_non_gateway_model_without_dialing() -> None:
    # a model id that is not a valid gateway id is not dispatchable here, so there
    # is nothing to discover — fail closed to None and never open a connection.
    plugin = OpenRouterProviderPlugin()
    client = _RoutingClient({MODELS_URL: _CATALOG})
    snap = await plugin.discover_chat_parameter_snapshot(model="bare-model", client=client)
    assert snap is None
    assert client.calls == []


@pytest.mark.asyncio
async def test_base_plugin_discovery_defaults_to_none_no_network() -> None:
    # A provider with no dynamic source returns None by default and never dials —
    # the caller then relies on labelled-local observations alone.
    class _NoDiscovery(ProviderPluginBase):
        custom_llm_provider = "nodisc"

        def register_models(self):
            return []

    plugin = _NoDiscovery()
    client = _RoutingClient()
    assert await plugin.discover_chat_parameter_snapshot(model="nodisc/x", client=client) is None
    assert client.calls == []


# --- OME-606: failure is distinguishable from "nothing to discover" ---------------------


@pytest.mark.asyncio
async def test_plugin_hook_propagates_failure_instead_of_swallowing_it() -> None:
    # The hook's None is reserved for NOT ATTEMPTED. Having it also mean "attempted
    # and failed" is what let an outage reach the cache looking like success.
    plugin = OpenRouterProviderPlugin()
    client = _RoutingClient(error=DiscoveryError("timeout"))
    with pytest.raises(DiscoveryError) as exc:
        await plugin.discover_chat_parameter_snapshot(
            model="openrouter/" + _UPSTREAM, client=client
        )
    assert exc.value.reason == "timeout"
    assert client.calls == [MODELS_URL]


@pytest.mark.asyncio
async def test_outage_degrades_through_the_cache_instead_of_caching_fresh_none() -> None:
    # The end-to-end case the protocol exists for: good snapshot → TTL expiry →
    # outage → STALE last-good → stale window expiry → DEGRADED. Under the swallowing
    # protocol the first failure stored a fresh None and the last good value was lost.
    clock = _FakeClock()
    cache = ObservationCache(
        clock=clock, limits=CacheLimits(ttl_s=60.0, stale_ttl_s=120.0, max_entries=8)
    )
    plugin = OpenRouterProviderPlugin()
    model = "openrouter/" + _UPSTREAM

    def refresh_with(client: DiscoveryHttpClient):
        async def _refresh():
            return await plugin.discover_chat_parameter_snapshot(model=model, client=client)

        return _refresh

    healthy = refresh_with(_RoutingClient({MODELS_URL: _CATALOG}))
    failing = refresh_with(_RoutingClient(error=DiscoveryError("unreachable")))

    good = await cache.get_or_refresh("or:m", revision="r1", refresh=healthy)
    assert good.freshness == "fresh"
    assert good.value is not None

    clock.advance(61.0)  # past TTL, inside the stale window
    degraded_once = await cache.get_or_refresh("or:m", revision="r1", refresh=failing)
    assert degraded_once.freshness == "stale"
    assert degraded_once.value is good.value  # last good evidence retained

    clock.advance(200.0)  # past ttl + stale
    fully_degraded = await cache.get_or_refresh("or:m", revision="r1", refresh=failing)
    assert fully_degraded.freshness == "degraded"
    assert fully_degraded.value is None
