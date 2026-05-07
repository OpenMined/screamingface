"""Unit tests for the aigw auth-proxy router factory.

We mount the factory's router on a bare FastAPI app and use httpx
MockTransport to fake the upstream aigateway. Each test asserts that
the SF-side route forwards correctly and reshapes errors as documented
in docs/superpowers/specs/2026-05-07-aigw-backend-oauth-authenticate-button-design.md.
"""

from __future__ import annotations

import json

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.plugins.aigw_base.auth_proxy_router import (
    build_aigw_auth_proxy_router,
)


def _make_client(handler, *, defaults=None) -> TestClient:
    """Mount the auth-proxy router onto a stub app, with a MockTransport gateway."""
    transport = httpx.MockTransport(handler)

    def http_factory(timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport, timeout=timeout)

    app = FastAPI()
    app.include_router(
        build_aigw_auth_proxy_router(
            path_prefix="/claude",
            gateway_url="http://gateway",
            gateway_provider="anthropic",
            profile_name="default",
            http_client_factory=http_factory,
            defaults=defaults,
        )
    )
    return TestClient(app)


def test_start_happy_path_passes_through_authorize_url() -> None:
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["body"] = json.loads(req.read().decode())
        return httpx.Response(
            201,
            json={
                "profile_id": "anthropic:default",
                "authorize_url": "https://provider/authorize?x=1",
                "state": "abc",
                "expires_in": 600,
            },
        )

    client = _make_client(handler)
    resp = client.post("/claude/auth/start")
    assert resp.status_code == 200
    body = resp.json()
    assert body["authorize_url"] == "https://provider/authorize?x=1"
    assert body["profile_id"] == "anthropic:default"
    assert body["state"] == "abc"
    assert body["expires_in"] == 600
    # Verify the SF route forwarded to the right gateway endpoint
    assert captured["url"] == "http://gateway/v1/auth/anthropic/profiles"
    assert captured["body"] == {"name": "default"}


def test_start_gateway_5xx_becomes_502() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "down"})

    client = _make_client(handler)
    resp = client.post("/claude/auth/start")
    assert resp.status_code == 502
    body = resp.json()
    assert body["detail"]["code"] == "gateway_error"
    assert body["detail"]["upstream_status"] == 503


def test_start_gateway_unreachable_becomes_502() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=req)

    client = _make_client(handler)
    resp = client.post("/claude/auth/start")
    assert resp.status_code == 502
    body = resp.json()
    assert body["detail"]["code"] == "gateway_unreachable"
    assert "connection refused" in body["detail"]["message"].lower()


def test_start_gateway_4xx_passes_through() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"code": "unknown_provider", "provider": "anthropic"})

    client = _make_client(handler)
    resp = client.post("/claude/auth/start")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "unknown_provider"


def test_status_happy_path_passes_through() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        assert str(req.url) == "http://gateway/v1/auth/anthropic/profiles/default/status"
        return httpx.Response(
            200,
            json={
                "state": "authenticated",
                "account_label": None,
                "last_refreshed_at": "2026-05-07T10:00:00+00:00",
            },
        )

    client = _make_client(handler)
    resp = client.get("/claude/auth/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "authenticated"
    assert body["last_refreshed_at"] == "2026-05-07T10:00:00+00:00"


def test_status_gateway_404_passes_through() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"code": "profile_not_found"})

    client = _make_client(handler)
    resp = client.get("/claude/auth/status")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "profile_not_found"


def test_start_omits_defaults_when_none() -> None:
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.read().decode())
        return httpx.Response(201, json={"profile_id": "anthropic:default"})

    client = _make_client(handler)  # defaults defaults to None
    resp = client.post("/claude/auth/start")
    assert resp.status_code == 200
    assert captured["body"] == {"name": "default"}
    assert "defaults" not in captured["body"]


def test_start_forwards_defaults_when_provided() -> None:
    captured: dict = {}
    defaults = {
        "model": "anthropic/claude-sonnet-4-5",
        "system_prompt": "Be concise.",
        "timeout_seconds": 300,
        "reasoning_effort": "medium",
    }

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.read().decode())
        return httpx.Response(201, json={"profile_id": "anthropic:default"})

    client = _make_client(handler, defaults=defaults)
    resp = client.post("/claude/auth/start")
    assert resp.status_code == 200
    assert captured["body"] == {"name": "default", "defaults": defaults}


def test_status_gateway_unreachable_becomes_502() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=req)

    client = _make_client(handler)
    resp = client.get("/claude/auth/status")
    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "gateway_unreachable"


def test_profiles_happy_path_returns_list() -> None:
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        return httpx.Response(
            200,
            json={
                "profiles": [
                    {
                        "id": "anthropic:default",
                        "name": "default",
                        "state": "authenticated",
                    }
                ]
            },
        )

    client = _make_client(handler)
    resp = client.get("/claude/auth/profiles")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "profiles": [
            {
                "id": "anthropic:default",
                "name": "default",
                "state": "authenticated",
            }
        ]
    }
    assert captured["url"] == "http://gateway/v1/auth/anthropic/profiles"


def test_profiles_gateway_5xx_becomes_502() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "down"})

    client = _make_client(handler)
    resp = client.get("/claude/auth/profiles")
    assert resp.status_code == 502
    body = resp.json()
    assert body["detail"]["code"] == "gateway_error"
    assert body["detail"]["upstream_status"] == 503


def test_profiles_gateway_unreachable_becomes_502() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=req)

    client = _make_client(handler)
    resp = client.get("/claude/auth/profiles")
    assert resp.status_code == 502
    body = resp.json()
    assert body["detail"]["code"] == "gateway_unreachable"
    assert "connection refused" in body["detail"]["message"].lower()


def test_start_with_name_override_targets_named_profile() -> None:
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.read().decode())
        return httpx.Response(
            201,
            json={
                "profile_id": "anthropic:work",
                "authorize_url": "https://x",
                "state": "s",
                "expires_in": 600,
            },
        )

    client = _make_client(handler, defaults={"model": "anthropic/claude-sonnet-4-5"})
    resp = client.post("/claude/auth/start?name=work")
    assert resp.status_code == 200
    # Named profile bypasses defaults forwarding
    assert captured["body"] == {"name": "work"}


def test_start_default_name_forwards_defaults() -> None:
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.read().decode())
        return httpx.Response(
            201,
            json={
                "profile_id": "anthropic:default",
                "authorize_url": "https://x",
                "state": "s",
                "expires_in": 600,
            },
        )

    client = _make_client(handler, defaults={"model": "anthropic/claude-sonnet-4-5"})
    resp = client.post("/claude/auth/start")  # no ?name → uses default "default"
    assert resp.status_code == 200
    assert captured["body"] == {
        "name": "default",
        "defaults": {"model": "anthropic/claude-sonnet-4-5"},
    }


def test_start_explicit_default_name_forwards_defaults() -> None:
    """When client passes ?name=default (the SF-configured default), defaults still apply."""
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.read().decode())
        return httpx.Response(
            201,
            json={
                "profile_id": "anthropic:default",
                "authorize_url": "https://x",
                "state": "s",
                "expires_in": 600,
            },
        )

    client = _make_client(handler, defaults={"model": "anthropic/claude-sonnet-4-5"})
    resp = client.post("/claude/auth/start?name=default")
    assert resp.status_code == 200
    assert captured["body"] == {
        "name": "default",
        "defaults": {"model": "anthropic/claude-sonnet-4-5"},
    }


def test_status_with_name_override_targets_named_profile() -> None:
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        return httpx.Response(200, json={"state": "authenticated"})

    client = _make_client(handler)
    resp = client.get("/claude/auth/status?name=work")
    assert resp.status_code == 200
    assert "/v1/auth/anthropic/profiles/work/status" in captured["url"]


def test_delete_profile_happy_path() -> None:
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["method"] = req.method
        captured["url"] = str(req.url)
        return httpx.Response(204)

    client = _make_client(handler)
    resp = client.delete("/claude/auth/profiles/work")
    assert resp.status_code == 204
    assert captured["method"] == "DELETE"
    assert captured["url"] == "http://gateway/v1/auth/anthropic/profiles/work"


def test_delete_profile_404_passes_through() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"code": "profile_not_found"})

    client = _make_client(handler)
    resp = client.delete("/claude/auth/profiles/missing")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "profile_not_found"


def test_exchange_code_happy_path_forwards_to_gateway() -> None:
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["method"] = req.method
        captured["body"] = json.loads(req.read().decode())
        return httpx.Response(200, json={"state": "authenticated"})

    client = _make_client(handler)
    resp = client.post("/claude/auth/exchange-code", json={"code": "pasted-code", "state": "abc"})
    assert resp.status_code == 200
    assert resp.json() == {"state": "authenticated"}
    assert captured["method"] == "POST"
    assert captured["url"] == "http://gateway/v1/auth/anthropic/exchange-code"
    assert captured["body"] == {"code": "pasted-code", "state": "abc"}


def test_exchange_code_gateway_4xx_passes_through() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"code": "unknown_state"})

    client = _make_client(handler)
    resp = client.post("/claude/auth/exchange-code", json={"code": "x", "state": "never-issued"})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "unknown_state"


def test_exchange_code_gateway_unreachable_becomes_502() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=req)

    client = _make_client(handler)
    resp = client.post("/claude/auth/exchange-code", json={"code": "x", "state": "y"})
    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "gateway_unreachable"


def test_delete_profile_gateway_unreachable_becomes_502() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=req)

    client = _make_client(handler)
    resp = client.delete("/claude/auth/profiles/anything")
    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "gateway_unreachable"
