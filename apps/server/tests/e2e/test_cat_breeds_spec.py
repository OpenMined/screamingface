"""E2E test for the cat-breeds-3sources url4 spec.

Spec expression (decoded):
  /claude?q=(src1.csv, src2.csv, src3.txt)!$prompt

Pipeline:
  1. Proxy substitutes $prompt → /data/{blob_key}
  2. The entire expression is a relative URL to /claude?q=...
  3. /claude endpoint URL-decodes q, gets: (src1,src2,src3)!/data/{key}
  4. ClaudeInterpreter resolves 3 GitHub sources in parallel
  5. Fetches /data/{key} to get the user's original prompt
  6. Sends sources + prompt to Claude CLI
  7. Claude's response is injected into the user message

Tests:
  - Source resolution (3 GitHub URLs) — no Claude CLI needed
  - Full pipeline through proxy — requires Claude CLI (e2e_live)
"""

from __future__ import annotations

import shutil
from urllib.parse import quote

import httpx
import pytest

from tests.e2e.infrastructure.claude_code_client import ClaudeCodeClient
from tests.e2e.infrastructure.otlp_collector import OTLPCollector
from tests.e2e.infrastructure.server_manager import ServerManager

CAT_SOURCES = [
    "https://raw.githubusercontent.com/phiggins/phiggins_coding_challenge/master/examples/cat_breeds.csv",
    "https://raw.githubusercontent.com/prasertcbs/basic-dataset/master/cat.csv",
    "https://raw.githubusercontent.com/multimandan/PetSave/refs/heads/master/cat-breeds.txt",
]

# The spec expression — URL-encoded parens/commas/bang inside the q= parameter.
# $prompt must stay unencoded so the proxy detects it for substitution.
_inner = quote(f"({','.join(CAT_SOURCES)})!$prompt", safe="$")
CAT_SPEC_EXPRESSION = f"/claude?q={_inner}"


# ---------------------------------------------------------------------------
# Level 1: Source resolution only (no Claude CLI)
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.e2e


@pytest.mark.timeout(30)
class TestCatBreedSources:
    """Verify the 3 GitHub cat-breed sources are fetchable and contain data."""

    @pytest.mark.parametrize("url", CAT_SOURCES, ids=["csv1", "csv2", "txt"])
    def test_individual_source(self, sf_server: ServerManager, url: str):
        """Each source URL resolves to non-empty content via /ensemble."""
        resp = httpx.get(
            f"{sf_server.base_url}/ensemble",
            params={"q": url},
            timeout=15,
        )
        assert resp.status_code == 200
        assert len(resp.text.strip()) > 0, f"Empty response from {url}"

    def test_all_sources_parallel(self, sf_server: ServerManager):
        """All 3 sources resolve in parallel via parenthesized group."""
        expr = f"({','.join(CAT_SOURCES)})"
        resp = httpx.get(
            f"{sf_server.base_url}/ensemble",
            params={"q": expr},
            timeout=30,
        )
        assert resp.status_code == 200
        text = resp.text
        # Should contain data from multiple sources
        assert len(text) > 100, f"Combined sources too short: {len(text)} chars"

    def test_sources_contain_breed_data(self, sf_server: ServerManager):
        """Resolved sources should contain actual cat breed names."""
        expr = f"({','.join(CAT_SOURCES)})"
        resp = httpx.get(
            f"{sf_server.base_url}/ensemble",
            params={"q": expr},
            timeout=30,
        )
        assert resp.status_code == 200
        text = resp.text.lower()
        # At least some well-known breeds should appear
        known_breeds = ["persian", "siamese", "bengal", "maine"]
        found = [b for b in known_breeds if b in text]
        assert len(found) >= 2, (
            f"Expected cat breed names in sources. Found: {found}. Text preview: {resp.text[:300]}"
        )


# ---------------------------------------------------------------------------
# Level 2: Full pipeline through proxy (requires Claude CLI)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def cat_proxy(otlp_collector: OTLPCollector):  # type: ignore[misc]
    """Start a proxy with the cat-breeds-3sources spec pointing at Claude."""
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
        "plugins": [
            "tracing",
            "claude-frontend",
            "claude-backend",
            "url4-specs",
            "url4-executor",
            "data-store",
        ],
        "plugin_config": {
            "tracing": {
                "phoenix_launch": False,
                "otlp_endpoint": otlp_collector.endpoint,
            },
            "claude-frontend": {
                "active_spec": "cat-breeds-3sources",
                "upstream_url": "https://httpbin.org/anything",
                "listen_host": "127.0.0.1",
                "listen_port": proxy_port,
            },
            "claude-backend": {
                "default_model": "claude-sonnet-4-20250514",
            },
            "url4-specs": {
                "specs": {
                    "cat-breeds-3sources": {
                        "expression": CAT_SPEC_EXPRESSION,
                    },
                },
            },
        },
    }

    mgr = ServerManager(config, session_id="e2e-cat-breeds")
    mgr.start(timeout=30)
    if not ServerManager.wait_for_port(proxy_port):
        mgr.stop()
        raise RuntimeError(f"Cat breeds proxy not listening on port {proxy_port}")
    yield mgr, proxy_port
    mgr.stop()


@pytest.mark.e2e
@pytest.mark.timeout(120)
class TestCatBreedsFullPipeline:
    """Full pipeline: proxy → /claude → 3 sources → Claude CLI → user message."""

    @pytest.fixture(autouse=True)
    def _require_claude(self):
        if not shutil.which("claude"):
            pytest.skip("Claude CLI not found in PATH")

    def test_cat_breeds_through_proxy(
        self,
        cat_proxy: tuple[ServerManager, int],
        otlp_collector: OTLPCollector,
    ):
        """Send a prompt about cats, verify Claude processes the 3 sources."""
        _, proxy_port = cat_proxy
        client = ClaudeCodeClient(proxy_url=f"http://127.0.0.1:{proxy_port}")

        # Long timeout: fetches 3 GitHub files + Claude CLI processing
        resp = client.send_message(
            "What breed of cat is best for apartments?",
            timeout=90,
        )

        assert resp.status_code == 200

        # The response is echoed by httpbin — check the forwarded user message
        user_text = resp.last_user_text

        # The user message should contain the original prompt
        assert "apartment" in user_text.lower(), (
            f"Original prompt missing from user message: {user_text[:300]}"
        )

        # The user message should contain Claude's response about cat breeds
        # (the /claude endpoint processes the 3 sources and returns analysis)
        assert len(user_text) > 100, (
            f"User message too short ({len(user_text)} chars) — "
            f"Claude response may not have been injected: {user_text[:300]}"
        )

    def test_cat_breeds_trace_shows_3_fetches(
        self,
        cat_proxy: tuple[ServerManager, int],
        otlp_collector: OTLPCollector,
    ):
        """Trace should show 3 parallel url4.fetch spans for the GitHub sources."""
        _, proxy_port = cat_proxy
        otlp_collector.clear()

        client = ClaudeCodeClient(proxy_url=f"http://127.0.0.1:{proxy_port}")
        client.send_message("List some cat breeds")

        import time

        time.sleep(8)
        spans = otlp_collector.wait_for_spans(5, timeout=15)

        fetch_spans = otlp_collector.find_spans(name="url4.fetch")
        fetched_urls = [s.attributes.get("http.url", "") for s in fetch_spans]

        assert len(fetch_spans) >= 3, (
            f"Expected 3+ url4.fetch spans (one per source), got {len(fetch_spans)}. "
            f"URLs: {fetched_urls}. All spans: {[s.name for s in spans]}"
        )
