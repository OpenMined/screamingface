"""Unit tests for noisy-path trace muting (SF-278).

Two-phase design: the server_request_hook *marks* muted-path spans
``_sf.internal`` at span start, and ``_FilteringSpanProcessor`` *decides*
whether to drop them at span end based on the ``mute_internal`` flag.
"""

from __future__ import annotations

from screamingface.plugins.tracing.plugin import (
    DEFAULT_MUTED_PATH_PATTERNS,
    _FilteringSpanProcessor,
    _is_muted_path,
    _make_server_request_hook,
)


class _FakeInner:
    """Minimal SpanProcessor stand-in recording forwarded spans."""

    def __init__(self) -> None:
        self.ended: list[object] = []

    def on_start(self, span, parent_context=None) -> None:  # noqa: ANN001, ARG002
        pass

    def on_end(self, span) -> None:  # noqa: ANN001
        self.ended.append(span)

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:  # noqa: ARG002
        return True


class _FakeSpan:
    def __init__(self, name: str, attributes: dict | None = None, *, recording: bool = True):
        self.name = name
        self.attributes = attributes if attributes is not None else {}
        self._recording = recording

    def is_recording(self) -> bool:
        return self._recording

    def set_attribute(self, key: str, value: object) -> None:
        self.attributes[key] = value


# ---------------------------------------------------------------------------
# _FilteringSpanProcessor
# ---------------------------------------------------------------------------


def test_mutes_internal_spans_when_enabled() -> None:
    inner = _FakeInner()
    proc = _FilteringSpanProcessor(inner, mute_internal=True)
    proc.on_end(_FakeSpan("GET /claude/auth/connections", {"_sf.internal": True}))
    assert inner.ended == []


def test_forwards_internal_spans_when_disabled() -> None:
    inner = _FakeInner()
    proc = _FilteringSpanProcessor(inner, mute_internal=False)
    span = _FakeSpan("GET /claude/auth/connections", {"_sf.internal": True})
    proc.on_end(span)
    assert inner.ended == [span]


def test_asgi_noise_always_dropped_regardless_of_flag() -> None:
    for mute in (True, False):
        inner = _FakeInner()
        proc = _FilteringSpanProcessor(inner, mute_internal=mute)
        proc.on_end(_FakeSpan("http send", {}))
        proc.on_end(_FakeSpan("http receive", {}))
        assert inner.ended == []


def test_normal_spans_always_forwarded() -> None:
    inner = _FakeInner()
    proc = _FilteringSpanProcessor(inner, mute_internal=True)
    span = _FakeSpan("POST /v1/messages", {"sf.plugin": "claude-frontend"})
    proc.on_end(span)
    assert inner.ended == [span]


# ---------------------------------------------------------------------------
# _is_muted_path (default patterns, method-aware)
# ---------------------------------------------------------------------------


def test_default_patterns_mute_polling_gets() -> None:
    muted = [
        "/health",
        "/claude/health",
        "/gemini/health",
        "/claude/auth/connections",
        "/codex/auth/connections",
        "/claude/auth/connections/abc-123",
        "/eval_runs/550e8400-e29b-41d4-a716-446655440000",
    ]
    for path in muted:
        assert _is_muted_path(path, "GET", DEFAULT_MUTED_PATH_PATTERNS), path


def test_default_patterns_keep_real_endpoints() -> None:
    kept = ["/v1/messages", "/ensemble", "/eval_runs", "/backends/status", "/data/abc"]
    for path in kept:
        assert not _is_muted_path(path, "GET", DEFAULT_MUTED_PATH_PATTERNS), path


def test_mutations_are_not_muted() -> None:
    # Same paths, non-GET methods — connecting/deleting must stay visible.
    assert not _is_muted_path("/claude/auth/connections", "POST", DEFAULT_MUTED_PATH_PATTERNS)
    assert not _is_muted_path("/eval_runs/abc", "DELETE", DEFAULT_MUTED_PATH_PATTERNS)
    assert not _is_muted_path(
        "/claude/auth/connections/x/refresh", "POST", DEFAULT_MUTED_PATH_PATTERNS
    )


# ---------------------------------------------------------------------------
# server_request_hook
# ---------------------------------------------------------------------------


def test_hook_marks_muted_paths() -> None:
    hook = _make_server_request_hook(DEFAULT_MUTED_PATH_PATTERNS)
    for path in ("/health", "/claude/auth/connections", "/eval_runs/abc"):
        span = _FakeSpan("server")
        hook(span, {"path": path, "method": "GET"})
        assert span.attributes.get("_sf.internal") is True, path


def test_hook_does_not_mark_real_paths_and_records_query() -> None:
    hook = _make_server_request_hook(DEFAULT_MUTED_PATH_PATTERNS)
    span = _FakeSpan("server")
    hook(span, {"path": "/ensemble", "method": "GET", "query_string": b"q=hi"})
    assert "_sf.internal" not in span.attributes
    assert span.attributes.get("http.query_string") == "q=hi"
