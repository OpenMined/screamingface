"""Tests for the blocking + fail-loud url4 resolve path (SF-237).

Three behaviors are pinned here:

1. **Blocking + fail-loud** — ``resolve_context()`` blocks on the resolve and
   **re-raises** on failure (timeout, ``/ensemble`` 5xx, …) instead of
   swallowing it, so the caller can surface a visible error.
2. **Negative cache (fail-fast)** — a failed/timed-out resolve is remembered for
   a short TTL; a repeat within the TTL re-raises immediately **without**
   re-running the (potentially long) ensemble. After the TTL it retries.
3. **Loop-aware, pool-free fetch** — ``_fetch_sync`` bounds the resolve with
   ``asyncio.wait_for`` (cancelling the in-flight request on timeout → raises
   ``TimeoutError``) while surfacing a real upstream error as-is. It works both
   with and without an already running event loop in the calling thread.
"""

from __future__ import annotations

import asyncio
import time

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
# (1) Blocking + fail-loud + (2) negative cache fail-fast
# ---------------------------------------------------------------------------


def test_resolve_failure_raises_and_neg_caches() -> None:
    """A failing fetch makes ``resolve_context`` RAISE and neg-cache the spec;
    a second call within the TTL re-raises WITHOUT re-running the fetch."""
    plugin = _make_plugin(spec_urls=[("spec-a", "(https://x)!'y'")])

    calls = {"n": 0}

    def _boom(_expr: str, _timeout: float) -> str:
        calls["n"] += 1
        raise RuntimeError("ensemble exploded")

    plugin._fetch_sync = _boom  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="ensemble exploded"):
        plugin.resolve_context()
    assert "spec-a" in plugin._neg_cache

    # Second call within TTL fails fast — no re-run of _fetch_sync.
    with pytest.raises(RuntimeError, match="failed recently"):
        plugin.resolve_context()
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

    with pytest.raises(RuntimeError, match="ensemble exploded"):
        plugin.resolve_context()
    time.sleep(0.1)  # past the TTL
    with pytest.raises(RuntimeError, match="ensemble exploded"):
        plugin.resolve_context()
    assert calls["n"] == 2  # retried (not fail-fast) after the TTL


def test_success_clears_negative_cache() -> None:
    plugin = _make_plugin(spec_urls=[("spec-a", "(https://x)!'y'")])

    def _ok(_expr: str, _timeout: float) -> str:
        return "resolved text"

    plugin._fetch_sync = _ok  # type: ignore[method-assign]

    assert plugin.resolve_context() == "resolved text"
    assert "spec-a" not in plugin._neg_cache


def test_resolve_context_none_when_no_specs() -> None:
    plugin = _make_plugin(spec_urls=[])
    assert plugin.resolve_context() is None


def test_resolve_context_skips_prompt_specs() -> None:
    plugin = _make_plugin(spec_urls=[("spec-p", "(https://x)!$prompt")])
    assert plugin.resolve_context() is None


# ---------------------------------------------------------------------------
# (3) Bounded / cancellable _fetch_sync
# ---------------------------------------------------------------------------


def test_fetch_sync_times_out() -> None:
    plugin = _make_plugin(spec_urls=[("spec-a", "(https://x)!'y'")])

    import screamingface.plugins.frontend_base.plugin_base as mod

    async def _slow_fetch(_base: str, _expr: str, _timeout: float) -> str:
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

    async def _err_fetch(_base: str, _expr: str, _timeout: float) -> str:
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
    """``_fetch_sync`` must work when a loop is already running.

    codex/gemini/ollama call ``resolve_context`` (→ ``_fetch_sync``)
    synchronously from inside their ``async def`` proxy handler, i.e. with the
    uvicorn loop already running in the same thread. A bare ``asyncio.run`` in
    ``_fetch_sync`` would raise ``RuntimeError: cannot be called from a running
    event loop``; the loop-detection branch must offload to a private thread.
    """
    plugin = _make_plugin(spec_urls=[("spec-a", "(https://x)!'y'")])

    import screamingface.plugins.frontend_base.plugin_base as mod

    async def _ok_fetch(_base: str, _expr: str, _timeout: float) -> str:
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
# (4) Hot-path call site (resolve_static_context) — blocking + screaming
# ---------------------------------------------------------------------------


class _FakeSettings:
    active_spec = "spec-a"
    embed_target = "system"
    embed_mode = "concat"


class _FakeBlockingPlugin:
    def __init__(self, context: str | None) -> None:
        self._context = context

    def resolve_context(self) -> str | None:
        return self._context


def test_resolve_static_context_none_proceeds() -> None:
    embedded: list[str] = []

    result = resolve_static_context(
        {"model": "m"},
        raw_expression="(https://x)!'y'",
        settings=_FakeSettings(),
        plugin=_FakeBlockingPlugin(None),
        embed_context=lambda _b, text, _s: embedded.append(text),
    )

    assert result is None
    assert embedded == []


def test_resolve_static_context_embeds_resolved() -> None:
    embedded: list[str] = []

    result = resolve_static_context(
        {"model": "m"},
        raw_expression="(https://x)!'y'",
        settings=_FakeSettings(),
        plugin=_FakeBlockingPlugin("cached docs"),
        embed_context=lambda _b, text, _s: embedded.append(text),
    )

    assert result is None
    assert embedded == ["cached docs"]
