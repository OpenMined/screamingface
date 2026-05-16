from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from litellm.exceptions import RateLimitError

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
async def test_chat_404_when_profile_missing(authenticated_client) -> None:
    resp = authenticated_client.post(
        "/v1/chat/completions",
        headers={"X-Profile": "missing"},
        json={
            "model": "anthropic/claude-haiku-4-5",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "profile_not_found"


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
    fake_acompletion = AsyncMock()

    with patch("aigateway.routes.chat.litellm.acompletion", fake_acompletion):
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
    fake_acompletion.assert_not_called()


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
