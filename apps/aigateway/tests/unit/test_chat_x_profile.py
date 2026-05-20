from __future__ import annotations

import json
import time
from functools import partial
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import httpx
import pytest
from litellm.exceptions import RateLimitError

from aigateway.core.auth.middleware import ANONYMOUS_ACCOUNT_ID
from aigateway.core.oauth.store import OAuthConnectionStore, credential_key_for
from aigateway.core.profile_index import ProfileIndexStore
from aigateway.core.profile_models import (
    Profile,
    ProfileDefaults,
    ProfileState,
    credential_name_for,
    profile_id_for,
)
from aigateway.plugins.anthropic_provider.auth import keychain_service_for
from aigateway.plugins.codex_provider.auth import keychain_service_for as codex_keychain_service_for


def _account_id(client) -> str:
    return client.get("/v1/auth/me").json()["id"]


def _seed_authenticated_profile(fake_keychain, account_id: str) -> None:
    fake_keychain.write(
        keychain_service_for(credential_name_for(account_id, "default")),
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


def _seed_authenticated_connection(
    fake_keychain,
    account_id: str,
    connection_id: str | UUID,
    *,
    access_token: str = "connection-tok",
) -> None:
    fake_keychain.write(
        keychain_service_for(credential_key_for(account_id, connection_id)),
        "default",
        json.dumps(
            {
                "access_token": access_token,
                "refresh_token": "connection-rt",
                "expires_at_ms": int(time.time() * 1000) + 3_600_000,
                "token_type": "Bearer",
            }
        ),
    )


async def _create_active_connection(
    account_id: str,
    *,
    provider: str = "anthropic",
    label: str = "work-anthropic",
):
    store = OAuthConnectionStore()
    connection = await store.create_pending(
        account_id=account_id,
        provider=provider,
        label=label,
        connection_id=uuid4(),
    )
    return await store.complete(connection, label=label, identity=None)


def _seed_authenticated_codex_profile(fake_keychain, account_id: str) -> None:
    fake_keychain.write(
        codex_keychain_service_for(credential_name_for(account_id, "default")),
        "default",
        json.dumps(
            {
                "access_token": "tok",
                "refresh_token": "rt",
                "id_token": "id",
                "expires_at_ms": int(time.time() * 1000) + 3_600_000,
                "token_type": "Bearer",
            }
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model",
    ["anthropic/claude-haiku-4-5", "codex/gpt-5.4-mini"],
)
async def test_chat_404_when_oauth_profile_missing(authenticated_client, model: str) -> None:
    resp = authenticated_client.post(
        "/v1/chat/completions",
        headers={"X-Profile": "missing"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "profile_not_found"


@pytest.mark.asyncio
async def test_chat_404_when_codex_profile_missing(authenticated_client) -> None:
    resp = authenticated_client.post(
        "/v1/chat/completions",
        headers={"X-Profile": "missing"},
        json={
            "model": "codex/gpt-5.4-mini",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )

    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "profile_not_found"


def test_chat_uses_single_active_oauth_connection_when_profile_missing(
    fake_keychain, authenticated_client
) -> None:
    account_id = _account_id(authenticated_client)
    connection = authenticated_client.portal.call(_create_active_connection, account_id)
    _seed_authenticated_connection(fake_keychain, account_id, connection.id)
    captured: dict = {}

    async def fake_chat_completion(_self, body):
        captured.update(body)
        from types import SimpleNamespace

        return SimpleNamespace(
            model_dump=lambda: {
                "id": "x",
                "choices": [{"message": {"content": "ok"}}],
            }
        )

    with patch(
        "aigateway.plugins.anthropic_provider.plugin.AnthropicProviderPlugin.chat_completion",
        fake_chat_completion,
    ):
        resp = authenticated_client.post(
            "/v1/chat/completions",
            json={
                "model": "anthropic/claude-haiku-4-5",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

    assert resp.status_code == 200
    assert captured["api_key"] == "connection-tok"
    refreshed = authenticated_client.portal.call(
        OAuthConnectionStore().get, account_id, connection.id
    )
    assert refreshed is not None
    assert refreshed.last_used_at is not None


def test_chat_requires_profile_label_when_multiple_oauth_connections_exist(
    fake_keychain, authenticated_client
) -> None:
    account_id = _account_id(authenticated_client)
    first = authenticated_client.portal.call(
        partial(_create_active_connection, account_id, label="work-anthropic")
    )
    second = authenticated_client.portal.call(
        partial(_create_active_connection, account_id, label="personal-anthropic")
    )
    _seed_authenticated_connection(fake_keychain, account_id, first.id, access_token="work-tok")
    _seed_authenticated_connection(
        fake_keychain, account_id, second.id, access_token="personal-tok"
    )

    ambiguous = authenticated_client.post(
        "/v1/chat/completions",
        json={
            "model": "anthropic/claude-haiku-4-5",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert ambiguous.status_code == 409
    assert ambiguous.json()["detail"]["code"] == "connection_ambiguous"

    captured: dict = {}

    async def fake_chat_completion(_self, body):
        captured.update(body)
        from types import SimpleNamespace

        return SimpleNamespace(
            model_dump=lambda: {
                "id": "x",
                "choices": [{"message": {"content": "ok"}}],
            }
        )

    with patch(
        "aigateway.plugins.anthropic_provider.plugin.AnthropicProviderPlugin.chat_completion",
        fake_chat_completion,
    ):
        resp = authenticated_client.post(
            "/v1/chat/completions",
            headers={"X-Profile": "personal-anthropic"},
            json={
                "model": "anthropic/claude-haiku-4-5",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

    assert resp.status_code == 200
    assert captured["api_key"] == "personal-tok"


def test_chat_empty_x_profile_header_uses_default_ambiguity(
    fake_keychain, authenticated_client
) -> None:
    account_id = _account_id(authenticated_client)
    authenticated_client.portal.call(
        partial(_create_active_connection, account_id, label="work-anthropic")
    )
    authenticated_client.portal.call(
        partial(_create_active_connection, account_id, label="personal-anthropic")
    )

    resp = authenticated_client.post(
        "/v1/chat/completions",
        headers={"X-Profile": ""},
        json={
            "model": "anthropic/claude-haiku-4-5",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "connection_ambiguous"


def test_chat_cannot_use_other_accounts_oauth_connection(
    fake_keychain, authenticated_client, provisioned_user_factory
) -> None:
    admin_account_id = _account_id(authenticated_client)
    connection = authenticated_client.portal.call(_create_active_connection, admin_account_id)
    _seed_authenticated_connection(fake_keychain, admin_account_id, connection.id)

    provisioned_user_factory("bob", "bob-pass1")
    login = authenticated_client.post(
        "/v1/auth/login",
        json={"username": "bob", "password": "bob-pass1"},
    )
    authenticated_client.headers.update({"Authorization": f"Bearer {login.json()['token']}"})

    resp = authenticated_client.post(
        "/v1/chat/completions",
        json={
            "model": "anthropic/claude-haiku-4-5",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )

    assert resp.status_code == 404


def test_chat_uses_oauth_connection_for_anonymous_local_mode(fake_keychain, client) -> None:
    client.app.state.settings.auth_enabled = False
    account_id = str(ANONYMOUS_ACCOUNT_ID)
    connection = client.portal.call(_create_active_connection, account_id)
    _seed_authenticated_connection(fake_keychain, account_id, connection.id)
    captured: dict = {}

    async def fake_chat_completion(_self, body):
        captured.update(body)
        from types import SimpleNamespace

        return SimpleNamespace(
            model_dump=lambda: {
                "id": "x",
                "choices": [{"message": {"content": "ok"}}],
            }
        )

    with patch(
        "aigateway.plugins.anthropic_provider.plugin.AnthropicProviderPlugin.chat_completion",
        fake_chat_completion,
    ):
        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "anthropic/claude-haiku-4-5",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

    assert resp.status_code == 200
    assert captured["api_key"] == "connection-tok"


@pytest.mark.asyncio
async def test_chat_409_when_profile_pending(fake_keychain, authenticated_client) -> None:
    account_id = _account_id(authenticated_client)
    idx = ProfileIndexStore(credential_store=fake_keychain)
    await idx.upsert(
        Profile(
            id=profile_id_for(account_id, "anthropic", "default"),
            account_id=account_id,
            provider="anthropic",
            name="default",
            state=ProfileState.PENDING,
        )
    )
    resp = authenticated_client.post(
        "/v1/chat/completions",
        json={
            "model": "anthropic/claude-haiku-4-5",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "profile_pending_auth"


@pytest.mark.asyncio
async def test_chat_merges_profile_defaults(fake_keychain, authenticated_client) -> None:
    account_id = _account_id(authenticated_client)
    _seed_authenticated_profile(fake_keychain, account_id)

    idx = ProfileIndexStore(credential_store=fake_keychain)
    await idx.upsert(
        Profile(
            id=profile_id_for(account_id, "anthropic", "default"),
            account_id=account_id,
            provider="anthropic",
            name="default",
            state=ProfileState.AUTHENTICATED,
            defaults=ProfileDefaults(max_tokens=4096, reasoning_effort="medium"),
        )
    )

    captured: dict = {}

    async def fake_chat_completion(_self, body):
        captured.update(body)
        from types import SimpleNamespace

        return SimpleNamespace(
            model_dump=lambda: {
                "id": "x",
                "choices": [{"message": {"content": "ok"}}],
            }
        )

    with patch(
        "aigateway.plugins.anthropic_provider.plugin.AnthropicProviderPlugin.chat_completion",
        fake_chat_completion,
    ):
        resp = authenticated_client.post(
            "/v1/chat/completions",
            json={
                "model": "anthropic/claude-haiku-4-5",
                "messages": [{"role": "user", "content": "hi"}],
                "reasoning_effort": "high",  # body wins
                # max_tokens omitted — profile default fills in
            },
        )
        assert resp.status_code == 200
        assert captured["max_tokens"] == 4096
        assert captured["reasoning_effort"] == "high"
    assert captured["api_key"] == "tok"


@pytest.mark.asyncio
async def test_chat_skips_anthropic_profile_reasoning_default(
    fake_keychain, authenticated_client
) -> None:
    account_id = _account_id(authenticated_client)
    _seed_authenticated_profile(fake_keychain, account_id)

    idx = ProfileIndexStore(credential_store=fake_keychain)
    await idx.upsert(
        Profile(
            id=profile_id_for(account_id, "anthropic", "default"),
            account_id=account_id,
            provider="anthropic",
            name="default",
            state=ProfileState.AUTHENTICATED,
            defaults=ProfileDefaults(reasoning_effort="medium"),
        )
    )
    captured: dict = {}

    async def fake_chat_completion(_self, body):
        captured.update(body)
        from types import SimpleNamespace

        return SimpleNamespace(
            model_dump=lambda: {
                "id": "x",
                "choices": [{"message": {"content": "ok"}}],
            }
        )

    with patch(
        "aigateway.plugins.anthropic_provider.plugin.AnthropicProviderPlugin.chat_completion",
        fake_chat_completion,
    ):
        resp = authenticated_client.post(
            "/v1/chat/completions",
            json={
                "model": "anthropic/claude-haiku-4-5",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

    assert resp.status_code == 200
    assert "reasoning_effort" not in captured


@pytest.mark.asyncio
async def test_chat_removes_anthropic_reasoning_none(fake_keychain, authenticated_client) -> None:
    account_id = _account_id(authenticated_client)
    _seed_authenticated_profile(fake_keychain, account_id)

    idx = ProfileIndexStore(credential_store=fake_keychain)
    await idx.upsert(
        Profile(
            id=profile_id_for(account_id, "anthropic", "default"),
            account_id=account_id,
            provider="anthropic",
            name="default",
            state=ProfileState.AUTHENTICATED,
        )
    )
    captured: dict = {}

    async def fake_chat_completion(_self, body):
        captured.update(body)
        from types import SimpleNamespace

        return SimpleNamespace(
            model_dump=lambda: {
                "id": "x",
                "choices": [{"message": {"content": "ok"}}],
            }
        )

    with patch(
        "aigateway.plugins.anthropic_provider.plugin.AnthropicProviderPlugin.chat_completion",
        fake_chat_completion,
    ):
        resp = authenticated_client.post(
            "/v1/chat/completions",
            json={
                "model": "anthropic/claude-haiku-4-5",
                "messages": [{"role": "user", "content": "hi"}],
                "reasoning_effort": "none",
            },
        )

    assert resp.status_code == 200
    assert "reasoning_effort" not in captured


@pytest.mark.asyncio
async def test_chat_cannot_use_other_accounts_profile(
    fake_keychain, authenticated_client, provisioned_user_factory
) -> None:
    admin_account_id = _account_id(authenticated_client)
    _seed_authenticated_profile(fake_keychain, admin_account_id)
    idx = ProfileIndexStore(credential_store=fake_keychain)
    await idx.upsert(
        Profile(
            id=profile_id_for(admin_account_id, "anthropic", "shared"),
            account_id=admin_account_id,
            provider="anthropic",
            name="shared",
            state=ProfileState.AUTHENTICATED,
        )
    )

    provisioned_user_factory("bob", "bob-pass1")
    login = authenticated_client.post(
        "/v1/auth/login",
        json={"username": "bob", "password": "bob-pass1"},
    )
    authenticated_client.headers.update({"Authorization": f"Bearer {login.json()['token']}"})

    resp = authenticated_client.post(
        "/v1/chat/completions",
        headers={"X-Profile": "shared"},
        json={
            "model": "anthropic/claude-haiku-4-5",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert resp.status_code == 404


def test_chat_requires_auth(client) -> None:
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "anthropic/claude-haiku-4-5", "messages": []},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_chat_rejects_codex_stream_before_litellm(
    fake_keychain, authenticated_client
) -> None:
    account_id = _account_id(authenticated_client)
    _seed_authenticated_codex_profile(fake_keychain, account_id)
    idx = ProfileIndexStore(credential_store=fake_keychain)
    await idx.upsert(
        Profile(
            id=profile_id_for(account_id, "codex", "default"),
            account_id=account_id,
            provider="codex",
            name="default",
            state=ProfileState.AUTHENTICATED,
        )
    )
    fake_stream = AsyncMock()

    with patch(
        "aigateway.plugins.codex_provider.plugin.CodexProviderPlugin.chat_completion_stream",
        fake_stream,
    ):
        resp = authenticated_client.post(
            "/v1/chat/completions",
            json={
                "model": "codex/gpt-5.4-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
        )

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "streaming_not_supported"
    fake_stream.assert_not_called()


@pytest.mark.asyncio
async def test_chat_streams_through_provider_plugin_boundary(
    fake_keychain, authenticated_client
) -> None:
    account_id = _account_id(authenticated_client)
    _seed_authenticated_profile(fake_keychain, account_id)
    idx = ProfileIndexStore(credential_store=fake_keychain)
    await idx.upsert(
        Profile(
            id=profile_id_for(account_id, "anthropic", "default"),
            account_id=account_id,
            provider="anthropic",
            name="default",
            state=ProfileState.AUTHENTICATED,
        )
    )
    captured: dict = {}

    async def fake_stream_completion(_self, body):
        captured.update(body)

        from types import SimpleNamespace

        yield SimpleNamespace(model_dump=lambda: {"choices": [{"delta": {"content": "hi"}}]})

    with patch(
        "aigateway.plugins.anthropic_provider.plugin.AnthropicProviderPlugin.chat_completion_stream",
        fake_stream_completion,
    ):
        resp = authenticated_client.post(
            "/v1/chat/completions",
            json={
                "model": "anthropic/claude-haiku-4-5",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
        )

    assert resp.status_code == 200
    assert 'data: {"choices": [{"delta": {"content": "hi"}}]}' in resp.text
    assert "data: [DONE]" in resp.text
    assert captured["api_key"] == "tok"


@pytest.mark.asyncio
async def test_chat_overwrites_client_api_key_for_codex_oauth(
    fake_keychain, authenticated_client
) -> None:
    account_id = _account_id(authenticated_client)
    _seed_authenticated_codex_profile(fake_keychain, account_id)
    idx = ProfileIndexStore(credential_store=fake_keychain)
    await idx.upsert(
        Profile(
            id=profile_id_for(account_id, "codex", "default"),
            account_id=account_id,
            provider="codex",
            name="default",
            state=ProfileState.AUTHENTICATED,
        )
    )
    captured: dict = {}

    async def fake_acompletion(_self, body):
        captured.update(body)
        from types import SimpleNamespace

        return SimpleNamespace(
            model_dump=lambda: {
                "id": "x",
                "choices": [{"message": {"content": "ok"}}],
            }
        )

    with patch(
        "aigateway.plugins.codex_provider.plugin.CodexProviderPlugin.chat_completion",
        fake_acompletion,
    ):
        resp = authenticated_client.post(
            "/v1/chat/completions",
            json={
                "model": "codex/gpt-5.4-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "api_key": "client-supplied-token",
            },
        )

    assert resp.status_code == 200
    assert captured["api_key"] == "tok"


@pytest.mark.asyncio
async def test_chat_maps_codex_reasoning_effort_to_reasoning(
    fake_keychain, authenticated_client
) -> None:
    account_id = _account_id(authenticated_client)
    _seed_authenticated_codex_profile(fake_keychain, account_id)
    idx = ProfileIndexStore(credential_store=fake_keychain)
    await idx.upsert(
        Profile(
            id=profile_id_for(account_id, "codex", "default"),
            account_id=account_id,
            provider="codex",
            name="default",
            state=ProfileState.AUTHENTICATED,
            defaults=ProfileDefaults(reasoning_effort="medium"),
        )
    )
    captured: dict = {}

    async def fake_acompletion(_self, body):
        captured.update(body)
        from types import SimpleNamespace

        return SimpleNamespace(
            model_dump=lambda: {
                "id": "x",
                "choices": [{"message": {"content": "ok"}}],
            }
        )

    with patch(
        "aigateway.plugins.codex_provider.plugin.CodexProviderPlugin.chat_completion",
        fake_acompletion,
    ):
        resp = authenticated_client.post(
            "/v1/chat/completions",
            json={
                "model": "codex/gpt-5.4-mini",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

    assert resp.status_code == 200
    assert captured["reasoning"] == {"effort": "medium"}
    assert "reasoning_effort" not in captured


@pytest.mark.asyncio
async def test_chat_maps_litellm_rate_limit_to_429(fake_keychain, authenticated_client) -> None:
    account_id = _account_id(authenticated_client)
    _seed_authenticated_profile(fake_keychain, account_id)
    idx = ProfileIndexStore(credential_store=fake_keychain)
    await idx.upsert(
        Profile(
            id=profile_id_for(account_id, "anthropic", "default"),
            account_id=account_id,
            provider="anthropic",
            name="default",
            state=ProfileState.AUTHENTICATED,
        )
    )
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(429, headers={"retry-after": "7"}, request=request)

    async def fake_chat_completion(_self, _body):
        raise RateLimitError(
            "limited",
            llm_provider="anthropic",
            model="anthropic/claude-sonnet-4-5",
            response=response,
        )

    with patch(
        "aigateway.plugins.anthropic_provider.plugin.AnthropicProviderPlugin.chat_completion",
        fake_chat_completion,
    ):
        resp = authenticated_client.post(
            "/v1/chat/completions",
            json={
                "model": "anthropic/claude-sonnet-4-5",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

    assert resp.status_code == 429
    assert resp.headers["retry-after"] == "7"
    assert resp.json()["detail"]["code"] == "rate_limited"
