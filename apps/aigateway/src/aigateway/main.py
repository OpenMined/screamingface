from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import Settings
from .core.auth.bootstrap_admin import ensure_admin_account
from .core.auth.jwt_secret import get_or_create_jwt_secret
from .core.auth.log_filter import (
    RedactProvisioningTokenFilter,
    install_provisioning_token_redaction,
)
from .core.auth.middleware import ANONYMOUS_ACCOUNT_ID
from .core.bootstrap import bootstrap_from_claude_code
from .core.credential_store import JsonFileCredentialStore, get_credential_store
from .core.loader import load_plugins
from .core.pending_auth import PendingAuthTable
from .core.profile_index import ProfileIndexStore
from .core.registry import ProviderRegistry
from .db import close_db, init_db
from .routes import accounts, auth, auth_session, chat, health, models

logger = logging.getLogger(__name__)


def _attach_log_filter() -> None:
    install_provisioning_token_redaction()
    for name in ("", "uvicorn.access", "uvicorn.error", "aigateway"):
        target = logging.getLogger(name)
        if not any(isinstance(f, RedactProvisioningTokenFilter) for f in target.filters):
            target.addFilter(RedactProvisioningTokenFilter())
        for handler in target.handlers:
            if not any(isinstance(f, RedactProvisioningTokenFilter) for f in handler.filters):
                handler.addFilter(RedactProvisioningTokenFilter())


@asynccontextmanager
async def _lifespan(app):
    database_url = app.state.settings.database_url.get_secret_value()
    await init_db(database_url)
    try:
        fake_store = getattr(app.state, "_fake_credential_store", None)
        credential_store = fake_store if fake_store is not None else get_credential_store()
        app.state.jwt_secret = await get_or_create_jwt_secret(
            credential_store,
            app.state.settings.jwt_secret,
        )
        admin = await ensure_admin_account(app.state.settings.admin_password)
        bootstrap_account_id = (
            str(admin.id) if app.state.settings.auth_enabled else str(ANONYMOUS_ACCOUNT_ID)
        )

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
            if fake_store is not None:
                try:
                    await bootstrap_from_claude_code(
                        account_id=bootstrap_account_id,
                        credential_store=fake_store,
                        index_store=app.state.profile_index,
                    )
                except Exception:
                    logger.exception("bootstrap failed; gateway will start with empty index")
            else:
                try:
                    await bootstrap_from_claude_code(
                        account_id=bootstrap_account_id,
                        index_store=app.state.profile_index,
                    )
                except Exception:
                    logger.exception("bootstrap failed; gateway will start with empty index")
        yield
    finally:
        await close_db()


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = Settings()
    _attach_log_filter()
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
            if req.url.host in (
                "platform.claude.com",
                "console.anthropic.com",
            ) and req.url.path.endswith("/oauth/token"):
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

    app.include_router(auth_session.router)
    app.include_router(accounts.router)
    app.include_router(auth.router)
    app.include_router(health.router)
    app.include_router(models.router)
    app.include_router(chat.router)

    logger.info("aigateway ready (port=%d, providers=%d)", settings.port, len(registry.all()))
    return app


app = create_app()
