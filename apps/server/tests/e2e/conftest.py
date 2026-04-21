"""E2E test fixtures — server lifecycle, OTLP collector, Claude Code client."""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest

from tests.e2e.infrastructure.claude_code_client import ClaudeCodeClient
from tests.e2e.infrastructure.otlp_collector import OTLPCollector
from tests.e2e.infrastructure.server_manager import ServerManager

# ---------------------------------------------------------------------------
# Auto-skip e2e_live tests without API key
# ---------------------------------------------------------------------------


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if has_api_key:
        return
    skip_marker = pytest.mark.skip(reason="ANTHROPIC_API_KEY not set")
    for item in items:
        if "e2e_live" in item.keywords:
            item.add_marker(skip_marker)


# ---------------------------------------------------------------------------
# OTLP Collector (session-scoped)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def otlp_collector() -> Generator[OTLPCollector, None, None]:
    collector = OTLPCollector()
    collector.start()
    yield collector
    collector.stop()


# ---------------------------------------------------------------------------
# Server configs
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def main_server_port() -> int:
    return ServerManager.find_free_port()


@pytest.fixture(scope="session")
def proxy_server_port() -> int:
    return ServerManager.find_free_port()


@pytest.fixture(scope="session")
def main_server_config(otlp_collector: OTLPCollector, main_server_port: int) -> dict:
    """Config for the main SF server (url4 resolution, data-store)."""
    return {
        "version": "0.1.0",
        "server": {
            "host": "127.0.0.1",
            "port": main_server_port,
            "ssl": False,
            "reload": False,
        },
        "plugins": ["tracing", "url4-executor", "url4-specs", "data-store"],
        "plugin_config": {
            "tracing": {
                "phoenix_launch": False,
                "otlp_endpoint": otlp_collector.endpoint,
            },
        },
    }


@pytest.fixture(scope="session")
def proxy_server_config(
    otlp_collector: OTLPCollector,
    main_server_port: int,
    proxy_server_port: int,
) -> dict:
    """Config for the session proxy (claude-frontend → httpbin echo)."""
    return {
        "version": "0.1.0",
        "server": {
            "host": "127.0.0.1",
            "port": main_server_port + 1,  # internal server port
            "ssl": False,
            "reload": False,
        },
        "plugins": [
            "tracing",
            "claude-frontend",
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
                "active_spec": "test-prompt-spec",
                "upstream_url": "https://httpbin.org/anything",
                "listen_host": "127.0.0.1",
                "listen_port": proxy_server_port,
            },
            "url4-specs": {
                "specs": {
                    "test-static-spec": {
                        "expression": "(https://httpbin.org/robots.txt)!'Be helpful'",
                    },
                    "test-prompt-spec": {
                        "expression": "(https://httpbin.org/robots.txt)!$prompt",
                    },
                },
            },
        },
    }


# ---------------------------------------------------------------------------
# Server lifecycle (session-scoped)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def sf_server(main_server_config: dict) -> Generator[ServerManager, None, None]:
    """Main SF server (url4-executor, data-store). Started once per session."""
    mgr = ServerManager(main_server_config)
    mgr.start(timeout=30)
    yield mgr
    mgr.stop()


@pytest.fixture(scope="session")
def proxy_server(
    proxy_server_config: dict,
    sf_server: ServerManager,  # noqa: ARG001 — ensure main server starts first
    proxy_server_port: int,
) -> Generator[ServerManager, None, None]:
    """Session proxy (claude-frontend → httpbin). Started once per session."""
    mgr = ServerManager(proxy_server_config, session_id="e2e-test")
    mgr.start(timeout=60)
    # Wait for the proxy port to be listening
    if not ServerManager.wait_for_port(proxy_server_port, timeout=60):
        last_logs = "\n".join(mgr.logs.dump_last()) if mgr.logs else "<no logs>"
        mgr.stop()
        raise RuntimeError(
            f"Proxy not listening on port {proxy_server_port}\nLast server log lines:\n{last_logs}"
        )
    yield mgr
    mgr.stop()


@pytest.fixture(scope="session")
def proxy_url(proxy_server_port: int) -> str:
    return f"http://127.0.0.1:{proxy_server_port}"


# ---------------------------------------------------------------------------
# Claude Code client (per-test)
# ---------------------------------------------------------------------------


@pytest.fixture
def claude_client(
    proxy_url: str,
    proxy_server: ServerManager,  # noqa: ARG001 — ensures servers are running
) -> Generator[ClaudeCodeClient, None, None]:
    client = ClaudeCodeClient(proxy_url=proxy_url)
    yield client
    client.reset()


# ---------------------------------------------------------------------------
# Span clearing (per-test, autouse)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_spans(otlp_collector: OTLPCollector) -> None:
    otlp_collector.clear()
