"""Route-level tests for the opt-in request cache on /v1/chat/completions.

Provider-dimension isolation is proven at the key level
(test_request_cache_keys.py): a route-level "different provider" request is
the same as a "different model prefix" request, which is covered here by the
different-model test.
"""

from __future__ import annotations

import json
import time
from functools import partial
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from aigateway.core.oauth.store import OAuthConnectionStore, credential_key_for
from aigateway.plugins.anthropic_provider.auth import credential_service_for

_CHAT_PATH = "/v1/chat/completions"
_PATCH_TARGET = (
    "aigateway.plugins.anthropic_provider.plugin.AnthropicProviderPlugin.chat_completion"
)


def _account_id(client) -> str:
    return client.get("/v1/auth/me").json()["id"]


async def _create_active_connection(account_id: str, *, label: str = "default"):
    store = OAuthConnectionStore()
    connection = await store.create_pending(
        account_id=account_id,
        provider="anthropic",
        label=label,
        connection_id=uuid4(),
    )
    return await store.complete(connection, label=label, identity=None)


def _seed_connection_credentials(credential_blobs, account_id: str, connection_id) -> None:
    credential_blobs.write(
        credential_service_for(credential_key_for(account_id, connection_id)),
        "default",
        json.dumps(
            {
                "access_token": "tok",
                "refresh_token": "rt",
                "expires_at_ms": int(time.time() * 1000) + 3_600_000,
                "token_type": "Bearer",
            }
        ),
    )


def _arrange_account(client, credential_blobs, *, label: str = "default") -> str:
    account_id = _account_id(client)
    connection = client.portal.call(partial(_create_active_connection, account_id, label=label))
    _seed_connection_credentials(credential_blobs, account_id, connection.id)
    return account_id


class _DispatchCounter:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    # Patched over the *class* method with an instance, which bypasses
    # function-descriptor binding — so only `body` arrives.
    async def __call__(self, body):
        self.calls.append(dict(body))
        from types import SimpleNamespace

        return SimpleNamespace(
            model_dump=lambda: {
                "id": f"resp-{len(self.calls)}",
                "choices": [{"message": {"content": "SECRET-ANSWER"}}],
            }
        )


def _chat_body(**overrides) -> dict:
    body = {
        "model": "anthropic/claude-haiku-4-5",
        "messages": [{"role": "user", "content": "hi"}],
        "cache": {"use-cache": True},
    }
    body.update(overrides)
    return body


@pytest.fixture
def _cache_env(monkeypatch):
    # Must run before the `client` fixture builds the app so Settings sees it.
    monkeypatch.setenv("AIGW_REQUEST_CACHE_ENABLED", "true")


@pytest.fixture
def cache_client(_cache_env, client: TestClient) -> TestClient:
    response = client.post(
        "/v1/auth/login",
        json={"username": "admin", "password": "test-admin-password"},
    )
    assert response.status_code == 200, response.text
    client.headers.update({"Authorization": f"Bearer {response.json()['token']}"})
    return client


def test_cache_disabled_by_default_dispatches_twice(credential_blobs, authenticated_client) -> None:
    _arrange_account(authenticated_client, credential_blobs)
    counter = _DispatchCounter()
    with patch(_PATCH_TARGET, counter):
        first = authenticated_client.post(_CHAT_PATH, json=_chat_body())
        second = authenticated_client.post(_CHAT_PATH, json=_chat_body())
    assert first.status_code == second.status_code == 200
    assert len(counter.calls) == 2
    assert first.headers["X-AIGW-Cache"] == "bypass"
    assert first.headers["X-AIGW-Cache-Reason"] == "disabled"


def test_enabled_but_not_requested_dispatches_twice(credential_blobs, cache_client) -> None:
    _arrange_account(cache_client, credential_blobs)
    counter = _DispatchCounter()
    body = _chat_body()
    del body["cache"]
    with patch(_PATCH_TARGET, counter):
        cache_client.post(_CHAT_PATH, json=body)
        resp = cache_client.post(_CHAT_PATH, json=body)
    assert len(counter.calls) == 2
    assert resp.headers["X-AIGW-Cache"] == "bypass"
    assert resp.headers["X-AIGW-Cache-Reason"] == "not_requested"


def test_opt_in_hit_skips_provider_dispatch(credential_blobs, cache_client) -> None:
    _arrange_account(cache_client, credential_blobs)
    counter = _DispatchCounter()
    with patch(_PATCH_TARGET, counter):
        first = cache_client.post(_CHAT_PATH, json=_chat_body())
        second = cache_client.post(_CHAT_PATH, json=_chat_body())
    assert first.status_code == second.status_code == 200
    assert len(counter.calls) == 1, "second identical request must be served from cache"
    assert first.headers["X-AIGW-Cache"] == "miss"
    assert first.headers["X-AIGW-Cache-Reason"] == "stored"
    assert second.headers["X-AIGW-Cache"] == "hit"
    assert second.json() == first.json()
    # The cache key header is hash-derived only.
    assert "hi" not in second.headers.get("X-AIGW-Cache-Key", "")
    assert len(second.headers["X-AIGW-Cache-Key"]) == 12


def test_different_account_misses(credential_blobs, cache_client, provisioned_user_factory) -> None:
    _arrange_account(cache_client, credential_blobs)
    counter = _DispatchCounter()
    with patch(_PATCH_TARGET, counter):
        cache_client.post(_CHAT_PATH, json=_chat_body())

        provisioned_user_factory("second-user")
        login = cache_client.post(
            "/v1/auth/login",
            json={"username": "second-user", "password": "test-user-password"},
        )
        assert login.status_code == 200
        other_headers = {"Authorization": f"Bearer {login.json()['token']}"}
        other_account = cache_client.get("/v1/auth/me", headers=other_headers).json()["id"]
        connection = cache_client.portal.call(_create_active_connection, other_account)
        _seed_connection_credentials(credential_blobs, other_account, connection.id)

        resp = cache_client.post(_CHAT_PATH, json=_chat_body(), headers=other_headers)
    assert resp.status_code == 200
    assert len(counter.calls) == 2, "another account must never hit the first account's cache"
    assert resp.headers["X-AIGW-Cache"] == "miss"


def test_different_profile_misses(credential_blobs, cache_client) -> None:
    account_id = _account_id(cache_client)
    for label in ("default", "work"):
        connection = cache_client.portal.call(
            partial(_create_active_connection, account_id, label=label)
        )
        _seed_connection_credentials(credential_blobs, account_id, connection.id)
    counter = _DispatchCounter()
    with patch(_PATCH_TARGET, counter):
        first = cache_client.post(_CHAT_PATH, json=_chat_body())
        second = cache_client.post(_CHAT_PATH, json=_chat_body(), headers={"X-Profile": "work"})
    assert first.status_code == second.status_code == 200
    assert len(counter.calls) == 2, "a different X-Profile must not share the cache entry"
    assert second.headers["X-AIGW-Cache"] == "miss"


def test_different_model_misses(credential_blobs, cache_client) -> None:
    _arrange_account(cache_client, credential_blobs)
    counter = _DispatchCounter()
    with patch(_PATCH_TARGET, counter):
        cache_client.post(_CHAT_PATH, json=_chat_body())
        resp = cache_client.post(_CHAT_PATH, json=_chat_body(model="anthropic/claude-sonnet-4-6"))
    assert resp.status_code == 200
    assert len(counter.calls) == 2


def test_no_cache_skips_lookup_but_stores(credential_blobs, cache_client) -> None:
    _arrange_account(cache_client, credential_blobs)
    counter = _DispatchCounter()
    with patch(_PATCH_TARGET, counter):
        cache_client.post(_CHAT_PATH, json=_chat_body())
        refreshed = cache_client.post(
            _CHAT_PATH, json=_chat_body(cache={"use-cache": True, "no-cache": True})
        )
        third = cache_client.post(_CHAT_PATH, json=_chat_body())
    assert len(counter.calls) == 2, "no-cache must skip lookup and re-dispatch"
    assert refreshed.headers["X-AIGW-Cache"] == "miss"
    # The refreshed response was stored: the third request hits it.
    assert third.headers["X-AIGW-Cache"] == "hit"
    assert third.json()["id"] == "resp-2"


def test_no_store_prevents_storage(credential_blobs, cache_client) -> None:
    _arrange_account(cache_client, credential_blobs)
    counter = _DispatchCounter()
    no_store_body = _chat_body(cache={"use-cache": True, "no-store": True})
    with patch(_PATCH_TARGET, counter):
        first = cache_client.post(_CHAT_PATH, json=no_store_body)
        second = cache_client.post(_CHAT_PATH, json=no_store_body)
    assert len(counter.calls) == 2, "no-store responses must not be persisted"
    assert first.headers["X-AIGW-Cache"] == "miss"
    assert first.headers["X-AIGW-Cache-Reason"] == "no_store"
    assert second.headers["X-AIGW-Cache"] == "miss"


def test_expired_entry_dispatches_again(credential_blobs, cache_client) -> None:
    _arrange_account(cache_client, credential_blobs)
    counter = _DispatchCounter()
    body = _chat_body(cache={"use-cache": True, "ttl": 1})
    with patch(_PATCH_TARGET, counter):
        cache_client.post(_CHAT_PATH, json=body)
        time.sleep(1.2)
        resp = cache_client.post(_CHAT_PATH, json=body)
    assert len(counter.calls) == 2
    assert resp.headers["X-AIGW-Cache"] == "miss"


def test_stream_bypasses_cache(credential_blobs, cache_client) -> None:
    _arrange_account(cache_client, credential_blobs)

    async def fake_stream(_self, body):
        from types import SimpleNamespace

        yield SimpleNamespace(model_dump=lambda: {"choices": [{"delta": {"content": "x"}}]})

    counter = _DispatchCounter()
    with (
        patch(_PATCH_TARGET, counter),
        patch(
            "aigateway.plugins.anthropic_provider.plugin.AnthropicProviderPlugin.chat_completion_stream",
            fake_stream,
        ),
    ):
        resp = cache_client.post(_CHAT_PATH, json=_chat_body(stream=True))
        resp2 = cache_client.post(_CHAT_PATH, json=_chat_body(stream=True))
    assert resp.status_code == resp2.status_code == 200
    assert len(counter.calls) == 0, "streaming must use the streaming path, never the cache"


def test_unsupported_field_bypasses(credential_blobs, cache_client) -> None:
    _arrange_account(cache_client, credential_blobs)
    counter = _DispatchCounter()
    body = _chat_body(temperature=0.7)
    with patch(_PATCH_TARGET, counter):
        first = cache_client.post(_CHAT_PATH, json=body)
        second = cache_client.post(_CHAT_PATH, json=body)
    assert len(counter.calls) == 2
    assert first.headers["X-AIGW-Cache"] == "bypass"
    assert second.headers["X-AIGW-Cache"] == "bypass"
    assert first.headers["X-AIGW-Cache-Reason"] == "unsupported_fields"


def test_cache_headers_do_not_leak_content(credential_blobs, cache_client) -> None:
    _arrange_account(cache_client, credential_blobs)
    counter = _DispatchCounter()
    with patch(_PATCH_TARGET, counter):
        resp = cache_client.post(
            _CHAT_PATH,
            json=_chat_body(messages=[{"role": "user", "content": "SECRET-PROMPT"}]),
        )
    header_blob = json.dumps(dict(resp.headers))
    assert "SECRET-PROMPT" not in header_blob
    assert "SECRET-ANSWER" not in header_blob
