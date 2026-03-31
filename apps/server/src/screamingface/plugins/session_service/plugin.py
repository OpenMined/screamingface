"""Session Service plugin — standalone microservice for conversation persistence.

Runs its own HTTP server on a dedicated port, providing REST API for
session CRUD and canonical message storage.
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
from screamingface.plugins.session_service.routes import create_router
from screamingface.plugins.session_service.store import FileSessionStore

if TYPE_CHECKING:
    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry

logger = logging.getLogger(__name__)


class SessionServiceSettings(PluginSettings):
    model_config = SettingsConfigDict(
        env_prefix="SF_SESSION_SERVICE__",
        env_nested_delimiter="__",
    )
    listen_host: str = "127.0.0.1"
    listen_port: int = 9200
    storage_dir: str = Field(
        default="~/.screamingface/sessions",
        description="Directory for JSONL session files.",
    )


class SessionServicePlugin(Plugin):
    name = "session-service"
    description = "Session persistence microservice — stores and retrieves conversation history"
    depends: list[str] = []
    settings_class = SessionServiceSettings

    def __init__(self) -> None:
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._store: FileSessionStore | None = None

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        settings: SessionServiceSettings = self.settings  # type: ignore[assignment]
        self._store = FileSessionStore(settings.storage_dir)

        service_app = FastAPI(title="session-service")
        router = create_router(self._store)
        service_app.include_router(router)

        # Instrument with OTEL if available
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            def _tag_plugin(span, scope):  # type: ignore[no-untyped-def]
                if span and span.is_recording():
                    span.set_attribute("sf.plugin", "session-service")

            FastAPIInstrumentor.instrument_app(
                service_app, server_request_hook=_tag_plugin
            )
        except ImportError:
            pass

        config = uvicorn.Config(
            service_app,
            host=settings.listen_host,
            port=settings.listen_port,
            log_level="info",
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(
            target=self._run_server, daemon=True, name="session-service"
        )
        self._thread.start()

        if not _wait_for_port(settings.listen_port, host=settings.listen_host):
            logger.warning("session-service server may not be ready yet")

        hooks.register("app.shutdown", self._on_shutdown, plugin_name=self.name)
        logger.info(
            "session-service listening on http://%s:%d (storage: %s)",
            settings.listen_host,
            settings.listen_port,
            settings.storage_dir,
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
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.1)
    return False
