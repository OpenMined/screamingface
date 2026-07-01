"""HF is API-key-only: the connection api-key proxy is the flow it actually uses.

The gateway mounts a provider OAuth router only when ``plugin.auth_router()`` is set,
and the HF provider has none — so ``/v1/auth/huggingface/*`` does not exist and the
OAuth-start proxy path is a dead end for HF. The real path is the provider-generic
api-key connection endpoint, which this asserts end to end (through the SF proxy).
"""

from __future__ import annotations

import json

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Route

from screamingface.plugins.aigw_base import auth_proxy_router as apr
from screamingface.plugins.aigw_huggingface_backend.plugin import (
    AigwHuggingfaceBackendPlugin,
    AigwHuggingfaceBackendSettings,
)

_HF_KEY = "hf_secret_token_1234567890"


def test_mounts_api_key_connection_routes() -> None:
    app = FastAPI()
    settings = AigwHuggingfaceBackendSettings()
    router = AigwHuggingfaceBackendPlugin.create_router(settings, app=app)
    app.include_router(router)

    routes = {
        (method, r.path)
        for r in app.routes
        if isinstance(r, Route)
        for method in (r.methods or set())
    }
    assert ("POST", "/huggingface/auth/connections/api-key") in routes
    assert ("GET", "/huggingface/auth/connections") in routes


def test_does_not_mount_dead_oauth_routes() -> None:
    # HF has no gateway OAuth surface (the provider exposes no auth_router), so all
    # OAuth routes would dead-end. Only the api-key connection CRUD is exposed —
    # which also drops the two OAuth-only connection routes the gateway rejects for
    # api-key providers (POST /connections starts an OAuth cycle; /refresh needs OAuth).
    app = FastAPI()
    settings = AigwHuggingfaceBackendSettings()
    router = AigwHuggingfaceBackendPlugin.create_router(settings, app=app)
    app.include_router(router)

    routes = {
        (method, r.path)
        for r in app.routes
        if isinstance(r, Route)
        for method in (r.methods or set())
    }
    paths = {path for _, path in routes}

    # Profile/OAuth-start proxy routes: not mounted.
    assert "/huggingface/auth/start" not in paths
    assert "/huggingface/auth/status" not in paths
    assert "/huggingface/auth/profiles" not in paths
    assert "/huggingface/auth/profiles/{name}" not in paths

    # OAuth-only connection routes: not mounted (gateway rejects them for HF).
    assert ("POST", "/huggingface/auth/connections") not in routes
    assert ("POST", "/huggingface/auth/connections/{connection_id}/refresh") not in routes

    # api-key connection CRUD: mounted.
    assert ("GET", "/huggingface/auth/connections") in routes
    assert ("GET", "/huggingface/auth/connections/{connection_id}") in routes
    assert ("DELETE", "/huggingface/auth/connections/{connection_id}") in routes
    assert ("POST", "/huggingface/auth/connections/api-key") in routes
    assert ("PUT", "/huggingface/auth/connections/{connection_id}/api-key") in routes


def test_create_api_key_connection_forwards_to_generic_gateway_endpoint() -> None:
    settings = AigwHuggingfaceBackendSettings()
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/v1/oauth/connections/api-key":
            captured["url"] = str(req.url)
            captured["body"] = json.loads(req.read().decode())
            return httpx.Response(
                201,
                json={
                    "id": "conn-1",
                    "provider": "huggingface",
                    "status": "active",
                    "auth_type": "api_key",
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

    def http_factory(timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport, timeout=timeout)

    original = apr._default_http_factory
    apr._default_http_factory = http_factory  # type: ignore[assignment]
    try:
        app = FastAPI()
        router = AigwHuggingfaceBackendPlugin.create_router(settings, app=app)
        app.include_router(router)
        response = TestClient(app).post(
            "/huggingface/auth/connections/api-key",
            json={"api_key": _HF_KEY, "label": "work"},
        )
        assert response.status_code == 201, response.text
    finally:
        apr._default_http_factory = original  # type: ignore[assignment]

    # Provider is injected server-side and forwarded to the generic gateway endpoint
    # (NOT /v1/auth/huggingface/*, which does not exist).
    assert captured["url"].endswith("/v1/oauth/connections/api-key")
    assert captured["body"]["provider"] == "huggingface"
    assert captured["body"]["api_key"] == _HF_KEY
    assert captured["body"]["label"] == "work"
    # The raw key is never echoed back in the SF response.
    assert _HF_KEY not in response.text
