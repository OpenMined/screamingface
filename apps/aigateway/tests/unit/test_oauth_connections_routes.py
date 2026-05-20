from __future__ import annotations

import base64
import json
import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from aigateway.core.plugin_base import OAuthConfig
from aigateway.plugins.codex_provider.oauth_config import (
    CODEX_AUTHORIZE_EXTRA_PARAMS,
    CODEX_AUTHORIZE_URL,
    CODEX_CLIENT_ID,
    CODEX_REDIRECT_PATH,
    CODEX_SCOPES,
    CODEX_TOKEN_URL,
)


def _account_id(client) -> str:
    return client.get("/v1/auth/me").json()["id"]


def _jwt(payload: dict) -> str:
    def encode(value: dict | bytes) -> str:
        raw = value if isinstance(value, bytes) else json.dumps(value).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    return f"{encode({'alg': 'none', 'typ': 'JWT'})}.{encode(payload)}.{encode(b'sig')}"


def _anthropic_token_factory():
    transport = httpx.MockTransport(
        lambda _req: httpx.Response(
            200,
            json={
                "access_token": "anthropic-access",
                "refresh_token": "anthropic-refresh",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )
    )
    return lambda: httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(5.0))


def _codex_token_factory(email: str = "codex@example.com", sub: str = "codex-sub"):
    payload = {
        "sub": sub,
        "email": email,
        "name": "Codex User",
        "exp": int(time.time()) + 3600,
        "https://api.openai.com/auth": {"chatgpt_account_id": "acct-1"},
    }
    token = _jwt(payload)
    transport = httpx.MockTransport(
        lambda _req: httpx.Response(
            200,
            json={
                "access_token": token,
                "refresh_token": "codex-refresh",
                "id_token": token,
                "token_type": "Bearer",
            },
        )
    )
    return lambda: httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(5.0))


def _failing_token_factory():
    transport = httpx.MockTransport(
        lambda _req: httpx.Response(400, json={"error": "invalid_grant"})
    )
    return lambda: httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(5.0))


@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("GET", "/v1/oauth/connections", None),
        ("GET", "/v1/oauth/connections/00000000-0000-0000-0000-000000000001", None),
        ("POST", "/v1/oauth/connections", {"provider": "codex"}),
        ("PATCH", "/v1/oauth/connections/00000000-0000-0000-0000-000000000001", {"label": "x"}),
        ("DELETE", "/v1/oauth/connections/00000000-0000-0000-0000-000000000001", None),
        ("POST", "/v1/oauth/connections/00000000-0000-0000-0000-000000000001/refresh", None),
    ],
)
def test_oauth_connection_routes_require_jwt(client, method, path, json_body) -> None:
    resp = client.request(method, path, json=json_body)
    assert resp.status_code == 401


def test_anthropic_connection_requires_label(authenticated_client) -> None:
    resp = authenticated_client.post("/v1/oauth/connections", json={"provider": "anthropic"})
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "label_required"


def test_anthropic_connection_uses_request_host_port_for_callback(
    authenticated_client,
) -> None:
    start = authenticated_client.post(
        "/v1/oauth/connections",
        json={"provider": "anthropic", "label": "port-check-anthropic"},
        headers={"host": "127.0.0.1:9106"},
    )

    assert start.status_code == 201
    query = parse_qs(urlparse(start.json()["authorize_url"]).query)
    assert query["redirect_uri"] == ["http://localhost:9106/callback"]


def test_anthropic_connection_lifecycle_and_label_conflict(
    authenticated_client, fake_keychain
) -> None:
    account_id = _account_id(authenticated_client)
    authenticated_client.app.state.anthropic_http_factory = _anthropic_token_factory()

    start = authenticated_client.post(
        "/v1/oauth/connections",
        json={"provider": "anthropic", "label": "work-anthropic"},
    )
    assert start.status_code == 201
    state = start.json()["state"]
    connection_id = start.json()["connection_id"]
    assert urlparse(start.json()["authorize_url"]).scheme == "https"

    cb = authenticated_client.get("/callback", params={"code": "code", "state": state})
    assert cb.status_code == 200

    detail = authenticated_client.get(f"/v1/oauth/connections/{connection_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "active"
    assert body["label"] == "work-anthropic"
    assert body["account"] is None
    assert (
        body["credential_locator"]["service"] == f"aigateway:anthropic:{account_id}:{connection_id}"
    )
    assert fake_keychain.read(body["credential_locator"]["service"], "default") is not None

    duplicate_label = authenticated_client.post(
        "/v1/oauth/connections",
        json={"provider": "anthropic", "label": "work-anthropic"},
    )
    assert duplicate_label.status_code == 409
    assert duplicate_label.json()["detail"]["code"] == "label_conflict"


def test_anthropic_connection_can_reconnect_after_delete(authenticated_client) -> None:
    authenticated_client.app.state.anthropic_http_factory = _anthropic_token_factory()

    first = authenticated_client.post(
        "/v1/oauth/connections",
        json={"provider": "anthropic", "label": "reconnect-anthropic"},
    )
    assert first.status_code == 201
    first_id = first.json()["connection_id"]
    assert (
        authenticated_client.get(
            "/callback", params={"code": "first", "state": first.json()["state"]}
        ).status_code
        == 200
    )
    assert authenticated_client.delete(f"/v1/oauth/connections/{first_id}").status_code == 204
    assert [
        item["id"]
        for item in authenticated_client.get(
            "/v1/oauth/connections", params={"provider": "anthropic"}
        ).json()["connections"]
    ] == []
    assert [
        item["id"]
        for item in authenticated_client.get(
            "/v1/oauth/connections", params={"provider": "anthropic", "status": "revoked"}
        ).json()["connections"]
    ] == [first_id]

    second = authenticated_client.post(
        "/v1/oauth/connections",
        json={"provider": "anthropic", "label": "reconnect-anthropic"},
    )
    assert second.status_code == 201
    second_id = second.json()["connection_id"]
    assert second_id != first_id
    assert (
        authenticated_client.get(
            "/callback", params={"code": "second", "state": second.json()["state"]}
        ).status_code
        == 200
    )

    detail = authenticated_client.get(f"/v1/oauth/connections/{second_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "active"

    assert authenticated_client.delete(f"/v1/oauth/connections/{second_id}").status_code == 204
    third = authenticated_client.post(
        "/v1/oauth/connections",
        json={"provider": "anthropic", "label": "reconnect-anthropic"},
    )
    assert third.status_code == 201
    assert (
        authenticated_client.get(
            "/callback", params={"code": "third", "state": third.json()["state"]}
        ).status_code
        == 200
    )


def test_failed_anthropic_connection_can_retry_same_label(authenticated_client) -> None:
    authenticated_client.app.state.anthropic_http_factory = _failing_token_factory()
    failed = authenticated_client.post(
        "/v1/oauth/connections",
        json={"provider": "anthropic", "label": "retry-anthropic"},
    )
    assert failed.status_code == 201
    callback = authenticated_client.get(
        "/callback", params={"code": "fail", "state": failed.json()["state"]}
    )
    assert callback.status_code == 500

    authenticated_client.app.state.anthropic_http_factory = _anthropic_token_factory()
    retry = authenticated_client.post(
        "/v1/oauth/connections",
        json={"provider": "anthropic", "label": "retry-anthropic"},
    )
    assert retry.status_code == 201
    assert (
        authenticated_client.get(
            "/callback", params={"code": "ok", "state": retry.json()["state"]}
        ).status_code
        == 200
    )


def test_refresh_error_releases_label_for_reauth(authenticated_client, fake_keychain) -> None:
    authenticated_client.app.state.anthropic_http_factory = _anthropic_token_factory()
    start = authenticated_client.post(
        "/v1/oauth/connections",
        json={"provider": "anthropic", "label": "refresh-error-anthropic"},
    )
    assert start.status_code == 201
    connection_id = start.json()["connection_id"]
    assert (
        authenticated_client.get(
            "/callback", params={"code": "first", "state": start.json()["state"]}
        ).status_code
        == 200
    )
    connection = authenticated_client.get(f"/v1/oauth/connections/{connection_id}").json()
    fake_keychain.delete(connection["credential_locator"]["service"], "default")

    refresh = authenticated_client.post(f"/v1/oauth/connections/{connection_id}/refresh")
    assert refresh.status_code == 401
    patch = authenticated_client.patch(
        f"/v1/oauth/connections/{connection_id}",
        json={"label": "refresh-error-anthropic"},
    )
    assert patch.status_code == 409
    assert patch.json()["detail"]["code"] == "connection_not_active"
    retry_refresh = authenticated_client.post(f"/v1/oauth/connections/{connection_id}/refresh")
    assert retry_refresh.status_code == 409
    assert retry_refresh.json()["detail"]["code"] == "connection_not_active"

    retry = authenticated_client.post(
        "/v1/oauth/connections",
        json={"provider": "anthropic", "label": "refresh-error-anthropic"},
    )
    assert retry.status_code == 201
    assert (
        authenticated_client.get(
            "/callback", params={"code": "second", "state": retry.json()["state"]}
        ).status_code
        == 200
    )


def test_patch_connection_label_conflict_returns_409(authenticated_client) -> None:
    authenticated_client.app.state.anthropic_http_factory = _anthropic_token_factory()

    first = authenticated_client.post(
        "/v1/oauth/connections",
        json={"provider": "anthropic", "label": "first-anthropic"},
    )
    second = authenticated_client.post(
        "/v1/oauth/connections",
        json={"provider": "anthropic", "label": "second-anthropic"},
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert (
        authenticated_client.get(
            "/callback", params={"code": "first", "state": first.json()["state"]}
        ).status_code
        == 200
    )
    assert (
        authenticated_client.get(
            "/callback", params={"code": "second", "state": second.json()["state"]}
        ).status_code
        == 200
    )

    conflict = authenticated_client.patch(
        f"/v1/oauth/connections/{second.json()['connection_id']}",
        json={"label": "first-anthropic"},
    )

    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "label_conflict"


def test_codex_duplicate_connection_returns_existing(
    authenticated_client, fake_keychain, monkeypatch
) -> None:
    account_id = _account_id(authenticated_client)
    authenticated_client.app.state.codex_http_factory = _codex_token_factory()
    monkeypatch.setattr(
        authenticated_client.app.state.providers.get("codex"),
        "oauth_config",
        lambda: OAuthConfig(
            authorize_url=CODEX_AUTHORIZE_URL,
            token_url=CODEX_TOKEN_URL,
            client_id=CODEX_CLIENT_ID,
            scopes=CODEX_SCOPES,
            redirect_path=CODEX_REDIRECT_PATH,
            extra_authorize_params=CODEX_AUTHORIZE_EXTRA_PARAMS,
            loopback_redirect_ports=None,
        ),
    )

    first = authenticated_client.post("/v1/oauth/connections", json={"provider": "codex"})
    assert first.status_code == 201
    first_id = first.json()["connection_id"]
    assert (
        authenticated_client.get(
            "/auth/callback", params={"code": "first", "state": first.json()["state"]}
        ).status_code
        == 200
    )

    second = authenticated_client.post("/v1/oauth/connections", json={"provider": "codex"})
    assert second.status_code == 201
    second_id = second.json()["connection_id"]
    assert (
        authenticated_client.get(
            "/auth/callback", params={"code": "second", "state": second.json()["state"]}
        ).status_code
        == 200
    )

    reused = authenticated_client.get(f"/v1/oauth/connections/{second_id}")
    assert reused.status_code == 200
    body = reused.json()
    assert body["id"] == first_id
    assert body["is_duplicate"] is True

    active = authenticated_client.get(
        "/v1/oauth/connections", params={"provider": "codex", "status": "active"}
    )
    assert [item["id"] for item in active.json()["connections"]] == [first_id]
    assert fake_keychain.read(f"aigateway:codex:{account_id}:{second_id}", "default") is None


def test_connection_lookup_is_account_scoped(
    authenticated_client, provisioned_user_factory
) -> None:
    start = authenticated_client.post(
        "/v1/oauth/connections",
        json={"provider": "anthropic", "label": "admin-anthropic"},
    )
    assert start.status_code == 201
    connection_id = start.json()["connection_id"]

    provisioned_user_factory("bob", "bob-pass1")
    login = authenticated_client.post(
        "/v1/auth/login", json={"username": "bob", "password": "bob-pass1"}
    )
    authenticated_client.headers.update({"Authorization": f"Bearer {login.json()['token']}"})

    assert authenticated_client.get(f"/v1/oauth/connections/{connection_id}").status_code == 404
    assert (
        authenticated_client.patch(
            f"/v1/oauth/connections/{connection_id}", json={"label": "x"}
        ).status_code
        == 404
    )
    assert authenticated_client.delete(f"/v1/oauth/connections/{connection_id}").status_code == 404
