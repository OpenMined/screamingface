"""E2E test fixtures — server lifecycle, OTLP collector, Claude Code client."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
import yaml

from tests.e2e.infrastructure.claude_code_client import ClaudeCodeClient
from tests.e2e.infrastructure.local_httpbin import LocalHttpbin
from tests.e2e.infrastructure.otlp_collector import OTLPCollector
from tests.e2e.infrastructure.server_manager import ServerManager

# ---------------------------------------------------------------------------
# Provider partitioning (for parallel e2e runs by provider queue)
# ---------------------------------------------------------------------------

_PROVIDERS = ("claude", "codex", "gemini", "multi", "other")
_DATA_DIR = Path(__file__).parent / "data"

# Files that target a specific provider exclusively. Files not listed are
# considered provider-agnostic and run only in the "multi" phase.
_PROVIDER_BY_FILE: dict[str, str] = {
    "test_proxy_context_injection.py": "claude",
    "test_proxy_multi_turn.py": "claude",
    "test_proxy_prompt_flow.py": "claude",
    "test_trace_structure.py": "claude",
    "test_cat_breeds_spec.py": "claude",
    "test_aigw_claude_e2e.py": "claude",
    "test_aigw_auth_e2e.py": "claude",
    "test_aigw_codex_auth_e2e.py": "codex",
    "test_url4_specs_live.py": "claude",
    "test_ensemble_features.py": "claude",
    "test_url4_resolution.py": "claude",
    # test_url4_matrix.py is classified per-test-id below.
}


def _build_matrix_id_map() -> dict[str, str]:
    """Map every YAML matrix test id to its provider folder."""
    out: dict[str, str] = {}
    if not _DATA_DIR.exists():
        return out
    for path in _DATA_DIR.rglob("*.yaml"):
        rel = path.relative_to(_DATA_DIR)
        provider = rel.parts[0] if len(rel.parts) > 1 else "other"
        try:
            cases = yaml.safe_load(path.read_text()) or []
        except Exception:
            continue
        for case in cases:
            cid = case.get("id")
            if cid:
                out[cid] = provider
    return out


_MATRIX_ID_PROVIDER = _build_matrix_id_map()


def _provider_for_item(item: pytest.Item) -> str:
    """Classify a collected test item to a provider bucket."""
    fname = Path(str(item.fspath)).name
    if fname == "test_url4_matrix.py":
        # Param id is wrapped in [brackets] at the end of nodeid
        nodeid = item.nodeid
        if "[" in nodeid and nodeid.endswith("]"):
            param = nodeid.rsplit("[", 1)[1][:-1]
            return _MATRIX_ID_PROVIDER.get(param, "multi")
        return "multi"
    return _PROVIDER_BY_FILE.get(fname, "multi")


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--provider",
        action="store",
        default=None,
        choices=[*_PROVIDERS, "all"],
        help=(
            "Run only e2e tests classified to the given provider queue. "
            "Used by scripts/run_e2e_parallel.sh to shard execution."
        ),
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    # 1) Auto-skip live tests without a Claude Code OAuth credential.
    from tests.e2e.infrastructure.claude_oauth import has_claude_code_oauth

    if not has_claude_code_oauth():
        skip_live = pytest.mark.skip(
            reason="Claude Code OAuth credential not found in macOS keychain"
        )
        for item in items:
            if "e2e_live" in item.keywords:
                item.add_marker(skip_live)

    # 2) Provider filter — deselect items not in the requested queue
    selected_provider = config.getoption("--provider")
    if not selected_provider or selected_provider == "all":
        return

    # The "multi" queue absorbs anything provider-agnostic ("other") too.
    multi_buckets = {"multi", "other"}
    keep, drop = [], []
    for item in items:
        bucket = _provider_for_item(item)
        if selected_provider == "multi":
            matched = bucket in multi_buckets
        else:
            matched = bucket == selected_provider
        if matched:
            keep.append(item)
        else:
            drop.append(item)
    if drop:
        config.hook.pytest_deselected(items=drop)
        items[:] = keep


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
def local_httpbin() -> Generator[LocalHttpbin, None, None]:
    """In-process httpbin mock — replaces httpbin.org for e2e tests.

    Eliminates the JSONDecodeError / 502 / DNS flake class that
    httpbin.org occasionally inflicts on CI.
    """
    hb = LocalHttpbin()
    hb.start()
    yield hb
    hb.stop()


@pytest.fixture(scope="session")
def httpbin_url(local_httpbin: LocalHttpbin) -> str:
    """Base URL of the local httpbin mock, e.g. ``http://127.0.0.1:54321``."""
    return local_httpbin.base_url


@pytest.fixture(scope="session")
def proxy_server_config(
    otlp_collector: OTLPCollector,
    main_server_port: int,
    proxy_server_port: int,
    httpbin_url: str,
) -> dict:
    """Config for the session proxy (claude-frontend → local httpbin echo)."""
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
                "upstream_url": f"{httpbin_url}/anything",
                "listen_host": "127.0.0.1",
                "listen_port": proxy_server_port,
            },
            "url4-specs": {
                "specs": {
                    "test-static-spec": {
                        "expression": f"({httpbin_url}/robots.txt)!'Be helpful'",
                    },
                    "test-prompt-spec": {
                        "expression": f"({httpbin_url}/robots.txt)!$prompt",
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
