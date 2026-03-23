"""Claude Frontend plugin — transparent proxy on a dedicated port.

Runs its own HTTP server so its routes (/v1/messages, /v1/*, /api/*) don't
clash with the main SF server or other frontend plugins.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import threading
import time
from typing import TYPE_CHECKING

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


class ClaudeFrontendPlugin(Plugin):
    name = "claude-frontend"
    description = "Transparent proxy between Claude Code and the Anthropic API"
    depends = ["url4-specs"]
    settings_class = ClaudeFrontendSettings

    def __init__(self) -> None:
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None

    def customize_schema(self, schema: dict) -> dict:
        props = schema.get("properties", {})
        # Populate active_spec enum from the url4-specs plugin
        if "active_spec" in props and hasattr(self, "_app") and self._app:
            specs_plugin = self._app.state.plugins.active_plugins.get("url4-specs")
            if specs_plugin and specs_plugin.settings:
                spec_names = list(specs_plugin.settings.specs.keys())
                if spec_names:
                    props["active_spec"]["enum"] = spec_names
        return schema

    def preflight(self) -> tuple[bool, str]:
        ok, reason = super().preflight()
        if not ok:
            return ok, reason
        import shutil

        if not shutil.which("claude"):
            return False, "Claude Code CLI not found in PATH"
        return True, ""

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        settings: ClaudeFrontendSettings = self.settings  # type: ignore[assignment]
        self._app = app  # store for customize_schema

        # Build a standalone FastAPI app with proxy routes
        frontend_app = FastAPI(title="claude-frontend")
        router = create_router(settings, app)
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

        # Clean up on shutdown
        hooks.register("app.shutdown", self._on_shutdown, plugin_name=self.name)
        logger.info(
            "claude-frontend listening on http://%s:%d",
            settings.listen_host,
            settings.listen_port,
        )

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


def _wait_for_port(port: int, host: str = "127.0.0.1", timeout: float = 5.0) -> bool:
    """Wait for a TCP port to be listening."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.1)
    return False
