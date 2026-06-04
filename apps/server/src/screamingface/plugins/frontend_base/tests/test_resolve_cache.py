"""Tests for the non-blocking url4 resolve path (WI-3 / SF-237).

Three fixes are pinned here:

1. **Negative cache** — a failed/timed-out resolve is remembered for a short
   TTL so subsequent requests don't re-run the (5-minute) ensemble until it
   expires.
2. **Non-blocking hot path** — ``get_cached_context()`` returns immediately
   (cached text or ``None``); it never blocks the chat on resolution. A cold
   read schedules a single background warm.
3. **Loop-aware, pool-free fetch** — ``_fetch_sync`` bounds the resolve with
   ``asyncio.wait_for`` (cancelling the in-flight request on timeout → raises
   ``TimeoutError``) while surfacing a real upstream error as-is. It never
   submits to ``_RESOLVE_POOL`` and works both with and without an already
   running event loop in the calling thread.
4. **No warm self-starvation** — concurrent warms on separate plugin instances
   resolve independently and quickly, because warms don't nest pool tasks.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import ClassVar

import pytest

from screamingface.plugins.claude_frontend._url4_context import resolve_static_context
from screamingface.plugins.frontend_base.plugin_base import (
    FrontendPluginBase,
    FrontendSettingsBase,
)


class _ConcreteFrontend(FrontendPluginBase):
    name = "test-frontend"
    settings_class = FrontendSettingsBase


def _make_plugin(
    *,
    spec_urls: list[tuple[str, str]],
    resolve_failure_ttl: float = 60.0,
    resolve_timeout: float = 300.0,
) -> _ConcreteFrontend:
    plugin = _ConcreteFrontend()
    plugin.settings = FrontendSettingsBase(
        resolve_failure_ttl=resolve_failure_ttl,
        resolve_timeout=resolve_timeout,
    )
    # Pin the active spec set; avoids touching config/disk.
    plugin._get_spec_urls = lambda: list(spec_urls)  # type: ignore[method-assign]
    return plugin


# ---------------------------------------------------------------------------
# (1) Negative cache
# ---------------------------------------------------------------------------


def test_negative_cache_suppresses_repeat_resolve() -> None:
    plugin = _make_plugin(spec_urls=[("spec-a", "(https://x)!'y'")])

    calls = {"n": 0}

    def _boom(_expr: str, _timeout: float) -> str:
        calls["n"] += 1
        raise RuntimeError("ensemble exploded")

    plugin._fetch_sync = _boom  # type: ignore[method-assign]

    assert plugin.resolve_context() is None
    assert plugin.resolve_context() is None  # second call must be suppressed
    assert calls["n"] == 1


def test_negative_cache_retries_after_ttl() -> None:
    plugin = _make_plugin(
        spec_urls=[("spec-a", "(https://x)!'y'")],
        resolve_failure_ttl=0.05,
    )

    calls = {"n": 0}

    def _boom(_expr: str, _timeout: float) -> str:
        calls["n"] += 1
        raise RuntimeError("ensemble exploded")

    plugin._fetch_sync = _boom  # type: ignore[method-assign]

    assert plugin.resolve_context() is None
    time.sleep(0.1)  # past the TTL
    assert plugin.resolve_context() is None
    assert calls["n"] == 2


def test_success_clears_negative_cache() -> None:
    plugin = _make_plugin(spec_urls=[("spec-a", "(https://x)!'y'")])

    def _ok(_expr: str, _timeout: float) -> str:
        return "resolved text"

    plugin._fetch_sync = _ok  # type: ignore[method-assign]

    assert plugin.resolve_context() == "resolved text"
    assert "spec-a" not in plugin._neg_cache


# ---------------------------------------------------------------------------
# (2) Non-blocking hot path
# ---------------------------------------------------------------------------


def test_get_cached_context_returns_cached_without_blocking() -> None:
    plugin = _make_plugin(spec_urls=[("spec-a", "(https://x)!'y'")])
    plugin._resolved_context = "warm context"
    plugin._active_key = "spec-a"

    start = time.monotonic()
    assert plugin.get_cached_context() == "warm context"
    assert time.monotonic() - start < 0.5


def test_get_cached_context_cold_returns_none_and_warms() -> None:
    plugin = _make_plugin(spec_urls=[("spec-a", "(https://x)!'y'")])

    entered = threading.Event()
    release = threading.Event()

    def _slow(_expr: str, _timeout: float) -> str:
        entered.set()
        # Block the warm so we can assert get_cached_context didn't wait on it.
        release.wait(timeout=5)
        return "eventually"

    plugin._fetch_sync = _slow  # type: ignore[method-assign]

    start = time.monotonic()
    result = plugin.get_cached_context()
    elapsed = time.monotonic() - start

    assert result is None
    assert elapsed < 1.0  # must not block on the 5s fetch
    # A background warm was scheduled and is running the fetch.
    assert entered.wait(timeout=2)
    assert plugin._warming is True
    release.set()


def test_get_cached_context_none_when_no_specs() -> None:
    plugin = _make_plugin(spec_urls=[])
    assert plugin.get_cached_context() is None


def test_get_cached_context_skips_prompt_specs() -> None:
    plugin = _make_plugin(spec_urls=[("spec-p", "(https://x)!$prompt")])
    assert plugin.get_cached_context() is None
    assert plugin._warming is False  # nothing warmable → no warm scheduled


# ---------------------------------------------------------------------------
# (3) Bounded / cancellable _fetch_sync
# ---------------------------------------------------------------------------


def test_fetch_sync_times_out() -> None:
    plugin = _make_plugin(spec_urls=[("spec-a", "(https://x)!'y'")])

    import screamingface.plugins.frontend_base.plugin_base as mod

    async def _slow_fetch(_base: str, _expr: str) -> str:
        await asyncio.sleep(5)
        return "never"

    original = mod._fetch
    mod._fetch = _slow_fetch  # type: ignore[assignment]
    plugin._get_backend_url = lambda: "http://localhost:8000"  # type: ignore[method-assign]
    try:
        with pytest.raises(TimeoutError):
            plugin._fetch_sync("(https://x)!'y'", timeout=0.2)
    finally:
        mod._fetch = original  # type: ignore[assignment]


def test_fetch_sync_surfaces_upstream_error() -> None:
    plugin = _make_plugin(spec_urls=[("spec-a", "(https://x)!'y'")])

    import screamingface.plugins.frontend_base.plugin_base as mod

    class _UpstreamError(RuntimeError):
        pass

    async def _err_fetch(_base: str, _expr: str) -> str:
        raise _UpstreamError("ensemble 502")

    original = mod._fetch
    mod._fetch = _err_fetch  # type: ignore[assignment]
    plugin._get_backend_url = lambda: "http://localhost:8000"  # type: ignore[method-assign]
    try:
        with pytest.raises(_UpstreamError, match="ensemble 502"):
            plugin._fetch_sync("(https://x)!'y'", timeout=5)
    finally:
        mod._fetch = original  # type: ignore[assignment]


def test_fetch_sync_works_inside_running_loop() -> None:
    """BLOCKER 2: ``_fetch_sync`` must work when a loop is already running.

    codex/gemini/ollama call ``resolve_context`` (→ ``_fetch_sync``)
    synchronously from inside their ``async def`` proxy handler, i.e. with the
    uvicorn loop already running in the same thread. A bare ``asyncio.run`` in
    ``_fetch_sync`` would raise ``RuntimeError: cannot be called from a running
    event loop``; the loop-detection branch must offload to a private thread.
    """
    plugin = _make_plugin(spec_urls=[("spec-a", "(https://x)!'y'")])

    import screamingface.plugins.frontend_base.plugin_base as mod

    async def _ok_fetch(_base: str, _expr: str) -> str:
        return "resolved inside loop"

    original = mod._fetch
    mod._fetch = _ok_fetch  # type: ignore[assignment]
    plugin._get_backend_url = lambda: "http://localhost:8000"  # type: ignore[method-assign]

    async def _call_from_loop() -> str:
        # Sanity-check the precondition: a loop really is running in this thread.
        asyncio.get_running_loop()
        return plugin._fetch_sync("(https://x)!'y'", timeout=5)

    try:
        result = asyncio.run(_call_from_loop())
    finally:
        mod._fetch = original  # type: ignore[assignment]

    assert result == "resolved inside loop"


# ---------------------------------------------------------------------------
# (3b) Concurrent warms must not self-starve (BLOCKER 1)
# ---------------------------------------------------------------------------


def test_concurrent_warms_do_not_starve() -> None:
    """BLOCKER 1: two warms on separate plugins must both resolve fast.

    The old ``_fetch_sync`` re-submitted to the SAME ``max_workers=2``
    ``_RESOLVE_POOL`` and blocked on the nested future. Two concurrent warms
    then occupied both workers while their nested fetches had nowhere to run,
    so both stalled for the full ``resolve_timeout``. With ``_fetch_sync`` off
    the pool, both warms complete in well under the timeout.
    """
    import screamingface.plugins.frontend_base.plugin_base as mod

    async def _fast_fetch(_base: str, _expr: str) -> str:
        return "resolved fast"

    original = mod._fetch
    mod._fetch = _fast_fetch  # type: ignore[assignment]

    # Small resolve_timeout: if a warm ever stalled on pool starvation it would
    # block for this long; the poll below (~3s) is the real assertion budget.
    plugins = []
    for i in range(2):
        p = _make_plugin(
            spec_urls=[(f"spec-{i}", f"(https://x{i})!'y'")],
            resolve_timeout=10.0,
        )
        p._get_backend_url = lambda: "http://localhost:8000"  # type: ignore[method-assign]
        plugins.append(p)

    try:
        # Fire both warms concurrently via the real background-warm path.
        for p in plugins:
            p._maybe_warm()

        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if all(p._resolved_context is not None for p in plugins):
                break
            time.sleep(0.01)
    finally:
        mod._fetch = original  # type: ignore[assignment]

    for i, p in enumerate(plugins):
        assert p._resolved_context == "resolved fast", (
            f"plugin {i} did not warm in time (self-starvation regression?)"
        )
        # Warm flag cleared once resolution completed.
        assert p._warming is False


# ---------------------------------------------------------------------------
# (4) Hot-path call site (resolve_static_context)
# ---------------------------------------------------------------------------


class _FakeSettings:
    active_spec = "spec-a"
    embed_target = "system"
    embed_mode = "concat"


class _FakeCachedPlugin:
    blocking_called: ClassVar[bool] = False

    def __init__(self, cached: str | None) -> None:
        self._cached = cached

    def get_cached_context(self) -> str | None:
        return self._cached

    def resolve_context(self) -> str | None:
        type(self).blocking_called = True
        raise AssertionError("hot path must not call the blocking resolve_context")


def test_resolve_static_context_none_proceeds() -> None:
    embedded: list[str] = []

    result = resolve_static_context(
        {"model": "m"},
        raw_expression="(https://x)!'y'",
        settings=_FakeSettings(),
        plugin=_FakeCachedPlugin(None),
        embed_context=lambda _b, text, _s: embedded.append(text),
    )

    assert result is None
    assert embedded == []
    assert _FakeCachedPlugin.blocking_called is False


def test_resolve_static_context_embeds_cached() -> None:
    embedded: list[str] = []

    result = resolve_static_context(
        {"model": "m"},
        raw_expression="(https://x)!'y'",
        settings=_FakeSettings(),
        plugin=_FakeCachedPlugin("cached docs"),
        embed_context=lambda _b, text, _s: embedded.append(text),
    )

    assert result is None
    assert embedded == ["cached docs"]
