"""The non-streaming dispatch path has a full exception boundary
(OME-428 third-review blocker B).

# STORY: as the gateway I must never turn an unexpected exception (a
# RuntimeError, a ValueError, a new litellm exception type, a malformed
# conversion) into an uncontrolled HTTP 500 with an ASGI traceback that leaks
# the raw provider message/prompt. Every non-streaming dispatch failure renders
# a sanitized status.
# INVARIANT: an exception that is neither a curated HTTPException nor a known
# litellm type still yields a sanitized 502 `provider_error`; the raw text never
# reaches the response, the logs, or persisted connection error state; and the
# credential is invalidated ONLY when the sanitized status proves 401 (never for
# a generic 502).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi import HTTPException

from aigateway.core.oauth.store import OAuthConnectionStore
from aigateway.plugins.openrouter_provider import plugin as openrouter_plugin_module
from aigateway.plugins.openrouter_provider.settings import OpenRouterPluginSettings

_KEY = "sk-or-v1-boundary"
_MODEL = "openrouter/anthropic/claude-fable-5"


@pytest.fixture()
def enabled_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        openrouter_plugin_module.PLUGIN, "settings", OpenRouterPluginSettings(enabled=True)
    )


@contextmanager
def _server_errors_as_responses(client) -> Iterator[None]:
    transport = client._transport
    previous = transport.raise_server_exceptions
    transport.raise_server_exceptions = False
    try:
        yield
    finally:
        transport.raise_server_exceptions = previous


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


def test_unknown_exception_becomes_sanitized_502_without_leak(
    enabled_openrouter,
    credential_blobs,
    authenticated_client,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unexpected exception that escapes the plugin (neither an HTTPException
    nor a known litellm type) is rendered as a sanitized 502, never a 500, and
    its raw text reaches neither the response nor the logs."""
    _create_connection(authenticated_client, "work-or")
    account_id = _account_id(authenticated_client)
    secret = "SECRET-raw-runtime-detail-9931"

    async def _boom(_self, _body):
        raise RuntimeError(secret)

    # AIDEV-NOTE: patch the CLASS method, never the PLUGIN instance. `getattr`
    # on the instance resolves `chat_completion` via the class, so a
    # `monkeypatch.setattr(PLUGIN, ...)` restores by re-`setattr` — leaving a
    # shadowing bound method in `PLUGIN.__dict__` that survives teardown and
    # corrupts later tests that patch the class method (e.g. the BYOK e2e test).
    monkeypatch.setattr(openrouter_plugin_module.OpenRouterProviderPlugin, "chat_completion", _boom)

    with (
        caplog.at_level(logging.DEBUG, logger="aigateway"),
        _server_errors_as_responses(authenticated_client),
    ):
        resp = _post_chat(authenticated_client)

    assert resp.status_code == 502
    assert resp.status_code != 500
    assert resp.json()["detail"]["code"] == "provider_error"
    # Raw exception text must not leak into the response or the logs.
    assert secret not in resp.text
    assert secret not in caplog.text
    # A generic 502 is not a 401 -> the stored connection stays active.
    assert _active_labels(authenticated_client, account_id) == ["work-or"]


def test_unknown_status_attribute_cannot_trigger_credential_invalidation(
    enabled_openrouter,
    credential_blobs,
    authenticated_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _create_connection(authenticated_client, "work-or")
    account_id = _account_id(authenticated_client)
    exc = RuntimeError("unclassified")
    exc.status_code = 401  # type: ignore[attr-defined]

    async def _boom(_self, _body):
        raise exc

    monkeypatch.setattr(openrouter_plugin_module.OpenRouterProviderPlugin, "chat_completion", _boom)
    resp = _post_chat(authenticated_client)

    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "provider_error"
    assert _active_labels(authenticated_client, account_id) == ["work-or"]


def test_throwing_exception_properties_cannot_escape_terminal_boundary(
    enabled_openrouter,
    credential_blobs,
    authenticated_client,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _create_connection(authenticated_client, "work-or")
    secret = "SECRET-throwing-property"

    class RaisingStatus(RuntimeError):
        @property
        def status_code(self):
            raise ValueError(secret)

    async def _boom(_self, _body):
        raise RaisingStatus("outer")

    monkeypatch.setattr(openrouter_plugin_module.OpenRouterProviderPlugin, "chat_completion", _boom)
    with (
        caplog.at_level(logging.DEBUG, logger="aigateway"),
        _server_errors_as_responses(authenticated_client),
    ):
        resp = _post_chat(authenticated_client)

    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "provider_error"
    assert secret not in resp.text
    assert secret not in caplog.text


def test_credential_failure_persistence_error_is_sanitized_502(
    enabled_openrouter,
    credential_blobs,
    authenticated_client,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _create_connection(authenticated_client, "work-or")
    account_id = _account_id(authenticated_client)
    secret = "SECRET-persistence-failure"

    async def _auth_failure(_self, _body):
        raise HTTPException(
            status_code=401,
            detail={"code": "auth_required", "message": "Authentication required"},
        )

    async def _mark_error_failure(_self, _connection, _message):
        raise RuntimeError(secret)

    monkeypatch.setattr(
        openrouter_plugin_module.OpenRouterProviderPlugin,
        "chat_completion",
        _auth_failure,
    )
    monkeypatch.setattr(OAuthConnectionStore, "mark_error", _mark_error_failure)
    with (
        caplog.at_level(logging.DEBUG, logger="aigateway"),
        _server_errors_as_responses(authenticated_client),
    ):
        resp = _post_chat(authenticated_client)

    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "provider_error"
    assert secret not in resp.text
    assert secret not in caplog.text
    assert _active_labels(authenticated_client, account_id) == ["work-or"]
