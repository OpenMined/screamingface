"""Test that OAuthStrategy routes through aigw_source when configured."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from screamingface.plugins.llm_base.aigw_token_source import AigwTokenSource
from screamingface.plugins.llm_base.oauth_base import OAuthStrategy

# SF-335 / C12 cross-app contract: mirrored BY CONTRACT (not shared code) with
# the AIGateway OAuth base (apps/aigateway/src/aigateway/core/oauth_base.py).
EXPECTED_REFRESH_WINDOW_SECONDS = 60


def test_refresh_window_matches_cross_app_contract() -> None:
    # The one genuinely-shared-yet-unpinned cross-app invariant (SF-335 / C12);
    # mirror any change in BOTH apps or fan-out refresh decisions drift (SF-282).
    assert OAuthStrategy.refresh_window_seconds == EXPECTED_REFRESH_WINDOW_SECONDS


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
async def test_aigw_source_remains_authoritative_for_each_header_request():
    fake_source = AsyncMock(spec=AigwTokenSource)
    fake_source.fetch_token.side_effect = ["aigw-token-1", "aigw-token-2"]
    strat = _FakeStrategy(aigw_source=fake_source)

    first = await strat.get_authorization_header()
    second = await strat.get_authorization_header()

    assert first == {"Authorization": "Bearer aigw-token-1"}
    assert second == {"Authorization": "Bearer aigw-token-2"}
    assert fake_source.fetch_token.await_count == 2


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
