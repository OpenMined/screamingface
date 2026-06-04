"""Shared :class:`FrontendPluginBase` for transparent-proxy frontends.

Every ``*_frontend`` plugin (claude, codex, gemini, ollama) ran ~300
lines of nearly-identical bookkeeping: spec resolution + caching, a
side-spawned FastAPI server, lifecycle hooks. The only real
differences are: plugin metadata, settings defaults, the CLI binary
name to check at preflight, and the per-provider router factory.

This base concentrates the shared behavior and asks each subclass for
those four hooks. Each frontend plugin shrinks to ~50 lines.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import socket
import threading
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, ClassVar, Literal

import httpx
import uvicorn
from fastapi import FastAPI
from pydantic import Field
from pydantic_settings import SettingsConfigDict

from screamingface.plugin import Plugin, PluginSettings

if TYPE_CHECKING:
    from collections.abc import Callable

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry

logger = logging.getLogger(__name__)


class FrontendSettingsBase(PluginSettings):
    """Base settings shared by every transparent-proxy frontend plugin.

    Subclasses only need to override:
    - ``model_config.env_prefix`` (e.g. ``"SF_CLAUDE_FRONTEND__"``)
    - ``upstream_url`` default
    - ``listen_port`` default
    - ``default_backend_path`` default

    Everything else is shared.
    """

    model_config = SettingsConfigDict(
        env_prefix="SF_FRONTEND__",
        env_nested_delimiter="__",
    )

    active_spec: str | None = Field(
        default=None,
        description="Active url4-spec to resolve and prepend as context.",
    )
    upstream_url: str = "https://example.com"
    listen_host: str = "127.0.0.1"
    listen_port: int = 9100
    session_service_url: str | None = Field(
        default=None,
        description="URL of the session service. Enables session persistence.",
    )
    backend_url: str | None = Field(
        default=None,
        description=(
            "SF server URL used for $prompt substitution — stores user text "
            "on /data and resolves url4 expressions via /ensemble. "
            "Set automatically in per-session mode."
        ),
    )
    default_backend_path: str = Field(
        default="/claude",
        description="Default backend path for ensemble fan-out.",
    )
    resolve_timeout: float = Field(
        default=1200.0,
        description="Max seconds to wait for url4 spec resolution on first request.",
    )
    resolve_failure_ttl: float = Field(
        default=60.0,
        description="seconds to suppress re-resolving a spec after a failure",
    )
    embed_target: Literal["system", "user"] = Field(
        default="user",
        description="Where to inject url4-resolved context: 'system' or 'user'.",
    )
    embed_mode: Literal["concat", "replace"] = Field(
        default="concat",
        description="How to embed in user message: 'concat' or 'replace'.",
    )
    system_prompt: str = Field(
        default=(
            "You are a helpful assistant. Answer the user's question based only on "
            "the provided context. Be concise and factual."
        ),
        description="System prompt prepended to resolved context when embed_target='system'.",
    )


class FrontendPluginBase(Plugin):
    """Shared lifecycle for transparent-proxy frontend plugins.

    Subclasses must declare:

    - The standard :class:`Plugin` class attrs (``name``, ``description``,
      ``tags``, ``depends``, ``settings_class``).
    - ``cli_binary``: the CLI binary name to look up at preflight, or
      ``None`` to skip the check.
    - ``cli_install_hint``: text appended to the preflight error message
      when ``cli_binary`` is missing.
    - ``app_title``: title for the spawned FastAPI app (mostly cosmetic).
    - ``create_router``: a static-method-style callable returning the
      provider's :class:`fastapi.APIRouter`. Signature
      ``(settings, app, plugin, hooks)`` matches the existing factories.
    """

    cli_binary: ClassVar[str | None] = None
    cli_install_hint: ClassVar[str] = ""
    app_title: ClassVar[str] = "frontend"
    create_router: ClassVar[Callable[..., Any]]

    def __init__(self) -> None:
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._cache: dict[str, str] = {}  # spec_name → resolved text
        self._resolved_context: str | None = None
        self._active_key: str | None = None  # tracks which specs produced the cache
        self._neg_cache: dict[str, float] = {}  # spec_name → monotonic expiry
        self._lock = threading.Lock()
        self._app: Any = None

    # ------------------------------------------------------------------
    # Schema customization
    # ------------------------------------------------------------------

    def _current_spec_expressions(self) -> dict[str, str]:
        """Current ``{name: expression}`` for url4-specs.

        Merges two sources so a spec is visible no matter how it was added,
        with the **running in-memory config winning** on name conflicts:

        - In-memory ``url4-specs`` plugin ``.settings`` — authoritative for
          this process. It reflects the config the server actually booted
          with (which may be supplied inline via ``--config-json``, with no
          file on disk) and is updated live by ``POST /plugins/url4-specs/
          settings``.
        - A fresh on-disk ``load_config()`` read — *supplements* names the
          running config doesn't have, catching a spec added by editing
          ``sf.json`` directly without going through the settings endpoint.

        A blind disk-first read is wrong: ``load_config()`` reads ``./sf.json``
        relative to cwd, which is NOT necessarily the config the server booted
        with — so it can shadow the real running specs with an unrelated file.
        """
        out: dict[str, str] = {}

        try:
            from screamingface.core.config import load_config

            raw = load_config().plugin_config.get("url4-specs") or {}
            specs = raw.get("specs")
            if isinstance(specs, dict):
                for name, spec in specs.items():
                    expr = spec.get("expression") if isinstance(spec, dict) else None
                    if expr:
                        out[name] = expr
        except Exception:
            logger.debug("Fresh url4-specs config unavailable; using in-memory", exc_info=True)

        specs_plugin = (
            self._app.state.plugins.active_plugins.get("url4-specs") if self._app else None
        )
        if specs_plugin and specs_plugin.settings:
            for name, spec in specs_plugin.settings.specs.items():
                if spec.expression:
                    out[name] = spec.expression

        return out

    def _get_spec_names(self) -> list[str] | None:
        names = list(self._current_spec_expressions().keys())
        return names or None

    def customize_schema(self, schema: dict) -> dict:
        props = schema.get("properties", {})
        spec_names = self._get_spec_names()
        if spec_names and "active_spec" in props:
            props["active_spec"]["enum"] = spec_names
        return schema

    # ------------------------------------------------------------------
    # Preflight
    # ------------------------------------------------------------------

    def preflight(self) -> tuple[bool, str]:
        # Skip the CLI check in test subprocesses (ServerManager sets this).
        # The proxy itself doesn't need the CLI — the check exists to
        # prevent a confusing runtime for end-users who haven't installed it.
        if os.environ.get("_SF_SUBPROCESS"):
            return True, ""
        if self.cli_binary and not shutil.which(self.cli_binary):
            return (
                False,
                f"{self.cli_binary} CLI not found in PATH. {self.cli_install_hint}".strip(),
            )
        return True, ""

    # ------------------------------------------------------------------
    # Spec resolution
    # ------------------------------------------------------------------

    def _collect_spec_names(self) -> list[str]:
        """Return the active spec as a single-element list, or empty."""
        settings: FrontendSettingsBase = self.settings  # type: ignore[assignment]
        if settings.active_spec:
            return [settings.active_spec]
        return []

    def _get_spec_urls(self) -> list[tuple[str, str]]:
        """Get (name, expression_url) pairs for active specs."""
        spec_names = self._collect_spec_names()
        if not spec_names:
            return []
        current = self._current_spec_expressions()
        result: list[tuple[str, str]] = []
        for name in spec_names:
            expr = current.get(name)
            if expr:
                result.append((name, expr))
        return result

    def get_active_expression(self) -> str | None:
        """Return the raw URL4 expression for the active spec, without resolving it."""
        spec_urls = self._get_spec_urls()
        if not spec_urls:
            return None
        return spec_urls[0][1]

    def resolve_context(self) -> str | None:
        """Resolve active specs lazily, **blocking** until done or failed.

        Cache hit (same spec set) returns cached text; cache miss
        fetches via :meth:`_fetch_sync` and stores. Specs containing
        ``$prompt`` are skipped — they need per-request substitution
        in the proxy.

        Fail-loud: if a spec resolve raises (timeout, ``/ensemble`` 5xx,
        …) the failure is negative-cached for ``resolve_failure_ttl`` and
        then **re-raised** so the caller can surface a visible error. A
        repeat call within the TTL re-raises immediately (fail-fast)
        instead of re-running the ensemble.

        Blocking: this monopolizes the calling session's event loop for up
        to ``resolve_timeout`` (default 1200s) while resolving — intentional
        for the single-client, per-session proxy model where each session
        serves one client and nothing else needs that loop meanwhile.
        """
        spec_urls = self._get_spec_urls()
        spec_urls = [(n, e) for n, e in spec_urls if "$prompt" not in e]
        if not spec_urls:
            return None

        active_key = ",".join(name for name, _ in spec_urls)
        if self._active_key == active_key and self._resolved_context is not None:
            return self._resolved_context

        with self._lock:
            if self._active_key == active_key and self._resolved_context is not None:
                return self._resolved_context

            settings: FrontendSettingsBase = self.settings  # type: ignore[assignment]
            timeout = settings.resolve_timeout
            resolved_parts: list[str] = []

            for name, url in spec_urls:
                if name in self._cache:
                    resolved_parts.append(self._cache[name])
                    logger.info("Cache hit for spec %r (%d chars)", name, len(self._cache[name]))
                    continue
                # Negative cache: a recent failure/timeout fails fast — re-raise
                # immediately instead of re-running the (potentially long)
                # ensemble until the TTL expires.
                neg_expiry = self._neg_cache.get(name)
                if neg_expiry is not None and time.monotonic() < neg_expiry:
                    cooldown = neg_expiry - time.monotonic()
                    logger.info("Negative-cache hit for spec %r; failing fast", name)
                    raise RuntimeError(
                        f"spec {name!r} resolution failed recently (cooldown {cooldown:.0f}s)"
                    )
                with _traced_resolve(name) as span:
                    try:
                        result = self._fetch_sync(url, timeout)
                        if result:
                            self._cache[name] = result
                            self._neg_cache.pop(name, None)
                            resolved_parts.append(result)
                            logger.info("Resolved spec %r (%d chars)", name, len(result))
                    except Exception as exc:
                        # Negative-cache the failure (so a repeat fails fast) and
                        # record it on the span for Phoenix, then re-raise so the
                        # caller surfaces a visible error in the CLI.
                        self._neg_cache[name] = time.monotonic() + settings.resolve_failure_ttl
                        logger.warning("Failed to resolve spec %r", name, exc_info=True)
                        _mark_span_error(span, exc, name)
                        raise

            if resolved_parts:
                self._resolved_context = "\n\n".join(resolved_parts)
                self._active_key = active_key
                logger.info(
                    "Cached %d chars of resolved url4 context",
                    len(self._resolved_context),
                )
            else:
                self._resolved_context = None
                self._active_key = active_key

            return self._resolved_context

    def _get_backend_url(self) -> str:
        """Return the base URL for backend/ensemble/data calls."""
        settings: FrontendSettingsBase = self.settings  # type: ignore[assignment]
        if settings.backend_url:
            return settings.backend_url.rstrip("/")
        cfg = getattr(self._app.state, "config", None) if self._app else None
        port = cfg.server.port if cfg else 8000
        use_ssl = cfg.server.ssl if cfg else False
        scheme = "https" if use_ssl else "http"
        return f"{scheme}://localhost:{port}"

    def _fetch_sync(self, expression: str, timeout: float) -> str:
        """Resolve a url4 expression by calling the /ensemble endpoint.

        Loop-aware and pool-free — it owns/borrows its own event loop and never
        leaks a thread.

        ``asyncio.wait_for(_fetch(...), timeout)`` bounds the resolve and cancels
        the in-flight httpx request on timeout. The inner :func:`_fetch` also
        gets ``timeout`` so its HTTP cap matches the resolve budget. Two
        execution paths:

        - **A loop is already running in THIS thread** — the production path.
          All four frontends call ``resolve_context`` synchronously from an
          ``async def`` proxy handler running on the event-loop thread, so a
          loop is already running and ``asyncio.run`` would raise. We therefore
          offload to a private throwaway thread with its own loop.
          ``Thread.join(timeout)`` plus the inner ``wait_for`` mean the worker
          exits within ``timeout`` — no leaked thread. A real upstream
          (non-timeout) error propagates as-is.
        - **No running loop** — a fallback for non-async callers (e.g. tests or
          a synchronous entrypoint): run the coroutine directly via
          ``asyncio.run``.
        """
        base = self._get_backend_url()

        async def _runner() -> str:
            return await asyncio.wait_for(_fetch(base, expression, timeout), timeout)

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # No running loop — own the loop directly.
            try:
                return asyncio.run(_runner())
            except TimeoutError as exc:
                raise TimeoutError(f"Spec resolution timed out after {timeout}s") from exc

        # A loop is already running in THIS thread. Offload to a private
        # throwaway thread with its own loop so ``asyncio.run`` is legal.
        box_r: list[str] = []
        box_e: list[BaseException] = []

        def _worker() -> None:
            try:
                box_r.append(asyncio.run(_runner()))
            except BaseException as e:  # noqa: BLE001 — surfaced to the caller below
                box_e.append(e)

        t = threading.Thread(target=_worker, name="url4-fetch", daemon=True)
        t.start()
        t.join(timeout=timeout + 1)  # inner asyncio.wait_for already enforces ``timeout``
        if box_e:
            exc = box_e[0]
            if isinstance(exc, asyncio.TimeoutError):
                raise TimeoutError(f"Spec resolution timed out after {timeout}s") from exc
            raise exc
        if not box_r:
            raise TimeoutError(f"Spec resolution timed out after {timeout}s")
        return box_r[0]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,  # noqa: ARG002 — required by Plugin contract
        routes: RouteRegistry,  # noqa: ARG002 — required by Plugin contract
    ) -> None:
        settings: FrontendSettingsBase = self.settings  # type: ignore[assignment]
        self._app = app

        is_session = bool(os.environ.get("_SF_SESSION_ID"))

        if is_session:
            frontend_app = FastAPI(title=self.app_title)
            router = type(self).create_router(settings, app, plugin=self, hooks=hooks)
            frontend_app.include_router(router)

            try:
                from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

                FastAPIInstrumentor.instrument_app(frontend_app)
            except ImportError:
                pass

            config = uvicorn.Config(
                frontend_app,
                host=settings.listen_host,
                port=settings.listen_port,
                log_level="info",
            )
            self._server = uvicorn.Server(config)
            self._thread = threading.Thread(
                target=self._run_server, daemon=True, name=self.app_title
            )
            self._thread.start()

            if not _wait_for_port(settings.listen_port, host=settings.listen_host):
                logger.warning("%s server may not be ready yet", self.app_title)

            logger.info(
                "%s listening on http://%s:%d",
                self.app_title,
                settings.listen_host,
                settings.listen_port,
            )
        else:
            logger.info("%s registered (proxy launches per-session only)", self.app_title)

        hooks.register("app.shutdown", self._on_shutdown, plugin_name=self.name)

    def _run_server(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._server.serve())  # type: ignore[union-attr]

    async def _on_shutdown(self) -> None:
        self._stop()

    def teardown(self) -> None:
        self._stop()

    def _stop(self) -> None:
        if self._server:
            self._server.should_exit = True
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._server = None
        self._thread = None


async def _fetch(base_url: str, expression: str, timeout: float) -> str:
    """Call /ensemble with a url4 expression and return plain text.

    ``timeout`` caps the inner HTTP request so it matches the resolve budget
    (``resolve_timeout``) rather than a hardcoded value.
    """
    async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
        resp = await client.get(f"{base_url}/ensemble", params={"q": expression})
        resp.raise_for_status()
        return resp.text


@contextmanager
def _traced_resolve(spec_name: str):  # type: ignore[no-untyped-def]
    """Span around static spec resolution so failures surface in Phoenix.

    Without this, a failed static-spec resolution was only logged and the
    proxy trace looked successful — leaving no error visible in the trace.
    Yields the span (or None when OpenTelemetry isn't installed).
    """
    try:
        from opentelemetry import trace
    except ImportError:
        yield None
        return
    tracer = trace.get_tracer("screamingface.frontend-base")
    with tracer.start_as_current_span("url4.static_resolve") as span:
        if span.is_recording():
            span.set_attribute("sf.plugin", "frontend-base")
            span.set_attribute("url4.spec", spec_name)
        yield span


def _mark_span_error(span: Any, exc: Exception, spec_name: str) -> None:
    """Record an exception + ERROR status on ``span`` (no-op without OTel)."""
    if span is None or not span.is_recording():
        return
    try:
        from opentelemetry.trace import Status, StatusCode

        span.set_attribute("url4.status", "error")
        span.set_attribute("url4.error", str(exc))
        span.set_attribute("url4.failed_spec", spec_name)
        span.record_exception(exc)
        span.set_status(Status(StatusCode.ERROR, str(exc)))
    except ImportError:
        pass


def _wait_for_port(port: int, host: str = "127.0.0.1", timeout: float = 5.0) -> bool:
    """Wait for a TCP port to be listening."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.1)
    return False


__all__ = ["FrontendPluginBase", "FrontendSettingsBase"]
