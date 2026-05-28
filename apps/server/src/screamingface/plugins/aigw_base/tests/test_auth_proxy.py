"""Unit tests for the aigw auth-proxy router factory.

We mount the factory's router on a bare FastAPI app and use httpx
MockTransport to fake the upstream aigateway. Each test asserts that
the SF-side route forwards correctly and reshapes errors as documented
in docs/superpowers/specs/2026-05-07-aigw-backend-oauth-authenticate-button-design.md.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.plugins.aigw_base.auth_proxy_router import (
    build_aigw_auth_proxy_router,
)


def _make_client(handler, *, defaults=None, bridge=None) -> TestClient:
    """Mount the auth-proxy router onto a stub app, with a MockTransport gateway."""
    transport = httpx.MockTransport(handler)

    def http_factory(timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport, timeout=timeout)

    app = FastAPI()
    router_app = None
    if bridge is not None:
        app.state.aigw_callback_bridge = bridge
        app.state.config = SimpleNamespace(
            plugin_config={"aigw-base": {"mode": "local_managed", "gateway_url": "http://gateway"}}
        )
        router_app = app
    app.include_router(
        build_aigw_auth_proxy_router(
            path_prefix="/claude",
            gateway_url="http://gateway",
            gateway_provider="anthropic",
            profile_name="default",
            http_client_factory=http_factory,
            app=router_app,
            defaults=defaults,
        )
    )
    return TestClient(app)


class _RecordingBridge:
    def __init__(self, redirect_uri: str | None = "http://localhost:9105/callback") -> None:
        self.redirect_uri = redirect_uri
        self.prepared: list[str] = []
        self.registered: list[dict[str, str]] = []
        self.released: list[str] = []

    async def prepare_redirect_uri(self, *, gateway_provider: str) -> str | None:
        self.prepared.append(gateway_provider)
        return self.redirect_uri

    def register_state(self, *, state: str, gateway_provider: str, redirect_uri: str) -> None:
        self.registered.append(
            {"state": state, "gateway_provider": gateway_provider, "redirect_uri": redirect_uri}
        )

    def release_redirect_uri(self, redirect_uri: str) -> None:
        self.released.append(redirect_uri)


class _FailingBridge(_RecordingBridge):
    async def prepare_redirect_uri(self, *, gateway_provider: str) -> str | None:
        self.prepared.append(gateway_provider)
        raise OSError("busy")


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
    assert resp.status_code == 201
    body = resp.json()
    assert body["authorize_url"] == "https://provider/authorize?x=1"
    assert body["profile_id"] == "anthropic:default"
    assert body["state"] == "abc"
    assert body["expires_in"] == 600
    # Verify the SF route forwarded to the right gateway endpoint
    assert captured["url"] == "http://gateway/v1/auth/anthropic/profiles"
    assert captured["body"] == {"name": "default"}


def test_start_with_disabled_bridge_keeps_gateway_body_unchanged() -> None:
    captured: dict = {}
    bridge = _RecordingBridge(redirect_uri=None)

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.read().decode())
        return httpx.Response(
            201,
            json={
                "profile_id": "anthropic:default",
                "authorize_url": "https://provider/authorize?x=1",
                "state": "abc",
            },
        )

    client = _make_client(handler, bridge=bridge)
    resp = client.post("/claude/auth/start")

    assert resp.status_code == 201
    assert captured["body"] == {"name": "default"}
    assert bridge.prepared == ["anthropic"]
    assert bridge.registered == []


def test_start_with_bridge_sends_redirect_uri_and_registers_state() -> None:
    captured: dict = {}
    bridge = _RecordingBridge()

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["body"] = json.loads(req.read().decode())
        return httpx.Response(
            201,
            json={
                "profile_id": "anthropic:default",
                "authorize_url": "https://provider/authorize?x=1",
                "state": "abc",
            },
        )

    client = _make_client(handler, bridge=bridge)
    resp = client.post("/claude/auth/start")

    assert resp.status_code == 201
    assert captured["url"] == "http://gateway/v1/auth/anthropic/profiles"
    assert captured["body"] == {
        "name": "default",
        "redirect_uri": "http://localhost:9105/callback",
    }
    assert bridge.registered == [
        {
            "state": "abc",
            "gateway_provider": "anthropic",
            "redirect_uri": "http://localhost:9105/callback",
        }
    ]
    assert bridge.released == []


def test_start_bridge_prepare_failure_becomes_503() -> None:
    bridge = _FailingBridge()

    def handler(_req: httpx.Request) -> httpx.Response:
        raise AssertionError("gateway should not be called")

    client = _make_client(handler, bridge=bridge)
    resp = client.post("/claude/auth/start")

    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "oauth_callback_unavailable"
    assert bridge.prepared == ["anthropic"]


def test_start_gateway_failure_releases_bridge_redirect_uri() -> None:
    bridge = _RecordingBridge()

    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"code": "bad_start"})

    client = _make_client(handler, bridge=bridge)
    resp = client.post("/claude/auth/start")

    assert resp.status_code == 400
    assert bridge.released == ["http://localhost:9105/callback"]
    assert bridge.registered == []


def test_start_rejects_missing_desktop_secret_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("SF_DESKTOP_SECRET", "test-secret")

    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"profile_id": "anthropic:default"})

    client = _make_client(handler)

    missing = client.post("/claude/auth/start")
    allowed = client.post("/claude/auth/start", headers={"X-SF-Desktop-Secret": "test-secret"})

    assert missing.status_code == 401
    assert allowed.status_code == 201


def test_profiles_rejects_missing_desktop_secret_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("SF_DESKTOP_SECRET", "test-secret")

    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"profiles": []})

    client = _make_client(handler)

    missing = client.get("/claude/auth/profiles")
    allowed = client.get("/claude/auth/profiles", headers={"X-SF-Desktop-Secret": "test-secret"})

    assert missing.status_code == 401
    assert allowed.status_code == 200


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
    assert resp.status_code == 201
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
    assert resp.status_code == 201
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
    assert resp.status_code == 201
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
    assert resp.status_code == 201
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
    assert resp.status_code == 201
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


def test_list_connections_filters_gateway_provider() -> None:
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        return httpx.Response(200, json={"connections": []})

    client = _make_client(handler)
    resp = client.get("/claude/auth/connections")

    assert resp.status_code == 200
    assert resp.json() == {"connections": []}
    assert captured["url"] == "http://gateway/v1/oauth/connections?provider=anthropic"


def test_start_connection_forwards_provider_and_label() -> None:
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["body"] = json.loads(req.read().decode())
        return httpx.Response(
            201,
            json={
                "connection_id": "00000000-0000-0000-0000-000000000001",
                "authorize_url": "https://provider/authorize?x=1",
                "state": "abc",
                "expires_in": 600,
            },
        )

    client = _make_client(handler)
    resp = client.post("/claude/auth/connections", json={"label": "work-anthropic"})

    assert resp.status_code == 201
    assert resp.json()["connection_id"] == "00000000-0000-0000-0000-000000000001"
    assert captured["url"] == "http://gateway/v1/oauth/connections"
    assert captured["body"] == {"provider": "anthropic", "label": "work-anthropic"}


def test_start_connection_with_bridge_sends_redirect_uri_and_registers_state() -> None:
    captured: dict = {}
    bridge = _RecordingBridge()

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["body"] = json.loads(req.read().decode())
        return httpx.Response(
            201,
            json={
                "connection_id": "00000000-0000-0000-0000-000000000001",
                "authorize_url": "https://provider/authorize?x=1",
                "state": "connection-state",
                "expires_in": 600,
            },
        )

    client = _make_client(handler, bridge=bridge)
    resp = client.post("/claude/auth/connections", json={"label": "work-anthropic"})

    assert resp.status_code == 201
    assert captured["url"] == "http://gateway/v1/oauth/connections"
    assert captured["body"] == {
        "provider": "anthropic",
        "label": "work-anthropic",
        "redirect_uri": "http://localhost:9105/callback",
    }
    assert bridge.registered == [
        {
            "state": "connection-state",
            "gateway_provider": "anthropic",
            "redirect_uri": "http://localhost:9105/callback",
        }
    ]


def test_start_connection_gateway_failure_releases_bridge_redirect_uri() -> None:
    bridge = _RecordingBridge()

    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"code": "label_conflict"})

    client = _make_client(handler, bridge=bridge)
    resp = client.post("/claude/auth/connections", json={"label": "work-anthropic"})

    assert resp.status_code == 409
    assert bridge.released == ["http://localhost:9105/callback"]
    assert bridge.registered == []


def test_start_connection_omits_empty_label() -> None:
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.read().decode())
        return httpx.Response(
            201,
            json={
                "connection_id": "00000000-0000-0000-0000-000000000001",
                "authorize_url": "https://provider/authorize?x=1",
                "state": "abc",
            },
        )

    client = _make_client(handler)
    resp = client.post("/claude/auth/connections", json={})

    assert resp.status_code == 201
    assert captured["body"] == {"provider": "anthropic"}


def test_get_connection_passes_through_duplicate_flag() -> None:
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        return httpx.Response(
            200,
            json={
                "id": "00000000-0000-0000-0000-000000000001",
                "provider": "anthropic",
                "label": "work-anthropic",
                "status": "active",
                "is_duplicate": True,
            },
        )

    client = _make_client(handler)
    resp = client.get("/claude/auth/connections/00000000-0000-0000-0000-000000000002")

    assert resp.status_code == 200
    assert resp.json()["is_duplicate"] is True
    assert (
        captured["url"]
        == "http://gateway/v1/oauth/connections/00000000-0000-0000-0000-000000000002"
    )


def test_get_connection_provider_mismatch_returns_404() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "00000000-0000-0000-0000-000000000001",
                "provider": "codex",
                "label": "work-codex",
                "status": "active",
            },
        )

    client = _make_client(handler)
    resp = client.get("/claude/auth/connections/00000000-0000-0000-0000-000000000001")

    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "connection_not_found"


def test_delete_connection_happy_path() -> None:
    captured: dict = {"requests": []}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["requests"].append((req.method, str(req.url)))
        if req.method == "GET":
            return httpx.Response(
                200,
                json={
                    "id": "00000000-0000-0000-0000-000000000001",
                    "provider": "anthropic",
                    "label": "work-anthropic",
                    "status": "active",
                },
            )
        return httpx.Response(204)

    client = _make_client(handler)
    resp = client.delete("/claude/auth/connections/00000000-0000-0000-0000-000000000001")

    assert resp.status_code == 204
    assert captured["requests"] == [
        ("GET", "http://gateway/v1/oauth/connections/00000000-0000-0000-0000-000000000001"),
        ("DELETE", "http://gateway/v1/oauth/connections/00000000-0000-0000-0000-000000000001"),
    ]


def test_delete_connection_provider_mismatch_returns_404_without_delete() -> None:
    captured: dict = {"requests": []}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["requests"].append((req.method, str(req.url)))
        return httpx.Response(
            200,
            json={
                "id": "00000000-0000-0000-0000-000000000001",
                "provider": "codex",
                "label": "work-codex",
                "status": "active",
            },
        )

    client = _make_client(handler)
    resp = client.delete("/claude/auth/connections/00000000-0000-0000-0000-000000000001")

    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "connection_not_found"
    assert captured["requests"] == [
        ("GET", "http://gateway/v1/oauth/connections/00000000-0000-0000-0000-000000000001")
    ]


def test_delete_connection_unexpected_success_status_passes_through() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "GET":
            return httpx.Response(
                200,
                json={
                    "id": "00000000-0000-0000-0000-000000000001",
                    "provider": "anthropic",
                    "label": "work-anthropic",
                    "status": "active",
                },
            )
        return httpx.Response(200)

    client = _make_client(handler)
    resp = client.delete("/claude/auth/connections/00000000-0000-0000-0000-000000000001")

    assert resp.status_code == 200


def test_refresh_connection_passes_through() -> None:
    captured: dict = {"requests": []}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["requests"].append((req.method, str(req.url)))
        return httpx.Response(
            200,
            json={
                "id": "00000000-0000-0000-0000-000000000001",
                "provider": "anthropic",
                "label": "work-anthropic",
                "status": "active",
            },
        )

    client = _make_client(handler)
    resp = client.post("/claude/auth/connections/00000000-0000-0000-0000-000000000001/refresh")

    assert resp.status_code == 200
    assert resp.json()["id"] == "00000000-0000-0000-0000-000000000001"
    assert captured["requests"] == [
        ("GET", "http://gateway/v1/oauth/connections/00000000-0000-0000-0000-000000000001"),
        (
            "POST",
            "http://gateway/v1/oauth/connections/00000000-0000-0000-0000-000000000001/refresh",
        ),
    ]


def test_refresh_connection_provider_mismatch_returns_404_without_refresh() -> None:
    captured: dict = {"requests": []}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["requests"].append((req.method, str(req.url)))
        return httpx.Response(
            200,
            json={
                "id": "00000000-0000-0000-0000-000000000001",
                "provider": "codex",
                "label": "work-codex",
                "status": "active",
            },
        )

    client = _make_client(handler)
    resp = client.post("/claude/auth/connections/00000000-0000-0000-0000-000000000001/refresh")

    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "connection_not_found"
    assert captured["requests"] == [
        ("GET", "http://gateway/v1/oauth/connections/00000000-0000-0000-0000-000000000001")
    ]


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
