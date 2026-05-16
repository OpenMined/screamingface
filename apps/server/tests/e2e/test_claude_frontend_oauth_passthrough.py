"""E2E: claude-frontend transparent OAuth-access-token passthrough to real Anthropic.

This test pins the configuration SF-198 set up:

    Claude Code-style client (Authorization: Bearer <oauth-access-token>)
        --> claude-frontend (transparent passthrough, no env-var injection)
        --> https://api.anthropic.com (real)

The proxy MUST forward the Bearer header unchanged; it MUST NOT substitute
an API token or inject an env-var fallback. SF-198 removed the env-var
fallback; this test guarantees that the OAuth path still reaches Anthropic
and returns a 200.

Skipped on machines without a Claude Code keychain entry.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest

from tests.e2e.infrastructure.claude_code_client import ClaudeCodeClient
from tests.e2e.infrastructure.claude_oauth import has_claude_code_oauth
from tests.e2e.infrastructure.claude_oauth_token import (
    ClaudeOAuthError,
    read_claude_code_oauth_access_token,
)
from tests.e2e.infrastructure.server_manager import ServerManager

pytestmark = pytest.mark.e2e_live


@pytest.fixture(scope="module")
def proxy_server() -> Generator[tuple[ServerManager, int], None, None]:
    if not has_claude_code_oauth():
        pytest.skip("Claude Code OAuth credential not found in macOS keychain")

    internal_port = ServerManager.find_free_port()
    proxy_port = ServerManager.find_free_port()

    config = {
        "version": "0.1.0",
        "server": {
            "host": "127.0.0.1",
            "port": internal_port,
            "ssl": False,
            "reload": False,
        },
        "plugins": ["claude-frontend"],
        "plugin_config": {
            "claude-frontend": {
                "upstream_url": "https://api.anthropic.com",
                "listen_host": "127.0.0.1",
                "listen_port": proxy_port,
            },
        },
    }

    mgr = ServerManager(config, session_id="e2e-sf199-oauth-passthrough")
    mgr.start(timeout=60)
    if not ServerManager.wait_for_port(proxy_port, timeout=60):
        last_logs = "\n".join(mgr.logs.dump_last()) if mgr.logs else "<no logs>"
        mgr.stop()
        pytest.fail(
            f"claude-frontend not listening on port {proxy_port}\n"
            f"Last server log lines:\n{last_logs}"
        )
    try:
        yield mgr, proxy_port
    finally:
        mgr.stop()


@pytest.mark.timeout(60)
def test_oauth_access_token_passthrough_round_trip(
    proxy_server: tuple[ServerManager, int],
) -> None:
    """End-to-end proof that the proxy forwards an OAuth Bearer to Anthropic.

    SUCCESS criteria - either of:
      * 200 with a well-formed content block (Anthropic happily replied), OR
      * 429 with a structured Anthropic rate_limit_error AND an Anthropic
        request_id (proves the Bearer reached Anthropic and was accepted -
        a 401 would mean auth failed; 429 means auth succeeded but the
        account is throttled).

    Any other status (401, 5xx, malformed body) is a real failure.
    """
    _, proxy_port = proxy_server
    try:
        access_token = read_claude_code_oauth_access_token()
    except ClaudeOAuthError as exc:
        pytest.skip(f"Cannot read OAuth access token: {exc}")

    client = ClaudeCodeClient(
        proxy_url=f"http://127.0.0.1:{proxy_port}",
        auth_mode="oauth_access_token",
        oauth_access_token=access_token,
    )
    resp = client.send_message("Reply with exactly the word OK.", timeout=45)

    if resp.status_code == 200:
        content = resp.body.get("content")
        assert isinstance(content, list) and content, f"unexpected body shape: {resp.body}"
        first = content[0]
        assert first.get("type") == "text"
        assert isinstance(first.get("text"), str) and first["text"].strip()
        return

    if resp.status_code == 429:
        # Anthropic-shaped error proves the Bearer reached Anthropic and was
        # accepted. We don't pin the message text, only the structural shape.
        body = resp.body if isinstance(resp.body, dict) else {}
        err = body.get("error", {}) if isinstance(body.get("error"), dict) else {}
        assert err.get("type") == "rate_limit_error", (
            f"429 without anthropic rate_limit_error shape: {resp.body}"
        )
        # Prefer the response header (canonical Anthropic source); fall back
        # to the body field if the header was not surfaced.
        header_request_id = resp.headers.get("request-id") or resp.headers.get("x-request-id")
        raw_body_rid = body.get("request_id")
        body_request_id = raw_body_rid if isinstance(raw_body_rid, str) else None
        request_id = header_request_id or body_request_id
        assert isinstance(request_id, str) and request_id.startswith("req_"), (
            f"429 without anthropic request_id (headers={resp.headers!r}, body={resp.body!r})"
        )
        return

    pytest.fail(f"proxy responded {resp.status_code}: {resp.body}")
