"""End-to-end tests for the filtered ``$prompt`` context blob.

These tests exercise the full pipeline:

    ClaudeCodeClient (emulated CLI)
        ↓
    claude-frontend proxy (subprocess, with backend_url → main SF server)
        ↓ POST /data (filtered JSON blob)
    main SF server (subprocess)
        ↓ context.key span attribute → OTLP collector
    test reads span → fetches /data/<key> → asserts blob JSON

Every test spawns its own proxy subprocess via ``custom_proxy_factory`` so
the proxy can be configured with an arbitrary ``context_filter``. The shared
``proxy_server`` fixture from conftest.py is intentionally NOT used here —
that fixture runs the proxy without ``backend_url`` (in-process url4
resolution), which is the right setup for trace-structure tests but the
wrong one for inspecting stored blobs from the test process.
"""

from __future__ import annotations

import httpx
import pytest

from tests.e2e.infrastructure.claude_code_client import ClaudeCodeClient
from tests.e2e.infrastructure.otlp_collector import CollectedSpan, OTLPCollector
from tests.e2e.infrastructure.server_manager import ServerManager

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(60)]


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


def _build_tool_call_history(client: ClaudeCodeClient) -> None:
    """Drive the client through a multi-turn tool_use / tool_result exchange.

    The resulting client history (after the second user turn) looks like:
        [user] "List the python files."
        [assistant] tool_use(Bash, ls *.py)
        [user] tool_result(file listing)
    """
    client.send_message("List the python files.", track_history=True)
    client.inject_assistant_response(
        [
            {"type": "text", "text": "Listing now."},
            {
                "type": "tool_use",
                "id": "tu_e2e_01",
                "name": "Bash",
                "input": {"command": "ls *.py"},
            },
        ]
    )


def _wait_for_prompt_span(
    collector: OTLPCollector,
    *,
    after_unix_ns: int = 0,
    timeout: float = 10,
) -> CollectedSpan:
    """Block until a ``url4.$prompt`` span newer than *after_unix_ns* arrives.

    Async OTLP export means stale spans from earlier requests can land late.
    Filtering by start_time defends against picking up the wrong span when
    multiple requests are issued in quick succession.
    """
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        candidates = [
            s
            for s in collector.find_spans(name="url4.$prompt")
            if s.start_time_ns >= after_unix_ns
        ]
        if candidates:
            # Return the latest span by start time (most recent request)
            return max(candidates, key=lambda s: s.start_time_ns)
        time.sleep(0.1)
    raise AssertionError(
        f"No url4.$prompt span (after {after_unix_ns}ns) observed within {timeout}s. "
        f"Collected span names: {[s.name for s in collector.spans]}"
    )


def _now_ns() -> int:
    """Wall-clock nanoseconds — matches OTel start_time_unix_nano."""
    import time

    return time.time_ns()


def _fetch_blob_json(main_server_base_url: str, key: str) -> tuple[dict, str]:
    """GET /data/<key> from the main SF server. Returns (parsed_json, content_type)."""
    resp = httpx.get(f"{main_server_base_url}/data/{key}", timeout=10)
    resp.raise_for_status()
    return resp.json(), resp.headers.get("content-type", "")


def _user_blocks(blob: dict) -> list[dict]:
    out: list[dict] = []
    for msg in blob.get("messages", []):
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            out.append({"type": "text", "text": content})
        elif isinstance(content, list):
            out.extend(content)
    return out


def _assistant_blocks(blob: dict) -> list[dict]:
    out: list[dict] = []
    for msg in blob.get("messages", []):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if isinstance(content, list):
            out.extend(content)
    return out


# ----------------------------------------------------------------------------
# Custom-filter proxy fixture factory
# ----------------------------------------------------------------------------


@pytest.fixture
def custom_proxy_factory(
    sf_server: ServerManager,
    main_server_port: int,
    otlp_collector: OTLPCollector,
):
    """Spawn a per-test proxy server with a custom context_filter.

    Returns a callable ``factory(context_filter, expression=...) -> (proxy_url, ServerManager)``
    that the test should use to bring up an isolated proxy. Each call gets its
    own free port. The fixture tears down all spawned servers after the test.
    """
    spawned: list[ServerManager] = []

    def _make(
        context_filter: list[str],
        *,
        expression: str = "(https://httpbin.org/robots.txt)!$prompt",
    ) -> tuple[str, ServerManager]:
        proxy_port = ServerManager.find_free_port()
        config = {
            "version": "0.1.0",
            "server": {
                "host": "127.0.0.1",
                "port": ServerManager.find_free_port(),  # internal-only
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
                    "active_spec": "filter-test-spec",
                    "upstream_url": "https://httpbin.org/anything",
                    "listen_host": "127.0.0.1",
                    "listen_port": proxy_port,
                    "backend_url": f"http://127.0.0.1:{main_server_port}",
                    "context_filter": context_filter,
                },
                "url4-specs": {
                    "specs": {
                        "filter-test-spec": {"expression": expression},
                    },
                },
            },
        }
        mgr = ServerManager(config, session_id=f"e2e-filter-{proxy_port}")
        mgr.start(timeout=30)
        if not ServerManager.wait_for_port(proxy_port, timeout=10):
            mgr.stop()
            raise RuntimeError(f"Custom proxy not listening on port {proxy_port}")
        spawned.append(mgr)
        return f"http://127.0.0.1:{proxy_port}", mgr

    yield _make

    for mgr in spawned:
        mgr.stop()


# ----------------------------------------------------------------------------
# Default-filter (reuses session-scoped proxy_server with default ['user:text'])
# ----------------------------------------------------------------------------


class TestDefaultFilter:
    """Default filter ['user:text'] — uses a custom-spawned proxy with backend_url."""

    def test_blob_is_application_json(
        self,
        custom_proxy_factory,
        otlp_collector: OTLPCollector,
        sf_server: ServerManager,
    ) -> None:
        """Filtered $prompt is stored as application/json, not text/plain."""
        proxy_url, _ = custom_proxy_factory(["user:text"])
        client = ClaudeCodeClient(proxy_url=proxy_url)

        cutoff = _now_ns()
        resp = client.send_message("List the python files.")
        assert resp.status_code == 200

        prompt_span = _wait_for_prompt_span(otlp_collector, after_unix_ns=cutoff)
        blob_key = prompt_span.attributes.get("context.key")
        assert blob_key, f"context.key missing on span: {prompt_span.attributes}"

        blob, content_type = _fetch_blob_json(sf_server.base_url, blob_key)
        assert "application/json" in content_type
        assert isinstance(blob, dict)

    def test_default_filter_captures_user_text_only(
        self,
        custom_proxy_factory,
        otlp_collector: OTLPCollector,
        sf_server: ServerManager,
    ) -> None:
        """Default filter ['user:text'] keeps user text, drops system/tools."""
        proxy_url, _ = custom_proxy_factory(["user:text"])
        client = ClaudeCodeClient(proxy_url=proxy_url)

        cutoff = _now_ns()
        client.send_message("Hello world from e2e test.")

        prompt_span = _wait_for_prompt_span(otlp_collector, after_unix_ns=cutoff)
        blob_key = prompt_span.attributes["context.key"]
        blob, _ = _fetch_blob_json(sf_server.base_url, blob_key)

        assert "system" not in blob
        assert "tools" not in blob
        user_text = " ".join(b.get("text", "") for b in _user_blocks(blob))
        assert "Hello world from e2e test." in user_text
        # No assistant content
        assert _assistant_blocks(blob) == []

    def test_span_carries_filter_metadata(
        self,
        custom_proxy_factory,
        otlp_collector: OTLPCollector,
    ) -> None:
        """The url4.$prompt span carries filter / size / message_count attrs."""
        proxy_url, _ = custom_proxy_factory(["user:text"])
        client = ClaudeCodeClient(proxy_url=proxy_url)

        cutoff = _now_ns()
        client.send_message("Span attribute check.")
        prompt_span = _wait_for_prompt_span(otlp_collector, after_unix_ns=cutoff)

        attrs = prompt_span.attributes
        assert attrs.get("context.filter") == "user:text"
        assert isinstance(attrs.get("context.size_bytes"), int)
        assert attrs.get("context.size_bytes", 0) > 0
        assert isinstance(attrs.get("context.message_count"), int)
        assert attrs.get("context.message_count", 0) >= 1
        assert attrs.get("context.has_system") is False
        assert attrs.get("context.has_tools") is False


# ----------------------------------------------------------------------------
# Custom-filter cases (each spawns its own proxy subprocess)
# ----------------------------------------------------------------------------


class TestCustomFilters:
    """Per-test proxies with overridden context_filter."""

    def test_reflection_filter_captures_tool_use_and_result(
        self,
        custom_proxy_factory,
        otlp_collector: OTLPCollector,
        sf_server: ServerManager,
    ) -> None:
        """['user:text,tool_result', 'assistant:text,tool_call'] full reflection slice."""
        proxy_url, _ = custom_proxy_factory(
            ["user:text,tool_result", "assistant:text,tool_call"]
        )
        client = ClaudeCodeClient(proxy_url=proxy_url)

        # Drive a multi-turn exchange ending with tool_result so the filter
        # has assistant tool_use AND user tool_result to keep.
        _build_tool_call_history(client)
        cutoff = _now_ns()
        resp = client.send_tool_result("tu_e2e_01", "alpha.py\nbeta.py\n")
        assert resp.status_code == 200

        prompt_span = _wait_for_prompt_span(otlp_collector, after_unix_ns=cutoff)
        blob_key = prompt_span.attributes["context.key"]
        blob, _ = _fetch_blob_json(sf_server.base_url, blob_key)

        user_types = {b["type"] for b in _user_blocks(blob)}
        asst_types = {b["type"] for b in _assistant_blocks(blob)}
        assert user_types == {"text", "tool_result"}
        assert asst_types == {"text", "tool_use"}

        # The actual tool_result content survives
        tool_results = [b for b in _user_blocks(blob) if b["type"] == "tool_result"]
        assert any("alpha.py" in str(b.get("content", "")) for b in tool_results)

    def test_assistant_tool_call_only(
        self,
        custom_proxy_factory,
        otlp_collector: OTLPCollector,
        sf_server: ServerManager,
    ) -> None:
        """['assistant:tool_call'] keeps only what Claude is calling."""
        proxy_url, _ = custom_proxy_factory(["assistant:tool_call"])
        client = ClaudeCodeClient(proxy_url=proxy_url)

        _build_tool_call_history(client)
        cutoff = _now_ns()
        resp = client.send_tool_result("tu_e2e_01", "alpha.py\n")
        assert resp.status_code == 200

        prompt_span = _wait_for_prompt_span(otlp_collector, after_unix_ns=cutoff)
        blob_key = prompt_span.attributes["context.key"]
        blob, _ = _fetch_blob_json(sf_server.base_url, blob_key)

        # Only assistant messages with tool_use survive
        assert all(m["role"] == "assistant" for m in blob.get("messages", []))
        types = {b["type"] for b in _assistant_blocks(blob)}
        assert types == {"tool_use"}
        # System and tools are NOT in the blob
        assert "system" not in blob
        assert "tools" not in blob

    def test_full_dump_includes_system_and_tools(
        self,
        custom_proxy_factory,
        otlp_collector: OTLPCollector,
        sf_server: ServerManager,
    ) -> None:
        """system:* tools:* user:* assistant:* — everything is captured."""
        proxy_url, _ = custom_proxy_factory(
            ["system:*", "tools:*", "user:*", "assistant:*"]
        )
        client = ClaudeCodeClient(proxy_url=proxy_url)

        cutoff = _now_ns()
        resp = client.send_message(
            "Full dump test prompt.",
            system="You are an e2e test assistant.",
            tools=[
                {
                    "name": "Bash",
                    "description": "shell",
                    "input_schema": {"type": "object", "properties": {}},
                }
            ],
        )
        assert resp.status_code == 200

        prompt_span = _wait_for_prompt_span(otlp_collector, after_unix_ns=cutoff)
        blob_key = prompt_span.attributes["context.key"]
        blob, _ = _fetch_blob_json(sf_server.base_url, blob_key)

        assert "system" in blob
        assert "tools" in blob
        assert blob["tools"][0]["name"] == "Bash"
        # Filter span attribute lists all four scopes
        assert "system:*" in prompt_span.attributes["context.filter"]
        assert prompt_span.attributes.get("context.has_system") is True
        assert prompt_span.attributes.get("context.has_tools") is True

    def test_empty_filter_skips_blob_creation(
        self,
        custom_proxy_factory,
        otlp_collector: OTLPCollector,
    ) -> None:
        """Empty filter [] — proxy short-circuits, no blob and no $prompt span."""
        proxy_url, _ = custom_proxy_factory([])
        client = ClaudeCodeClient(proxy_url=proxy_url)

        cutoff = _now_ns()
        resp = client.send_message("This should not produce a blob.")
        assert resp.status_code == 200

        # The proxy must NOT have entered the $prompt block, so no
        # url4.$prompt span should be emitted for THIS request. Older
        # spans from previous tests are filtered out by the cutoff.
        # Wait briefly to flush the OTLP exporter.
        import time

        time.sleep(2)
        prompt_spans = [
            s
            for s in otlp_collector.find_spans(name="url4.$prompt")
            if s.start_time_ns >= cutoff
        ]
        assert prompt_spans == [], (
            f"Empty filter should skip $prompt processing, but got "
            f"{len(prompt_spans)} url4.$prompt span(s) after cutoff"
        )
