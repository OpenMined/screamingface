"""E2E tests for url4 expression resolution via /ensemble endpoint.

Migrated from test_e2e_url4.py — tests basic url4 resolution and intent
dispatch without mocks.
"""

from __future__ import annotations

import shutil

import httpx
import pytest

from tests.e2e.infrastructure.server_manager import ServerManager

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(30)]


class TestUrl4Resolution:
    """Tests for the /ensemble endpoint — url4 expression resolution."""

    def test_resolve_plain_text(self, sf_server: ServerManager):
        resp = httpx.get(f"{sf_server.base_url}/ensemble", params={"q": "hello"})

        assert resp.status_code == 200
        assert "hello" in resp.text

    def test_missing_q_rejected(self, sf_server: ServerManager):
        resp = httpx.get(f"{sf_server.base_url}/ensemble", params={"context": "hello"})

        assert resp.status_code == 400

    def test_text_intent_returns_combined(self, sf_server: ServerManager):
        """Text intent is treated as literal — returns intent + sources."""
        resp = httpx.get(f"{sf_server.base_url}/ensemble", params={"q": "hello!echo"})

        assert resp.status_code == 200
        assert "echo" in resp.text
        assert "hello" in resp.text

    def test_resolve_http_url(self, sf_server: ServerManager, httpbin_url: str):
        """Fetches a real URL and returns its content."""
        resp = httpx.get(
            f"{sf_server.base_url}/ensemble",
            params={"q": f"{httpbin_url}/robots.txt"},
            timeout=15,
        )

        assert resp.status_code == 200
        assert "User-agent" in resp.text

    def test_resolve_parenthesized_group(self, sf_server: ServerManager):
        """Resolves a parenthesized group of text atoms."""
        resp = httpx.get(f"{sf_server.base_url}/ensemble", params={"q": "(hello, world)"})

        assert resp.status_code == 200
        assert "hello" in resp.text
        assert "world" in resp.text

    def test_ast_mode(self, sf_server: ServerManager):
        """?ast=true returns JSON with both AST and resolved result."""
        resp = httpx.get(
            f"{sf_server.base_url}/ensemble",
            params={"q": "hello", "ast": "true"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert "ast" in data
        assert "result" in data


@pytest.mark.e2e_live
@pytest.mark.timeout(120)
class TestUrl4IntentDispatch:
    """Tests that require Claude CLI for intent dispatch."""

    @pytest.fixture(autouse=True)
    def _require_claude(self):
        if not shutil.which("claude"):
            pytest.skip("Claude CLI not found in PATH")

    def test_intent_dispatch_to_claude(self, sf_server: ServerManager):
        """Plain text context dispatched to claude-backend."""
        from urllib.parse import quote

        backend_url = f"{sf_server.base_url}/claude/default"
        prompt = "respond with exactly: E2E_OK"
        intent_url = f"{backend_url}?prompt={quote(prompt)}"

        resp = httpx.get(
            f"{sf_server.base_url}/ensemble",
            params={"q": f"hello!{intent_url}"},
            timeout=60,
        )

        assert resp.status_code == 200
        assert resp.text.strip() != ""

    def test_intent_fetch_then_dispatch(self, sf_server: ServerManager):
        """Fetched resource context dispatched to claude-backend."""
        from urllib.parse import quote

        health_url = f"{sf_server.base_url}/health"
        backend_url = f"{sf_server.base_url}/claude/default"
        prompt = "describe what you see in one sentence"
        intent_url = f"{backend_url}?prompt={quote(prompt)}"

        resp = httpx.get(
            f"{sf_server.base_url}/ensemble",
            params={"q": f"({health_url})!{intent_url}"},
            timeout=60,
        )

        assert resp.status_code == 200
        assert resp.text.strip() != ""
