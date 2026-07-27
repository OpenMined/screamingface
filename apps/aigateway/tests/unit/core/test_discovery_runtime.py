"""OME-627: the shared discovery runtime that feeds the DETAILED contract only.

RED-first for the seam that turns a provider's declared discovery source into a
cached snapshot plus the locked v1 ``freshness`` window (§6.2). The runtime owns
the bounded client, the observation cache and the wall clock; it takes no
credentials and builds no URL, so a caller can influence nothing but the model id
— which the route has already validated against the canonical inventory.

INVARIANT under test throughout: discovery is EVIDENCE. Nothing here enables a
parameter, and a failure degrades honestly rather than inventing an observation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from aigateway.core.chat_parameters import (
    ProviderDiscoverySnapshot,
    ProviderParameterObservation,
)
from aigateway.core.discovery_runtime import DiscoveryRuntime, static_discovery_outcome
from aigateway.core.parameter_discovery import (
    DiscoveryError,
    DiscoveryLimits,
    DiscoverySourceRef,
    RawResponse,
)
from aigateway.core.parameter_discovery_cache import CacheLimits, CacheOutcome, ObservationCache

_MODEL = "openrouter/google/gemini-3.6-flash"
_SOURCE = DiscoverySourceRef(source="stub:models", revision="stub:models:live")
_TTL_S = 900.0
_STALE_TTL_S = 3600.0
_EPOCH = datetime(2026, 7, 27, 12, 0, 0, tzinfo=UTC)


def _snapshot(path: str = "temperature") -> ProviderDiscoverySnapshot:
    return ProviderDiscoverySnapshot(
        source_revision=_SOURCE.revision,
        model_observations=(
            ProviderParameterObservation(request_path=path, support="supported", source="stub"),
        ),
    )


class _Clock:
    """Monotonic clock for the cache and wall clock for the runtime, advanced together."""

    def __init__(self) -> None:
        self._elapsed = 0.0

    def advance(self, seconds: float) -> None:
        self._elapsed += seconds

    def now(self) -> float:  # MonotonicClock
        return self._elapsed

    def utc(self) -> datetime:  # wall clock
        return _EPOCH + timedelta(seconds=self._elapsed)


class _NeverCalledClient:
    """A ``DiscoveryHttpClient`` that fails the test if discovery touches the network."""

    async def get(self, url: str, *, timeout_s: float, max_bytes: int) -> RawResponse:
        raise AssertionError(f"discovery must not have been attempted (url={url})")


class _StubPlugin:
    """Minimal provider double: declares a source, then answers the fetch hook."""

    def __init__(
        self,
        *,
        source: DiscoverySourceRef | None = _SOURCE,
        answers: list[Any] | None = None,
    ) -> None:
        self._source = source
        # Each entry is returned, or raised when it is an exception.
        self._answers = answers if answers is not None else [_snapshot()]
        self.attempts = 0
        self.fetch_kwargs: list[dict[str, Any]] = []

    def chat_discovery_source(self, *, model: str) -> DiscoverySourceRef | None:
        return self._source

    async def discover_chat_parameter_snapshot(
        self, *, model: str, client: Any, limits: DiscoveryLimits | None = None
    ) -> ProviderDiscoverySnapshot | None:
        self.attempts += 1
        self.fetch_kwargs.append({"model": model, "client": client, "limits": limits})
        answer = self._answers[min(self.attempts - 1, len(self._answers) - 1)]
        if isinstance(answer, BaseException):
            raise answer
        return answer


class _KeySpyCache:
    """Delegating cache that records the identity every lookup was made under."""

    def __init__(self, inner: ObservationCache) -> None:
        self._inner = inner
        self.lookups: list[tuple[str, str]] = []

    @property
    def limits(self) -> CacheLimits:
        return self._inner.limits

    async def get_or_refresh(self, key: str, *, revision: str, refresh: Any) -> CacheOutcome:
        self.lookups.append((key, revision))
        return await self._inner.get_or_refresh(key, revision=revision, refresh=refresh)


def _runtime(
    clock: _Clock, *, plugin_client: Any = None, cache: Any = None
) -> tuple[DiscoveryRuntime, _KeySpyCache]:
    spy = cache or _KeySpyCache(
        ObservationCache(
            clock=clock,
            limits=CacheLimits(ttl_s=_TTL_S, stale_ttl_s=_STALE_TTL_S, max_entries=8),
        )
    )
    runtime = DiscoveryRuntime(
        client=plugin_client if plugin_client is not None else _NeverCalledClient(),
        cache=spy,
        limits=DiscoveryLimits(timeout_s=1.5, max_bytes=2048),
        now_utc=clock.utc,
    )
    return runtime, spy


# --- no declared source: static evidence only --------------------------------


@pytest.mark.asyncio
async def test_no_declared_source_never_touches_the_cache_or_the_client() -> None:
    # A provider with no dynamic source is served entirely from its STATIC
    # observations; the runtime must not manufacture a cache entry for it.
    clock = _Clock()
    runtime, spy = _runtime(clock)
    plugin = _StubPlugin(source=None)

    outcome = await runtime.observe(plugin, model=_MODEL)

    assert plugin.attempts == 0
    assert spy.lookups == []
    assert outcome.snapshot is None
    assert outcome.freshness == static_discovery_outcome().freshness


def test_static_window_reports_never_observed_without_claiming_degradation() -> None:
    # WHY these exact values: null timestamps say "no dynamic evidence exists",
    # which is a different claim from "the dynamic evidence went bad" (degraded)
    # or "it aged out" (stale). Reporting degraded here would libel a provider
    # that never had a source to lose.
    assert static_discovery_outcome().freshness == {
        "observed_at": None,
        "expires_at": None,
        "stale": False,
        "degraded": False,
    }


def test_each_static_outcome_gets_its_own_freshness_mapping() -> None:
    # The document composer embeds this dict by reference; a shared constant
    # would let one response mutate another's contract.
    first = static_discovery_outcome().freshness
    first["stale"] = True
    assert static_discovery_outcome().freshness["stale"] is False


# --- cache identity ----------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_identity_carries_source_model_and_revision() -> None:
    # INVARIANT: evidence observed for one source/model/revision triple is never
    # served for another. The revision is known BEFORE the fetch precisely so the
    # cache can refuse a value produced under a different source identity.
    clock = _Clock()
    runtime, spy = _runtime(clock)

    await runtime.observe(_StubPlugin(), model=_MODEL)

    ((key, revision),) = spy.lookups
    assert revision == _SOURCE.revision
    for part in (_SOURCE.source, _MODEL, _SOURCE.revision):
        assert part in key
    # Distinct models under one source must not collide.
    await runtime.observe(_StubPlugin(), model="openrouter/other/model")
    assert spy.lookups[0][0] != spy.lookups[1][0]


# --- fresh / stale / degraded windows ----------------------------------------


@pytest.mark.asyncio
async def test_successful_fetch_reports_the_observation_and_its_expiry() -> None:
    clock = _Clock()
    runtime, _ = _runtime(clock)
    plugin = _StubPlugin()

    outcome = await runtime.observe(plugin, model=_MODEL)

    assert outcome.snapshot == _snapshot()
    assert outcome.freshness == {
        "observed_at": "2026-07-27T12:00:00Z",
        "expires_at": "2026-07-27T12:15:00Z",
        "stale": False,
        "degraded": False,
    }


@pytest.mark.asyncio
async def test_a_hit_inside_the_ttl_reuses_the_snapshot_and_its_original_window() -> None:
    # WHY the ORIGINAL instant: the window describes when the EVIDENCE was
    # observed, not when this request was served. Restamping it on every hit
    # would advertise a freshness the source never granted.
    clock = _Clock()
    runtime, _ = _runtime(clock)
    plugin = _StubPlugin()

    await runtime.observe(plugin, model=_MODEL)
    clock.advance(300.0)
    second = await runtime.observe(plugin, model=_MODEL)

    assert plugin.attempts == 1
    assert second.freshness["observed_at"] == "2026-07-27T12:00:00Z"
    assert second.freshness["expires_at"] == "2026-07-27T12:15:00Z"


@pytest.mark.asyncio
async def test_expiry_then_outage_serves_the_last_good_snapshot_as_stale() -> None:
    clock = _Clock()
    runtime, _ = _runtime(clock)
    plugin = _StubPlugin(answers=[_snapshot(), DiscoveryError("unreachable")])

    await runtime.observe(plugin, model=_MODEL)
    clock.advance(_TTL_S + 60.0)
    outcome = await runtime.observe(plugin, model=_MODEL)

    assert plugin.attempts == 2
    assert outcome.snapshot == _snapshot()  # last good, not invented
    assert outcome.freshness["stale"] is True
    assert outcome.freshness["degraded"] is False
    # Still the ORIGINAL observation instant — that is what makes it stale.
    assert outcome.freshness["observed_at"] == "2026-07-27T12:00:00Z"


@pytest.mark.asyncio
async def test_outage_past_the_stale_window_degrades_without_a_timestamp() -> None:
    # Fail-closed: no snapshot, and NO observation timestamp — a degraded contract
    # must not carry a window that implies evidence backs it.
    clock = _Clock()
    runtime, _ = _runtime(clock)
    plugin = _StubPlugin(answers=[_snapshot(), DiscoveryError("unreachable")])

    await runtime.observe(plugin, model=_MODEL)
    clock.advance(_TTL_S + _STALE_TTL_S + 1.0)
    outcome = await runtime.observe(plugin, model=_MODEL)

    assert outcome.snapshot is None
    assert outcome.freshness == {
        "observed_at": None,
        "expires_at": None,
        "stale": False,
        "degraded": True,
    }


@pytest.mark.asyncio
async def test_cold_source_failure_degrades_rather_than_reporting_fresh() -> None:
    clock = _Clock()
    runtime, _ = _runtime(clock)
    plugin = _StubPlugin(answers=[DiscoveryError("timeout")])

    outcome = await runtime.observe(plugin, model=_MODEL)

    assert outcome.snapshot is None
    assert outcome.freshness["degraded"] is True
    assert outcome.freshness["observed_at"] is None


@pytest.mark.asyncio
async def test_declared_source_that_reports_no_attempt_degrades() -> None:
    # A provider that declares a source and then answers NOT ATTEMPTED is
    # internally inconsistent. Storing that as a successful refresh would cache
    # "no evidence" under a fresh label and evict the last good snapshot, so the
    # runtime treats it as a failed attempt instead.
    clock = _Clock()
    runtime, _ = _runtime(clock)
    plugin = _StubPlugin(answers=[None])

    outcome = await runtime.observe(plugin, model=_MODEL)

    assert outcome.snapshot is None
    assert outcome.freshness["degraded"] is True


# --- what the runtime is allowed to pass downstream --------------------------


@pytest.mark.asyncio
async def test_the_provider_receives_only_the_model_and_the_runtime_bounds() -> None:
    # INVARIANT: no credential and no caller-built URL enter discovery. The model
    # is the ONLY caller-influenced input, and the route has already validated it
    # against the canonical inventory before this runs.
    clock = _Clock()
    client = _NeverCalledClient()
    runtime, _ = _runtime(clock, plugin_client=client)
    plugin = _StubPlugin()

    await runtime.observe(plugin, model=_MODEL)

    (call,) = plugin.fetch_kwargs
    assert set(call) == {"model", "client", "limits"}
    assert call["model"] == _MODEL
    assert call["client"] is client
    assert call["limits"] == DiscoveryLimits(timeout_s=1.5, max_bytes=2048)


@pytest.mark.asyncio
async def test_a_provider_defect_surfaces_instead_of_masquerading_as_degraded() -> None:
    # WHY: transport faults are already translated to DiscoveryError at the
    # adapter. Anything else is a bug, and swallowing it here would hide it
    # behind an indistinguishable "the source was unreachable" contract.
    clock = _Clock()
    runtime, _ = _runtime(clock)
    plugin = _StubPlugin(answers=[RuntimeError("plugin defect")])

    with pytest.raises(RuntimeError, match="plugin defect"):
        await runtime.observe(plugin, model=_MODEL)
