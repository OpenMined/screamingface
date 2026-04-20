"""Claude Frontend plugin — transparent proxy on a dedicated port.

Runs its own HTTP server so its routes (/v1/messages, /v1/*, /api/*) don't
clash with the main SF server or other frontend plugins.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import threading
import time
from typing import TYPE_CHECKING, Literal

import httpx
import uvicorn
from fastapi import FastAPI
from pydantic import Field
from pydantic_settings import SettingsConfigDict

from screamingface.plugin import Plugin, PluginSettings
from screamingface.plugins.claude_frontend.proxy import create_router

if TYPE_CHECKING:
    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry

logger = logging.getLogger(__name__)


class ClaudeFrontendSettings(PluginSettings):
    model_config = SettingsConfigDict(
        env_prefix="SF_CLAUDE_FRONTEND__",
        env_nested_delimiter="__",
    )
    active_spec: str | None = Field(
        default=None,
        description="Active url4-spec to resolve and prepend as system context.",
    )
    upstream_url: str = "https://api.anthropic.com"
    listen_host: str = "127.0.0.1"
    listen_port: int = 9101
    session_service_url: str | None = Field(
        default=None,
        description=(
            "URL of the session service (e.g. http://127.0.0.1:9200). Enables session persistence."
        ),
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
        description=(
            "Default backend path for ensemble fan-out (e.g. /claude). "
            "Used when resolving $prompt expressions through this frontend."
        ),
    )
    resolve_timeout: float = Field(
        default=300.0,
        description="Max seconds to wait for url4 spec resolution on first request.",
    )
    embed_target: Literal["system", "user"] = Field(
        default="user",
        description=(
            "Where to inject url4-resolved context: "
            "'system' (prepend to system prompt) or 'user' (inject into user message)."
        ),
    )
    embed_mode: Literal["concat", "replace"] = Field(
        default="concat",
        description=(
            "How to embed in user message: "
            "'concat' (original prompt + context) or 'replace' (context only). "
            "Only used when embed_target is 'user'."
        ),
    )
    system_prompt: str = Field(
        default=(
            "You are a helpful assistant. Answer the user's question based only on "
            "the provided context. Be concise and factual."
        ),
        description=(
            "System prompt prepended to the resolved context when embed_target is 'system'."
        ),
    )


class ClaudeFrontendPlugin(Plugin):
    name = "claude-frontend"
    description = "Transparent proxy between Claude Code and the Anthropic API"
    tags: list[str] = ["product:claude"]
    depends = ["url4-specs", "url4-executor"]
    settings_class = ClaudeFrontendSettings

    def __init__(self) -> None:
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._cache: dict[str, str] = {}  # spec_name → resolved text
        self._resolved_context: str | None = None
        self._active_key: str | None = None  # tracks which specs produced the cache
        self._lock = threading.Lock()

    def _get_spec_names(self) -> list[str] | None:
        if not hasattr(self, "_app") or not self._app:
            return None
        specs_plugin = self._app.state.plugins.active_plugins.get("url4-specs")
        if specs_plugin and specs_plugin.settings:
            names = list(specs_plugin.settings.specs.keys())
            if names:
                return names
        return None

    def customize_schema(self, schema: dict) -> dict:
        props = schema.get("properties", {})
        spec_names = self._get_spec_names()
        if spec_names and "active_spec" in props:
            props["active_spec"]["enum"] = spec_names
        return schema

    def preflight(self) -> tuple[bool, str]:
        import shutil

        # Skip the CLI check in test subprocesses (ServerManager sets this).
        # The proxy itself doesn't need the Claude CLI — the check exists to
        # prevent a confusing runtime for end-users who haven't installed it.
        if os.environ.get("_SF_SUBPROCESS"):
            return True, ""
        if not shutil.which("claude"):
            return False, (
                "Claude CLI not found in PATH. "
                "Install it from https://docs.anthropic.com/en/docs/claude-code"
            )
        return True, ""

    def _collect_spec_names(self) -> list[str]:
        """Return the active spec as a single-element list, or empty."""
        settings: ClaudeFrontendSettings = self.settings  # type: ignore[assignment]
        if settings.active_spec:
            return [settings.active_spec]
        return []

    def _get_spec_urls(self) -> list[tuple[str, str]]:
        """Get (name, expression_url) pairs for active specs."""
        spec_names = self._collect_spec_names()
        if not spec_names or not hasattr(self, "_app") or not self._app:
            return []

        specs_plugin = self._app.state.plugins.active_plugins.get("url4-specs")
        if not specs_plugin or not specs_plugin.settings:
            return []

        result: list[tuple[str, str]] = []
        for name in spec_names:
            spec = specs_plugin.settings.specs.get(name)
            if spec and spec.expression:
                result.append((name, spec.expression))
        return result

    def get_active_expression(self) -> str | None:
        """Return the raw URL4 expression for the active spec, without resolving it."""
        spec_urls = self._get_spec_urls()
        if not spec_urls:
            return None
        return spec_urls[0][1]

    def resolve_context(self) -> str | None:
        """Resolve active specs lazily. Called on first request.

        - Checks if current active specs match what's cached
        - If cache hit (same specs) → return cached
        - If cache miss (new/changed specs) → fetch, cache, return
        - Thread-safe via lock
        - Skips specs containing $prompt (handled by proxy_messages instead)
        """
        spec_urls = self._get_spec_urls()
        # Skip $prompt specs — they need per-request substitution in the proxy
        spec_urls = [(n, e) for n, e in spec_urls if "$prompt" not in e]
        if not spec_urls:
            return None

        # Build a cache key from the spec names
        active_key = ",".join(name for name, _ in spec_urls)

        # Fast path: already resolved for these exact specs
        if self._active_key == active_key and self._resolved_context is not None:
            return self._resolved_context

        with self._lock:
            # Double-check after acquiring lock
            if self._active_key == active_key and self._resolved_context is not None:
                return self._resolved_context

            settings: ClaudeFrontendSettings = self.settings  # type: ignore[assignment]
            timeout = settings.resolve_timeout
            resolved_parts: list[str] = []

            for name, url in spec_urls:
                # Check per-spec cache first
                if name in self._cache:
                    resolved_parts.append(self._cache[name])
                    logger.info("Cache hit for spec %r (%d chars)", name, len(self._cache[name]))
                    continue

                # Fetch and cache
                try:
                    result = self._fetch_sync(url, timeout)
                    if result:
                        self._cache[name] = result
                        resolved_parts.append(result)
                        logger.info("Resolved spec %r (%d chars)", name, len(result))
                except Exception:
                    logger.warning("Failed to resolve spec %r", name, exc_info=True)

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
        settings: ClaudeFrontendSettings = self.settings  # type: ignore[assignment]
        if settings.backend_url:
            return settings.backend_url.rstrip("/")
        # Fallback: same server (non-session mode)
        cfg = getattr(self._app.state, "config", None) if self._app else None
        port = cfg.server.port if cfg else 8000
        use_ssl = cfg.server.ssl if cfg else False
        scheme = "https" if use_ssl else "http"
        return f"{scheme}://localhost:{port}"

    def _fetch_sync(self, expression: str, timeout: float) -> str:
        """Resolve a url4 expression by calling the /ensemble endpoint."""
        base = self._get_backend_url()

        result_holder: list[str] = []

        def _run() -> None:
            loop = asyncio.new_event_loop()
            try:
                result_holder.append(loop.run_until_complete(_fetch(base, expression)))
            finally:
                loop.close()

        thread = threading.Thread(target=_run, name="url4-fetch", daemon=True)
        thread.start()
        thread.join(timeout=timeout)

        if not result_holder:
            raise TimeoutError(f"Spec resolution timed out after {timeout}s for {expression[:100]}")
        return result_holder[0]

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        settings: ClaudeFrontendSettings = self.settings  # type: ignore[assignment]
        self._app = app  # store for customize_schema and spec lookup

        # Only launch the proxy daemon thread in per-session mode.
        # In the main server the plugin stays active (for settings/discovery)
        # but doesn't bind a port — sessions spawn their own instances.
        is_session = bool(os.environ.get("_SF_SESSION_ID"))

        if is_session:
            # Build a standalone FastAPI app with proxy routes.
            # Pass `self` so the router can call resolve_context() lazily.
            frontend_app = FastAPI(title="claude-frontend")
            router = create_router(settings, app, plugin=self, hooks=hooks)
            frontend_app.include_router(router)

            # Instrument with OTEL if tracing extras are installed.
            try:
                from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

                FastAPIInstrumentor.instrument_app(frontend_app)
            except ImportError:
                pass

            # Start HTTP server in a background thread
            config = uvicorn.Config(
                frontend_app,
                host=settings.listen_host,
                port=settings.listen_port,
                log_level="info",
            )
            self._server = uvicorn.Server(config)
            self._thread = threading.Thread(
                target=self._run_server, daemon=True, name="claude-frontend"
            )
            self._thread.start()

            # Wait for the server to be listening before continuing
            if not _wait_for_port(settings.listen_port, host=settings.listen_host):
                logger.warning("claude-frontend server may not be ready yet")

            logger.info(
                "claude-frontend listening on http://%s:%d",
                settings.listen_host,
                settings.listen_port,
            )
        else:
            logger.info("claude-frontend registered (proxy launches per-session only)")

        # Clean up on shutdown
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


async def _fetch(base_url: str, expression: str) -> str:
    """Call the local /ensemble endpoint with a url4 expression and return plain text."""
    async with httpx.AsyncClient(timeout=300, verify=False) as client:
        resp = await client.get(f"{base_url}/ensemble", params={"q": expression})
        resp.raise_for_status()
        return resp.text


def _wait_for_port(port: int, host: str = "127.0.0.1", timeout: float = 5.0) -> bool:
    """Wait for a TCP port to be listening."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.1)
    return False
