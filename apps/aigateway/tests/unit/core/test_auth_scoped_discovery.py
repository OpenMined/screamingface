"""OME-632: binding one contract read's auth mode to a provider's discovery hooks.

FEATURE: auth-scoped provider evidence. A provider whose auth modes reach different
upstreams cannot answer "is there a dynamic source for this model" without the
resolved mode — Gemini's api-key path talks to an API that publishes a schema, its
OAuth path to one that does not.

INVARIANT: the ``DiscoveryRuntime``'s own port stays auth-FREE. The runtime never
reads the mode — it caches by (source, model, revision) — so threading a value it
never inspects through its port would be coupling. The route, which already
resolved the mode, binds it and hands the runtime a narrowed view.

INVARIANT (cache identity): auth is deliberately absent from the cache key. A
provider whose snapshot CONTENT varies by mode must say so in the ref itself — a
different source or revision keys separately. Declaring no ref at all (Gemini's
OAuth path) forms no key.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from aigateway.core.chat_parameters import (
    ProviderDiscoverySnapshot,
    ProviderParameterObservation,
)
from aigateway.core.discovery_runtime import (
    DiscoveryRuntime,
    auth_scoped,
    static_discovery_outcome,
)
from aigateway.core.parameter_discovery import (
    DiscoveryLimits,
    DiscoverySourceRef,
    RawResponse,
)
from aigateway.core.parameter_discovery_cache import CacheLimits, ObservationCache
from aigateway.core.plugin_base import ModelEntry, PluginSettings, ProviderPluginBase

_MODEL = "gemini-cli/gemini-2.5-pro"
_REF = DiscoverySourceRef(source="probe:source", revision="probe:rev-1")
_SNAPSHOT = ProviderDiscoverySnapshot(
    source_revision=_REF.revision,
    endpoint_observations=(
        ProviderParameterObservation(
            request_path="temperature", support="supported", source="probe:source"
        ),
    ),
)


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def utc(self) -> datetime:
        return datetime(2026, 7, 27, tzinfo=UTC) + timedelta(seconds=self.t)


class _NeverCalledClient:
    async def get(self, url: str, *, timeout_s: float, max_bytes: int) -> RawResponse:
        raise AssertionError(f"discovery must not have been attempted (url={url})")


class _AuthAwarePlugin:
    """Declares a source ONLY for the mode it was told to serve."""

    def __init__(self, *, serves: str = "api_key") -> None:
        self._serves = serves
        self.declared: list[Any] = []
        self.fetched: list[dict[str, Any]] = []

    def chat_discovery_source(
        self, *, model: str, auth_type: Any = None
    ) -> DiscoverySourceRef | None:
        self.declared.append(auth_type)
        return _REF if auth_type == self._serves else None

    async def discover_chat_parameter_snapshot(
        self,
        *,
        model: str,
        client: Any,
        limits: DiscoveryLimits | None = None,
        auth_type: Any = None,
    ) -> ProviderDiscoverySnapshot | None:
        self.fetched.append(
            {"model": model, "client": client, "limits": limits, "auth_type": auth_type}
        )
        return _SNAPSHOT if auth_type == self._serves else None


class _NarrowPlugin:
    """A double satisfying the runtime's port WITHOUT knowing about auth at all."""

    def __init__(self) -> None:
        self.fetches = 0

    def chat_discovery_source(self, *, model: str) -> DiscoverySourceRef | None:
        return _REF

    async def discover_chat_parameter_snapshot(
        self, *, model: str, client: Any, limits: DiscoveryLimits | None = None
    ) -> ProviderDiscoverySnapshot | None:
        self.fetches += 1
        return _SNAPSHOT


class _ModeIgnoringPlugin:
    """A provider whose public evidence does not vary by mode — the common case."""

    def __init__(self) -> None:
        self.fetches = 0

    def chat_discovery_source(
        self, *, model: str, auth_type: Any = None
    ) -> DiscoverySourceRef | None:
        return _REF

    async def discover_chat_parameter_snapshot(
        self,
        *,
        model: str,
        client: Any,
        limits: DiscoveryLimits | None = None,
        auth_type: Any = None,
    ) -> ProviderDiscoverySnapshot | None:
        self.fetches += 1
        return _SNAPSHOT


def _runtime(clock: _Clock, *, client: Any = None) -> DiscoveryRuntime:
    return DiscoveryRuntime(
        client=client if client is not None else _NeverCalledClient(),
        cache=ObservationCache(
            clock=clock, limits=CacheLimits(ttl_s=60.0, stale_ttl_s=120.0, max_entries=8)
        ),
        limits=DiscoveryLimits(timeout_s=1.5, max_bytes=2048),
        now_utc=clock.utc,
    )


# --- the bound mode reaches the provider -------------------------------------


def test_the_bound_mode_reaches_the_source_declaration() -> None:
    plugin = _AuthAwarePlugin()

    assert auth_scoped(plugin, "api_key").chat_discovery_source(model=_MODEL) == _REF
    assert auth_scoped(plugin, "oauth").chat_discovery_source(model=_MODEL) is None
    assert plugin.declared == ["api_key", "oauth"]


@pytest.mark.asyncio
async def test_the_bound_mode_reaches_the_fetch() -> None:
    # INVARIANT: ONE predicate gates both hooks, so a view that bound the mode for
    # the declaration but not the fetch would let a provider promise evidence and
    # then report NOT ATTEMPTED — indistinguishable from an outage.
    plugin = _AuthAwarePlugin()
    view = auth_scoped(plugin, "api_key")

    snapshot = await view.discover_chat_parameter_snapshot(
        model=_MODEL, client=_NeverCalledClient()
    )

    assert snapshot is _SNAPSHOT
    assert plugin.fetched[0]["auth_type"] == "api_key"


@pytest.mark.asyncio
async def test_the_view_forwards_the_runtime_arguments_untouched() -> None:
    plugin = _AuthAwarePlugin()
    client = _NeverCalledClient()
    limits = DiscoveryLimits(timeout_s=0.25, max_bytes=99)

    await auth_scoped(plugin, "api_key").discover_chat_parameter_snapshot(
        model=_MODEL, client=client, limits=limits
    )

    assert plugin.fetched == [
        {"model": _MODEL, "client": client, "limits": limits, "auth_type": "api_key"}
    ]


def test_an_unresolved_mode_is_forwarded_as_none_rather_than_guessed() -> None:
    # Fail-closed: a provider that only serves one mode must see the absence, not a
    # default the binder invented on its behalf.
    plugin = _AuthAwarePlugin()

    assert auth_scoped(plugin, None).chat_discovery_source(model=_MODEL) is None
    assert plugin.declared == [None]


# --- through the runtime ------------------------------------------------------


@pytest.mark.asyncio
async def test_a_mode_with_no_source_is_never_fetched_and_never_cached() -> None:
    clock = _Clock()
    plugin = _AuthAwarePlugin()

    outcome = await _runtime(clock).observe(auth_scoped(plugin, "oauth"), model=_MODEL)

    assert plugin.fetched == []
    assert outcome.snapshot is None
    assert outcome.freshness == static_discovery_outcome().freshness


@pytest.mark.asyncio
async def test_the_served_mode_is_observed_with_a_real_window() -> None:
    clock = _Clock()
    plugin = _AuthAwarePlugin()

    outcome = await _runtime(clock).observe(auth_scoped(plugin, "api_key"), model=_MODEL)

    assert outcome.snapshot is _SNAPSHOT
    assert outcome.freshness["observed_at"] is not None
    assert outcome.freshness["degraded"] is False


@pytest.mark.asyncio
async def test_the_runtime_port_still_admits_a_provider_that_ignores_auth_entirely() -> None:
    # The reason the shared Protocol was NOT widened: a caller holding a narrow
    # DiscoverablePlugin — every auth-independent provider and every pre-existing
    # test double — still reaches the runtime unchanged, with no binder involved.
    clock = _Clock()
    plugin = _NarrowPlugin()

    outcome = await _runtime(clock).observe(plugin, model=_MODEL)

    assert outcome.snapshot is _SNAPSHOT
    assert plugin.fetches == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["api_key", "oauth", None])
async def test_a_mode_ignoring_provider_is_unaffected_by_which_mode_is_bound(
    mode: Any,
) -> None:
    # OpenRouter and Hugging Face accept the mode for port conformance and discard
    # it: their catalogs are public. Binding must therefore be inert for them —
    # same ref, same snapshot, one fetch, whatever the contract read resolved.
    plugin = _ModeIgnoringPlugin()

    outcome = await _runtime(_Clock()).observe(auth_scoped(plugin, mode), model=_MODEL)

    assert outcome.snapshot is _SNAPSHOT
    assert plugin.fetches == 1


# --- the port default ---------------------------------------------------------


class _DefaultPlugin(ProviderPluginBase[PluginSettings]):
    """A provider that overrides nothing — the inherited discovery defaults."""

    custom_llm_provider = "probe"

    def register_models(self) -> list[ModelEntry]:
        return []


def test_a_provider_declares_no_source_for_any_mode_by_default() -> None:
    base = _DefaultPlugin()

    assert base.chat_discovery_source(model=_MODEL) is None
    assert base.chat_discovery_source(model=_MODEL, auth_type="api_key") is None
    assert base.chat_discovery_source(model=_MODEL, auth_type="oauth") is None


@pytest.mark.asyncio
async def test_the_default_fetch_hook_reports_no_attempt_for_any_mode() -> None:
    base = _DefaultPlugin()

    assert (
        await base.discover_chat_parameter_snapshot(
            model=_MODEL, client=_NeverCalledClient(), auth_type="api_key"
        )
        is None
    )
