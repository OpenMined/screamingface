"""Benign top-level ``error`` shapes pass through as paid successes (CODE-1).

litellm 1.87.0's converter (convert_dict_to_response.py:491-509) deliberately
returns a valid ModelResponse for benign top-level error shapes — "some
OpenAI-compatible providers return empty error objects even on success". The
gateway must not turn such a billed 200 into a 502: the payload (including
native usage/cost — D10) reaches the caller intact and the stored key is
never invalidated.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from aigateway.core.oauth.store import OAuthConnectionStore
from aigateway.plugins.openrouter_provider import plugin as openrouter_plugin_module
from aigateway.plugins.openrouter_provider.settings import OpenRouterPluginSettings

_KEY = "sk-or-v1-benign"
_MODEL = "openrouter/anthropic/claude-fable-5"

_VALID_CHOICES = [
    {
        "index": 0,
        "finish_reason": "stop",
        "message": {"role": "assistant", "content": "hello"},
    }
]


@pytest.fixture()
def enabled_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        openrouter_plugin_module.PLUGIN, "settings", OpenRouterPluginSettings(enabled=True)
    )


def _account_id(client) -> str:
    return client.get("/v1/auth/me").json()["id"]


def _create_connection(client, label: str) -> None:
    resp = client.post(
        "/v1/oauth/connections/api-key",
        json={"provider": "openrouter", "label": label, "api_key": _KEY},
    )
    assert resp.status_code == 201, resp.text


def _active_labels(client, account_id: str) -> list[str]:
    async def _list() -> list[str]:
        connections = await OAuthConnectionStore().list(
            account_id, provider="openrouter", status="active"
        )
        return sorted(connection.label for connection in connections)

    return client.portal.call(_list)


def _post_chat(client):
    return client.post(
        "/v1/chat/completions",
        json={"model": _MODEL, "messages": [{"role": "user", "content": "hi"}]},
    )


def _returning_acompletion(payload: dict):
    async def fake_acompletion(**_kwargs):
        return SimpleNamespace(model_dump=lambda: payload)

    return fake_acompletion


@pytest.mark.parametrize(
    "payload",
    [
        # The benign trio litellm's converter passes through (:491-509) …
        {"id": "gen-b1", "choices": _VALID_CHOICES, "error": {}},
        {"id": "gen-b2", "choices": _VALID_CHOICES, "error": ""},
        {"id": "gen-b3", "choices": _VALID_CHOICES, "error": {"code": None, "message": ""}},
        # … and the paid-success case: full native usage/cost alongside error:{}.
        {
            "id": "gen-b4",
            "model": "anthropic/claude-fable-5",
            "provider": "Anthropic",
            "choices": _VALID_CHOICES,
            "error": {},
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "cost": 0.00021,
                "cost_details": {"upstream_inference_cost": 0.0002},
                "is_byok": True,
            },
        },
    ],
)
def test_benign_top_level_error_returns_the_paid_payload_intact(
    enabled_openrouter, credential_blobs, authenticated_client, payload: dict
) -> None:
    account_id = _account_id(authenticated_client)
    _create_connection(authenticated_client, "work-or")

    with patch("litellm.acompletion", _returning_acompletion(payload)):
        resp = _post_chat(authenticated_client)

    # STORY: as a BYOK user I paid for this completion — the gateway must not
    # discard it as a 502 because the upstream attached a benign error object.
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.pop("_aigw")["usage_accounting"]["schema"] == "aigw.chat_usage_accounting"
    assert body == payload
    assert _active_labels(authenticated_client, account_id) == ["work-or"]
