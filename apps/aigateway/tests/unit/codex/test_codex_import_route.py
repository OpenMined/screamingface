from __future__ import annotations

import json

import pytest

from aigateway.core.profile_models import profile_id_for

from .helpers import write_codex_auth


def _account_id(client) -> str:
    return client.get("/v1/auth/me").json()["id"]


def test_codex_import_route_requires_jwt(client, codex_home) -> None:
    write_codex_auth(codex_home)

    resp = client.post("/v1/auth/codex/profiles/import", json={"name": "default"})

    assert resp.status_code == 401


def test_generic_codex_oauth_start_is_rejected(authenticated_client) -> None:
    resp = authenticated_client.post("/v1/auth/codex/profiles", json={"name": "default"})

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "provider_does_not_use_oauth"


def test_codex_import_creates_authenticated_profile(authenticated_client, codex_home) -> None:
    write_codex_auth(
        codex_home,
        id_claims={"sub": "sub-1", "email": "codex@example.com"},
        account_id="acct-1",
    )
    account_id = _account_id(authenticated_client)

    resp = authenticated_client.post(
        "/v1/auth/codex/profiles/import",
        json={"name": "work", "defaults": {"model": "codex/gpt-5.4-mini"}},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] == profile_id_for(account_id, "codex", "work")
    assert body["provider"] == "codex"
    assert body["state"] == "authenticated"
    assert body["account_label"] == "codex@example.com"
    assert body["defaults"]["model"] == "codex/gpt-5.4-mini"


@pytest.mark.asyncio
async def test_codex_chat_translates_reasoning_effort_before_litellm(
    authenticated_client, codex_home, monkeypatch
) -> None:
    captured: dict = {}

    class FakeResponse:
        def model_dump(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    async def fake_acompletion(**kwargs):
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr("aigateway.routes.chat.litellm.acompletion", fake_acompletion)
    write_codex_auth(codex_home)
    imported = authenticated_client.post(
        "/v1/auth/codex/profiles/import",
        json={"name": "default", "defaults": {"reasoning_effort": "high"}},
    )
    assert imported.status_code == 201, imported.text

    resp = authenticated_client.post(
        "/v1/chat/completions",
        json={"model": "codex/gpt-5.4-mini", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert resp.status_code == 200, resp.text
    assert captured["reasoning"] == {"effort": "high"}
    assert "reasoning_effort" not in captured


def test_codex_import_returns_auth_required_when_file_missing(authenticated_client) -> None:
    resp = authenticated_client.post("/v1/auth/codex/profiles/import", json={"name": "default"})

    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "auth_required"


def test_delete_codex_profile_does_not_touch_codex_auth_file(
    authenticated_client, codex_home
) -> None:
    auth_path = write_codex_auth(codex_home)
    original = json.loads(auth_path.read_text())
    imported = authenticated_client.post("/v1/auth/codex/profiles/import", json={"name": "default"})
    assert imported.status_code == 201

    deleted = authenticated_client.delete("/v1/auth/codex/profiles/default")

    assert deleted.status_code == 204
    assert json.loads(auth_path.read_text()) == original


@pytest.mark.asyncio
async def test_codex_streaming_fails_before_streaming_response(
    authenticated_client, codex_home
) -> None:
    write_codex_auth(codex_home)
    imported = authenticated_client.post("/v1/auth/codex/profiles/import", json={"name": "default"})
    assert imported.status_code == 201

    resp = authenticated_client.post(
        "/v1/chat/completions",
        json={
            "model": "codex/gpt-5.4-mini",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        },
    )

    assert resp.status_code == 501
    assert resp.json()["detail"] == {"code": "streaming_not_supported", "provider": "codex"}
