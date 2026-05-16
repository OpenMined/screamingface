"""Unit tests for the ClaudeCodeClient auth-mode header builder."""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.claude_code_client import ClaudeCodeClient


def _headers_for(client: ClaudeCodeClient) -> dict[str, str]:
    """Use the same private builder the client uses for real requests."""
    return client._auth_headers()  # noqa: SLF001 — exercising the boundary


def test_api_token_mode_emits_x_api_key() -> None:
    client = ClaudeCodeClient(proxy_url="http://x", api_key="sk-abc")
    headers = _headers_for(client)
    assert headers == {"x-api-key": "sk-abc"}


def test_oauth_access_token_mode_emits_bearer_and_oauth_betas() -> None:
    client = ClaudeCodeClient(
        proxy_url="http://x",
        auth_mode="oauth_access_token",
        oauth_access_token="tkn-1",
    )
    headers = _headers_for(client)
    assert headers["Authorization"] == "Bearer tkn-1"
    assert headers["anthropic-version"] == "2023-06-01"
    assert headers["anthropic-beta"] == "oauth-2025-04-20"
    assert "x-api-key" not in headers


def test_oauth_mode_requires_token() -> None:
    client = ClaudeCodeClient(proxy_url="http://x", auth_mode="oauth_access_token")
    with pytest.raises(ValueError, match="oauth_access_token"):
        _headers_for(client)


def test_default_is_api_token_backward_compat() -> None:
    client = ClaudeCodeClient(proxy_url="http://x")
    assert client.auth_mode == "api_token"
    assert _headers_for(client) == {"x-api-key": "test-key"}
