"""Unit tests for OllamaAuth — optional bearer token, no refresh."""

from __future__ import annotations

import pytest

from screamingface.plugins.ollama_backend_api.auth import OllamaAuth

pytestmark = pytest.mark.anyio


class TestGetAuthorizationHeader:
    async def test_no_key_returns_empty_dict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        auth = OllamaAuth()
        assert await auth.get_authorization_header() == {}

    async def test_explicit_api_key_sent_as_bearer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        auth = OllamaAuth(api_key="local-secret")
        assert await auth.get_authorization_header() == {"Authorization": "Bearer local-secret"}

    async def test_env_var_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OLLAMA_API_KEY", "env-secret")
        auth = OllamaAuth()
        assert await auth.get_authorization_header() == {"Authorization": "Bearer env-secret"}

    async def test_explicit_key_wins_over_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OLLAMA_API_KEY", "env-secret")
        auth = OllamaAuth(api_key="explicit-secret")
        assert await auth.get_authorization_header() == {"Authorization": "Bearer explicit-secret"}


class TestLifecycle:
    async def test_refresh_is_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        auth = OllamaAuth(api_key="x")
        assert await auth.refresh() is None

    def test_invalidate_cache_is_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        auth = OllamaAuth(api_key="x")
        assert auth.invalidate_cache() is None
