from __future__ import annotations

import json
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from aigateway.core.profile_index import ProfileIndexStore
from aigateway.core.profile_models import Profile, ProfileDefaults, ProfileState
from aigateway.main import create_app
from aigateway.plugins.anthropic_provider.auth import keychain_service_for


def _seed_authenticated_profile(fake_keychain) -> None:
    fake_keychain.write(
        keychain_service_for("default"),
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


def _patch_credential_factory(monkeypatch, fake_keychain):
    from aigateway.core import bootstrap as bs_module
    from aigateway.core import credential_store as cs_module
    from aigateway.core import profile_index as pi_module
    from aigateway.plugins.anthropic_provider import auth as auth_module

    monkeypatch.setattr(cs_module, "get_credential_store", lambda: fake_keychain)
    monkeypatch.setattr(pi_module, "get_credential_store", lambda: fake_keychain)
    monkeypatch.setattr(bs_module, "get_credential_store", lambda: fake_keychain)
    monkeypatch.setattr(auth_module, "get_credential_store", lambda: fake_keychain)


@pytest.mark.asyncio
async def test_chat_404_when_profile_missing(fake_keychain, monkeypatch) -> None:
    _patch_credential_factory(monkeypatch, fake_keychain)

    client = TestClient(create_app())
    resp = client.post(
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
async def test_chat_409_when_profile_pending(fake_keychain, monkeypatch) -> None:
    _patch_credential_factory(monkeypatch, fake_keychain)

    idx = ProfileIndexStore(credential_store=fake_keychain)
    await idx.upsert(
        Profile(
            id="anthropic:default",
            provider="anthropic",
            name="default",
            state=ProfileState.PENDING,
        )
    )
    client = TestClient(create_app())
    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "anthropic/claude-haiku-4-5",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "profile_pending_auth"


@pytest.mark.asyncio
async def test_chat_merges_profile_defaults(fake_keychain, monkeypatch) -> None:
    _patch_credential_factory(monkeypatch, fake_keychain)
    _seed_authenticated_profile(fake_keychain)

    idx = ProfileIndexStore(credential_store=fake_keychain)
    await idx.upsert(
        Profile(
            id="anthropic:default",
            provider="anthropic",
            name="default",
            state=ProfileState.AUTHENTICATED,
            defaults=ProfileDefaults(max_tokens=4096, reasoning_effort="medium"),
        )
    )

    captured: dict = {}

    async def fake_acompletion(**kwargs):
        captured.update(kwargs)
        from types import SimpleNamespace

        return SimpleNamespace(
            model_dump=lambda: {
                "id": "x",
                "choices": [{"message": {"content": "ok"}}],
            }
        )

    with patch("aigateway.routes.chat.litellm.acompletion", fake_acompletion):
        client = TestClient(create_app())
        resp = client.post(
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
