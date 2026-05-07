from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import Settings
from .core.bootstrap import bootstrap_from_claude_code
from .core.credential_store import JsonFileCredentialStore
from .core.loader import load_plugins
from .core.pending_auth import PendingAuthTable
from .core.profile_index import ProfileIndexStore
from .core.registry import ProviderRegistry
from .routes import auth, chat, health, models

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app):
    # Auto-import of the developer's Claude Code keychain entry is opt-in.
    # By default the gateway boots with an empty profile index so the user
    # explicitly authenticates via the UI rather than seeing a "default"
    # profile they never OAuthed for. Set
    # AIGATEWAY_BOOTSTRAP_FROM_CLAUDE_CODE=1 to restore the legacy import.
    #
    # When the fake-keychain test hook is active, bootstrap (if enabled)
    # uses the same fake store so it cannot pull in the developer's real
    # Claude Code credentials behind the test's back.
    if os.getenv("AIGATEWAY_BOOTSTRAP_FROM_CLAUDE_CODE") == "1":
        fake_store = getattr(app.state, "_fake_credential_store", None)
        try:
            if fake_store is not None:
                await bootstrap_from_claude_code(
                    credential_store=fake_store, index_store=app.state.profile_index
                )
            else:
                await bootstrap_from_claude_code(index_store=app.state.profile_index)
        except Exception:
            logger.exception("bootstrap failed; gateway will start with empty index")
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = Settings()
    app = FastAPI(title="aigateway", version="0.1.0", lifespan=_lifespan)
    app.state.settings = settings

    registry = ProviderRegistry()
    load_plugins(registry)
    app.state.providers = registry

    # Test-only hooks (do not affect production behavior).
    # When AIGATEWAY_FAKE_KEYCHAIN=1 is set, swap the OS-keychain-backed
    # credential store for a JSON-file-backed one, and likewise install a
    # MockTransport-backed httpx factory for the Anthropic OAuth token
    # endpoint when AIGATEWAY_FAKE_ANTHROPIC_OAUTH=1. These are gated by
    # env vars so they only ever activate in the e2e test harness.
    if os.getenv("AIGATEWAY_FAKE_KEYCHAIN") == "1":
        kc_path = os.getenv("AIGATEWAY_KEYCHAIN_FILE")
        if not kc_path:
            raise RuntimeError("AIGATEWAY_FAKE_KEYCHAIN=1 requires AIGATEWAY_KEYCHAIN_FILE=<path>")
        fake_store = JsonFileCredentialStore(kc_path)
        app.state._fake_credential_store = fake_store
        app.state.profile_index = ProfileIndexStore(credential_store=fake_store)
    else:
        app.state.profile_index = ProfileIndexStore()

    if os.getenv("AIGATEWAY_FAKE_ANTHROPIC_OAUTH") == "1":
        import httpx

        fail_mode = os.getenv("AIGATEWAY_FAKE_ANTHROPIC_OAUTH_FAIL") == "1"

        def _fake_handler(req: httpx.Request) -> httpx.Response:
            if req.url.host == "console.anthropic.com" and req.url.path.endswith("/oauth/token"):
                if fail_mode:
                    return httpx.Response(400, json={"error": "invalid_grant"})
                return httpx.Response(
                    200,
                    json={
                        "access_token": "fake-tok",
                        "refresh_token": "fake-rt",
                        "expires_in": 3600,
                        "token_type": "Bearer",
                    },
                )
            return httpx.Response(404, json={"error": "unmapped"})

        def _factory() -> httpx.AsyncClient:
            return httpx.AsyncClient(
                transport=httpx.MockTransport(_fake_handler),
                timeout=httpx.Timeout(30.0),
            )

        app.state.anthropic_http_factory = _factory

    app.state.pending_auth = PendingAuthTable(ttl_seconds=600)

    for plugin in registry.all():
        auth_router = plugin.auth_router()
        if auth_router is not None:
            app.include_router(auth_router, prefix=f"/v1/auth/{plugin.custom_llm_provider}")

    app.include_router(auth.router)
    app.include_router(health.router)
    app.include_router(models.router)
    app.include_router(chat.router)

    logger.info("aigateway ready (port=%d, providers=%d)", settings.port, len(registry.all()))
    return app


app = create_app()
