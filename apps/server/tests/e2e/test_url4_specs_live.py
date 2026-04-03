"""E2E tests for url4 spec evaluation against real external resources.

These tests fetch real URLs and verify that url4 resolution produces
non-empty, expected content. Useful for ongoing correctness monitoring.
"""

from __future__ import annotations

import httpx
import pytest

from tests.e2e.infrastructure.server_manager import ServerManager

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(30)]


class TestUrl4SpecsLive:
    """Tests that evaluate url4 specs against real external URLs."""

    def test_single_url_resolution(self, sf_server: ServerManager):
        """Single URL expression resolves to non-empty content."""
        resp = httpx.get(
            f"{sf_server.base_url}/ensemble",
            params={"q": "https://httpbin.org/robots.txt"},
            timeout=15,
        )

        assert resp.status_code == 200
        assert len(resp.text.strip()) > 0
        assert "User-agent" in resp.text

    def test_multiple_urls_parallel(self, sf_server: ServerManager):
        """Parenthesized group of URLs resolved in parallel."""
        expr = "(https://httpbin.org/robots.txt, https://httpbin.org/user-agent)"
        resp = httpx.get(
            f"{sf_server.base_url}/ensemble",
            params={"q": expr},
            timeout=15,
        )

        assert resp.status_code == 200
        assert "User-agent" in resp.text

    def test_mixed_text_and_url(self, sf_server: ServerManager):
        """Mix of text atoms and URL atoms in a group."""
        expr = "(context preamble, https://httpbin.org/robots.txt)"
        resp = httpx.get(
            f"{sf_server.base_url}/ensemble",
            params={"q": expr},
            timeout=15,
        )

        assert resp.status_code == 200
        assert "context preamble" in resp.text
        assert "User-agent" in resp.text

    def test_resolution_idempotency(self, sf_server: ServerManager):
        """Same expression resolves to same content across runs."""
        expr = "https://httpbin.org/robots.txt"

        resp1 = httpx.get(
            f"{sf_server.base_url}/ensemble",
            params={"q": expr},
            timeout=15,
        )
        resp2 = httpx.get(
            f"{sf_server.base_url}/ensemble",
            params={"q": expr},
            timeout=15,
        )

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.text == resp2.text

    def test_relative_url_data_store(self, sf_server: ServerManager):
        """Relative URL /data/{key} resolved via in-process ASGI."""
        # First store a blob
        store_resp = httpx.post(
            f"{sf_server.base_url}/data",
            content=b"test blob content",
            headers={"content-type": "text/plain"},
            timeout=10,
        )
        assert store_resp.status_code == 200
        key = store_resp.json()["key"]

        # Now resolve it via url4
        resp = httpx.get(
            f"{sf_server.base_url}/ensemble",
            params={"q": f"/data/{key}"},
            timeout=10,
        )

        assert resp.status_code == 200
        assert "test blob content" in resp.text

    def test_intent_with_text(self, sf_server: ServerManager):
        """Expression with text intent (quoted string after !)."""
        expr = "(https://httpbin.org/robots.txt)!'Summarize this'"
        resp = httpx.get(
            f"{sf_server.base_url}/ensemble",
            params={"q": expr},
            timeout=15,
        )

        assert resp.status_code == 200
        # With text intent, result is: intent + "\n\n" + sources
        assert "Summarize this" in resp.text
        assert "User-agent" in resp.text
