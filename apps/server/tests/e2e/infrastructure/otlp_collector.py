"""Lightweight in-process OTLP HTTP collector for capturing spans in tests.

Runs an ``http.server`` in a daemon thread that accepts
``POST /v1/traces`` with protobuf-encoded ``ExportTraceServiceRequest``
bodies, deserializes them, and stores the spans for assertion.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any


@dataclass
class CollectedSpan:
    """A single span received by the collector."""

    name: str
    trace_id: str
    span_id: str
    parent_span_id: str | None
    attributes: dict[str, Any]
    start_time_ns: int
    end_time_ns: int
    status_code: int  # 0=UNSET, 1=OK, 2=ERROR
    kind: int  # SpanKind enum value
    events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def duration_ms(self) -> float:
        return (self.end_time_ns - self.start_time_ns) / 1_000_000


def _bytes_to_hex(b: bytes) -> str:
    return b.hex()


def _extract_attribute_value(kv: Any) -> Any:
    """Extract a typed value from an OTLP KeyValue's ``value`` field."""
    v = kv.value
    if v.HasField("string_value"):
        return v.string_value
    if v.HasField("int_value"):
        return v.int_value
    if v.HasField("double_value"):
        return v.double_value
    if v.HasField("bool_value"):
        return v.bool_value
    if v.HasField("bytes_value"):
        return v.bytes_value
    if v.HasField("array_value"):
        return [_extract_attribute_value_inner(el) for el in v.array_value.values]
    return str(v)


def _extract_attribute_value_inner(v: Any) -> Any:
    """Extract value from an AnyValue (used in array elements)."""
    if v.HasField("string_value"):
        return v.string_value
    if v.HasField("int_value"):
        return v.int_value
    if v.HasField("double_value"):
        return v.double_value
    if v.HasField("bool_value"):
        return v.bool_value
    return str(v)


def _parse_spans(body: bytes) -> list[CollectedSpan]:
    """Deserialize protobuf ExportTraceServiceRequest into CollectedSpan list."""
    from opentelemetry.proto.collector.trace.v1 import trace_service_pb2

    request = trace_service_pb2.ExportTraceServiceRequest.FromString(body)
    spans: list[CollectedSpan] = []

    for resource_spans in request.resource_spans:
        for scope_spans in resource_spans.scope_spans:
            for span in scope_spans.spans:
                attrs = {}
                for kv in span.attributes:
                    attrs[kv.key] = _extract_attribute_value(kv)

                events = []
                for event in span.events:
                    event_attrs = {}
                    for kv in event.attributes:
                        event_attrs[kv.key] = _extract_attribute_value(kv)
                    events.append(
                        {
                            "name": event.name,
                            "timestamp_ns": event.time_unix_nano,
                            "attributes": event_attrs,
                        }
                    )

                parent_id = _bytes_to_hex(span.parent_span_id)
                spans.append(
                    CollectedSpan(
                        name=span.name,
                        trace_id=_bytes_to_hex(span.trace_id),
                        span_id=_bytes_to_hex(span.span_id),
                        parent_span_id=parent_id if parent_id != "0" * 16 else None,
                        attributes=attrs,
                        start_time_ns=span.start_time_unix_nano,
                        end_time_ns=span.end_time_unix_nano,
                        status_code=span.status.code,
                        kind=span.kind,
                        events=events,
                    )
                )

    return spans


class _OTLPHandler(BaseHTTPRequestHandler):
    """HTTP handler that accepts OTLP trace exports."""

    collector: OTLPCollector  # set by OTLPCollector before serving

    def do_POST(self) -> None:
        if self.path != "/v1/traces":
            self.send_response(404)
            self.end_headers()
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            spans = _parse_spans(body)
            self.server._collector.add_spans(spans)  # type: ignore[attr-defined]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b"{}")
        except Exception as exc:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(exc).encode())

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress HTTP access logs during tests
        pass


class OTLPCollector:
    """In-process OTLP HTTP collector for test span capture."""

    def __init__(self, port: int = 0) -> None:
        self._port = port
        self._spans: list[CollectedSpan] = []
        self._lock = threading.Lock()
        self._new_span_event = threading.Event()
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> int:
        """Start the collector server. Returns the bound port."""
        self._server = HTTPServer(("127.0.0.1", self._port), _OTLPHandler)
        self._server._collector = self  # type: ignore[attr-defined]
        self._port = self._server.server_address[1]

        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self._port

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server = None
        self._thread = None

    @property
    def endpoint(self) -> str:
        """OTLP endpoint URL for server config."""
        return f"http://127.0.0.1:{self._port}/v1/traces"

    @property
    def spans(self) -> list[CollectedSpan]:
        with self._lock:
            return list(self._spans)

    def add_spans(self, spans: list[CollectedSpan]) -> None:
        """Called by the HTTP handler to add received spans."""
        with self._lock:
            self._spans.extend(spans)
        self._new_span_event.set()

    def wait_for_spans(self, count: int, timeout: float = 15) -> list[CollectedSpan]:
        """Block until at least *count* spans have been received."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if len(self._spans) >= count:
                    return list(self._spans)
            self._new_span_event.clear()
            remaining = deadline - time.monotonic()
            if remaining > 0:
                self._new_span_event.wait(timeout=min(remaining, 0.5))
        with self._lock:
            return list(self._spans)

    def find_spans(
        self,
        name: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> list[CollectedSpan]:
        """Filter spans by name substring and/or attribute key-value pairs."""
        with self._lock:
            result = list(self._spans)
        if name:
            result = [s for s in result if name in s.name]
        if attributes:
            for k, v in attributes.items():
                result = [s for s in result if s.attributes.get(k) == v]
        return result

    def get_children(self, parent_span_id: str) -> list[CollectedSpan]:
        """Return all spans whose parent is *parent_span_id*."""
        with self._lock:
            return [s for s in self._spans if s.parent_span_id == parent_span_id]

    def clear(self) -> None:
        """Clear all collected spans."""
        with self._lock:
            self._spans.clear()
        self._new_span_event.clear()
