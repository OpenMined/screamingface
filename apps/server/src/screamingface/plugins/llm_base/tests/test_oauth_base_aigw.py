"""Test that OAuthStrategy routes through aigw_source when configured."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from screamingface.plugins.llm_base.aigw_token_source import AigwTokenSource
from screamingface.plugins.llm_base.oauth_base import OAuthStrategy


class _FakeStrategy(OAuthStrategy):
    """Concrete strategy that uses the snake_case shape (like Codex/Gemini)."""

    def _read_credential(self) -> dict:
        raise AssertionError("CLI keychain path must not be reached with aigw_source set")

    def _is_expired(self, creds: dict) -> bool:
        return False

    async def _refresh_credential(self, creds: dict) -> dict:
        raise AssertionError("provider refresh must not be reached with aigw_source set")

    def _build_headers(self, creds: dict) -> dict[str, str]:
        return {"Authorization": f"Bearer {creds['access_token']}"}

    def _aigw_creds_shape(self, access_token: str, expires_at: datetime) -> dict:
        return {"access_token": access_token, "expires_at_iso": expires_at.isoformat()}


@pytest.mark.asyncio
async def test_aigw_source_replaces_keychain_read():
    fake_source = AsyncMock(spec=AigwTokenSource)
    fake_source.fetch_token.return_value = "aigw-token-1"
    strat = _FakeStrategy(aigw_source=fake_source)

    headers = await strat.get_authorization_header()
    assert headers == {"Authorization": "Bearer aigw-token-1"}
    fake_source.fetch_token.assert_awaited_once()


@pytest.mark.asyncio
async def test_aigw_source_unset_uses_existing_path():
    """Sanity: without aigw_source the existing abstract hooks are called."""

    class _LocalStrategy(_FakeStrategy):
        called = False

        def _read_credential(self):
            _LocalStrategy.called = True
            return {"access_token": "from-disk"}

    strat = _LocalStrategy()
    headers = await strat.get_authorization_header()
    assert headers == {"Authorization": "Bearer from-disk"}
    assert _LocalStrategy.called is True
