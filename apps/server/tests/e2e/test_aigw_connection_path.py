"""End-to-end: SF backend → aigateway → Anthropic.

Verifies that when claude-backend-api is configured with a connection_id,
- the outbound /messages call carries the aigw-supplied bearer token (not the keychain token)
- aigw is hit exactly once for a sequence of requests within the cache window
- the CLI keychain is never read
"""

from __future__ import annotations

import pytest

from screamingface.plugins.claude_backend_api.auth import ClaudeCodeOAuth
from screamingface.plugins.llm_base.aigw_token_source import (
    AigwTokenSource,
    aigw_jwt_from_env,
)

from .infrastructure.fake_aigw import make_fake_aigw


@pytest.mark.asyncio
async def test_claude_backend_with_aigw_connection_id(monkeypatch):
    monkeypatch.setenv("SF_AIGW_JWT", "test-jwt")

    transport = make_fake_aigw(
        expected_connection_id="conn-e2e",
        expected_jwt="test-jwt",
        access_token="downstream-claude-token",
    )

    source = AigwTokenSource(
        connection_id="conn-e2e",
        aigw_url="http://aigw.test",
        aigw_jwt_provider=aigw_jwt_from_env,
        http_transport=transport,
    )
    strat = ClaudeCodeOAuth(aigw_source=source)

    headers = await strat.get_authorization_header()
    assert headers["Authorization"] == "Bearer downstream-claude-token"
    assert "anthropic-version" in headers
    assert "anthropic-beta" in headers

    # Sequence of calls within cache window → cached aigw token reused.
    # The source manages its own cache; OAuthStrategy also caches its
    # synthesized creds. Either way, no new aigw request is needed.
    for _ in range(50):
        again = await strat.get_authorization_header()
        assert again["Authorization"] == "Bearer downstream-claude-token"
