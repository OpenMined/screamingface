"""E2E tests for claude-frontend proxy context injection.

Migrated from test_e2e_claude_frontend.py — tests that the proxy correctly
injects url4-resolved context into the system prompt (static spec, no $prompt).
Uses httpbin /anything as upstream echo server.
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.claude_code_client import ClaudeCodeClient

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="session")
def static_proxy_config(otlp_collector, proxy_server_port):
    """Proxy config using a static spec (no $prompt) for system-prompt injection."""
    from tests.e2e.infrastructure.server_manager import ServerManager

    main_port = ServerManager.find_free_port()
    return {
        "version": "0.1.0",
        "server": {
            "host": "127.0.0.1",
            "port": main_port,
            "ssl": False,
            "reload": False,
        },
        "plugins": [
            "tracing",
            "claude-frontend",
            "url4-specs",
            "url4-executor",
        ],
        "plugin_config": {
            "tracing": {
                "phoenix_launch": False,
                "otlp_endpoint": otlp_collector.endpoint,
            },
            "claude-frontend": {
                "active_spec": "httpbin-robots",
                "upstream_url": "https://httpbin.org/anything",
                "listen_host": "127.0.0.1",
                "listen_port": proxy_server_port + 100,
                "embed_target": "system",
            },
            "url4-specs": {
                "specs": {
                    "httpbin-robots": {
                        "expression": "(https://httpbin.org/robots.txt)!"
                        "'You are an API testing assistant'",
                    },
                },
            },
        },
    }


@pytest.fixture(scope="session")
def static_proxy(static_proxy_config, proxy_server_port):
    """Start a proxy with static spec (context → system prompt)."""
    from tests.e2e.infrastructure.server_manager import ServerManager

    mgr = ServerManager(static_proxy_config, session_id="e2e-static")
    mgr.start(timeout=30)
    listen_port = proxy_server_port + 100
    if not ServerManager.wait_for_port(listen_port):
        mgr.stop()
        raise RuntimeError(f"Static proxy not listening on port {listen_port}")
    yield mgr, listen_port
    mgr.stop()


@pytest.fixture
def static_client(static_proxy):
    _, port = static_proxy
    client = ClaudeCodeClient(proxy_url=f"http://127.0.0.1:{port}")
    yield client
    client.reset()


@pytest.mark.timeout(30)
class TestStaticContextInjection:
    """Tests for static spec (no $prompt) — context injected into system prompt."""

    def test_context_injection_with_string_system(self, static_client: ClaudeCodeClient):
        """url4 context + original system prompt both present in forwarded request."""
        resp = static_client.send_message("Hello", system="Be helpful")

        assert resp.status_code == 200

        system = str(resp.forwarded_system)
        assert "User-agent" in system, f"url4 source content missing: {system[:200]}"
        assert "Be helpful" in system, f"original system prompt missing: {system[:200]}"
        assert "API testing assistant" in system, f"intent text missing: {system[:200]}"

    def test_context_injection_no_system(self, static_client: ClaudeCodeClient):
        """url4 context injected even when no system prompt provided."""
        resp = static_client.send_message("Hello")

        assert resp.status_code == 200

        system = str(resp.forwarded_system)
        assert "User-agent" in system, f"url4 source content missing: {system[:200]}"
        assert "API testing assistant" in system, f"intent text missing: {system[:200]}"

    def test_extra_fields_passthrough(self, static_client: ClaudeCodeClient):
        """Custom fields in the request body survive proxying."""
        resp = static_client.send_message(
            "Hello",
            extra_body={"custom_field": "should_survive"},
        )

        assert resp.status_code == 200
        assert resp.echoed_body.get("custom_field") == "should_survive"
