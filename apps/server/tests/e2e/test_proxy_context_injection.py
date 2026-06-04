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
def static_proxy_config(otlp_collector, proxy_server_port, httpbin_url):
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
                "upstream_url": f"{httpbin_url}/anything",
                "listen_host": "127.0.0.1",
                "listen_port": proxy_server_port + 100,
                "embed_target": "system",
            },
            "url4-specs": {
                "specs": {
                    "httpbin-robots": {
                        "expression": (
                            f"({httpbin_url}/robots.txt)!'You are an API testing assistant'"
                        ),
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
    mgr.start(timeout=60)
    listen_port = proxy_server_port + 100
    if not ServerManager.wait_for_port(listen_port, timeout=60):
        last_logs = "\n".join(mgr.logs.dump_last()) if mgr.logs else "<no logs>"
        mgr.stop()
        raise RuntimeError(
            f"Static proxy not listening on port {listen_port}\nLast server log lines:\n{last_logs}"
        )
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
    """Tests for the static spec (no $prompt) under the terminal cutover.

    The proxy no longer forwards. The static spec
    ``(robots.txt)!'You are an API testing assistant'`` resolves in-process to
    its terminal text (intent + fetched robots.txt) and *becomes* the response
    body. The client-sent ``system`` and extra body fields have no upstream to
    land in, so they are ignored — assertions now target ``response_text``.
    """

    def test_context_injection_with_string_system(self, static_client: ClaudeCodeClient):
        """url4 context (source + intent) is the resolved terminal response text.

        The client ``system`` ("Be helpful") is ignored — there is no upstream to
        merge it into — so it is no longer asserted.
        """
        resp = static_client.send_message("Hello", system="Be helpful")

        assert resp.status_code == 200

        text = resp.response_text
        assert "User-agent" in text, f"url4 source content missing: {text[:200]}"
        assert "API testing assistant" in text, f"intent text missing: {text[:200]}"

    def test_context_injection_no_system(self, static_client: ClaudeCodeClient):
        """url4 context is resolved into the response even when no system prompt is sent."""
        resp = static_client.send_message("Hello")

        assert resp.status_code == 200

        text = resp.response_text
        assert "User-agent" in text, f"url4 source content missing: {text[:200]}"
        assert "API testing assistant" in text, f"intent text missing: {text[:200]}"

    def test_extra_fields_tolerated(self, static_client: ClaudeCodeClient):
        """Unknown extra body fields are tolerated by the terminal handler.

        The terminal path does not forward, so extra fields cannot be echoed
        back. Instead assert they are accepted without error: a well-formed
        Anthropic message envelope is still returned (status 200, ``type`` =
        ``message``) and the resolved url4 context is present.
        """
        resp = static_client.send_message(
            "Hello",
            extra_body={"custom_field": "should_survive"},
        )

        assert resp.status_code == 200
        assert resp.body["type"] == "message"
        assert resp.body["role"] == "assistant"
        assert "User-agent" in resp.response_text
