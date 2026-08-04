from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings
from .db import close_db, init_db
from .portal import register_portal
from .routes import health, leaderboard, scores
from .scores.baseline_store import BaselineStore
from .scores.store import ScoreStore

# WHY read directly from os.environ, not a Settings field: this is uvicorn's own env var
# (FORWARDED_ALLOW_IPS, no SCOREBOARD_ prefix — see charts/scoreboard/values.yaml's
# config.forwardedAllowIps), read by uvicorn.Config itself in cli.py's uvicorn.run(), never
# by this app. Checking it here is purely a startup sanity guard, not a config source.
# AIDEV-NOTE: not discoverable from Settings' field docstrings for the same reason — if you're
# auditing "what must be configured correctly for cloudflare_headers mode" and only read
# config.py, you will miss this. See Settings.auth_mode's docstring for a pointer back here.
_FORWARDED_ALLOW_IPS_ENV = "FORWARDED_ALLOW_IPS"
# Mirrors uvicorn.config.Config's own fallback (os.environ.get("FORWARDED_ALLOW_IPS",
# "127.0.0.1")) — pinned by test_header_mode_starts_with_unset_forwarded_allow_ips against the
# installed uvicorn version, so a future uvicorn upgrade that changes its default breaks a test
# here rather than silently drifting.
_UVICORN_DEFAULT_FORWARDED_ALLOW_IPS = "127.0.0.1"


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_db(app.state.settings.database_url)
    try:
        yield
    finally:
        await close_db()


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = Settings()

    # WHY at construction, not left to peer_in_networks' own fail-closed default: this service
    # trusts X-User-Email BECAUSE only declared networks may present it, so a deployment that
    # forgets to set SCOREBOARD_ALLOWED_NETWORKS should fail loudly at startup, not silently
    # 403 every submission in production and leave an operator debugging a "broken" service
    # that is actually just unconfigured (mirrors aigateway's create_app of the same name).
    if settings.auth_mode == "cloudflare_headers" and not settings.allowed_networks:
        raise ValueError(
            "SCOREBOARD_AUTH_MODE=cloudflare_headers requires SCOREBOARD_ALLOWED_NETWORKS to be "
            "set — this service cannot trust X-User-Email without knowing which peers may "
            "present it."
        )

    # WHY: peer_in_networks() trusts request.client.host as the real TCP peer. Uvicorn's
    # ProxyHeadersMiddleware (always on by default) overwrites that value from a
    # client-supplied X-Forwarded-For whenever FORWARDED_ALLOW_IPS matches the peer — and "*"
    # matches every peer, no proxy relationship required. Confirmed by reproduction: with
    # FORWARDED_ALLOW_IPS=* an attacker who can merely reach this port at all (no relation to
    # the real reverse proxy) can forge X-Forwarded-For to satisfy allowed_networks and ride
    # straight through to a forged X-User-Email. "*" is the value apps/scoreboard's chart sets
    # by default for the Traefik-fronted deployment (DEPLOYMENT.md) — safe there because that
    # deployment doesn't use cloudflare_headers mode, but never safe combined with it.
    # INVARIANT: cloudflare_headers mode and FORWARDED_ALLOW_IPS="*" must never both hold.
    # AIDEV-NOTE: this exact-string check ("*") is pinned to uvicorn's ACTUAL (undocumented,
    # private) `_TrustedHosts.always_trust` logic, verified against the installed version —
    # not part of uvicorn's public contract. No test here exercises uvicorn's real
    # ProxyHeadersMiddleware directly; test_allowed_networks.py only asserts on this
    # function's own ValueError. A future uvicorn upgrade that changes how it decides "trust
    # everyone" (e.g. any-entry-is-"*" in a list) could silently reopen this bypass without
    # any test failing. Also: this only inspects the env var uvicorn falls back to — an
    # explicit `--forwarded-allow-ips`/`Config(forwarded_allow_ips=...)` override at the
    # invocation site would bypass this guard entirely. Neither gap applies to this app's
    # actual startup path today (cli.py's uvicorn.run() passes neither), so both are
    # documented limitations, not fixed here.
    if settings.auth_mode == "cloudflare_headers":
        forwarded_allow_ips = os.environ.get(
            _FORWARDED_ALLOW_IPS_ENV, _UVICORN_DEFAULT_FORWARDED_ALLOW_IPS
        ).strip()
        if forwarded_allow_ips == "*":
            raise ValueError(
                f"SCOREBOARD_AUTH_MODE=cloudflare_headers conflicts with "
                f"{_FORWARDED_ALLOW_IPS_ENV}='*' — uvicorn would trust a client-supplied "
                "X-Forwarded-For from ANY peer and overwrite request.client.host, defeating "
                "peer_in_networks() entirely. Scope FORWARDED_ALLOW_IPS to the real reverse "
                "proxy's address(es) before enabling this auth mode."
            )

    app = FastAPI(title="scoreboard", version="0.1.1", lifespan=_lifespan)
    app.state.settings = settings
    app.state.score_store = ScoreStore()
    app.state.baseline_store = BaselineStore()

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(health.router)
    app.include_router(leaderboard.router)
    app.include_router(scores.router)
    register_portal(app, settings)
    return app


app = create_app()
