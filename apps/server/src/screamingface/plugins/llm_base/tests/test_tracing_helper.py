"""Unit tests for the shared provider HTTP-span helper (SF-278)."""

from __future__ import annotations

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind

from screamingface.plugins.llm_base._tracing import set_provider_attrs, traced_provider_post


@pytest.fixture
def exporter() -> InMemorySpanExporter:
    """Attach an in-memory exporter to the active SDK tracer provider.

    Works whether or not a provider is already installed: if the global
    provider isn't an SDK ``TracerProvider`` we create and install one.
    """
    exp = InMemorySpanExporter()
    provider = trace.get_tracer_provider()
    if not isinstance(provider, TracerProvider):
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
    provider.add_span_processor(SimpleSpanProcessor(exp))
    exp.clear()
    return exp


def test_traced_provider_post_creates_client_span(exporter: InMemorySpanExporter) -> None:
    with traced_provider_post("anthropic", "https://api.anthropic.com/v1/messages"):
        set_provider_attrs(
            {"http.status_code": 200, "gen_ai.request.model": "claude", "absent": None}
        )

    spans = [s for s in exporter.get_finished_spans() if s.name == "llm.POST anthropic"]
    assert len(spans) == 1
    span = spans[0]
    attrs = dict(span.attributes or {})
    assert span.kind == SpanKind.CLIENT
    assert attrs["sf.plugin"] == "anthropic"
    assert attrs["http.method"] == "POST"
    assert str(attrs["http.url"]).startswith("https://api.anthropic.com")
    assert attrs["http.status_code"] == 200
    assert attrs["gen_ai.request.model"] == "claude"
    # None-valued attributes are skipped (OTel rejects None).
    assert "absent" not in attrs


def test_method_param_changes_span_name(exporter: InMemorySpanExporter) -> None:
    with traced_provider_post("aigw", "http://127.0.0.1:9105/v1/auth", method="GET"):
        pass
    names = [s.name for s in exporter.get_finished_spans()]
    assert "llm.GET aigw" in names


def test_exception_inside_span_is_recorded(exporter: InMemorySpanExporter) -> None:
    with pytest.raises(ValueError):  # noqa: PT012, SIM117
        with traced_provider_post("ollama", "http://localhost:11434/api/chat"):
            raise ValueError("boom")
    spans = [s for s in exporter.get_finished_spans() if s.name == "llm.POST ollama"]
    assert len(spans) == 1
    # OTel records the exception as a span event on context exit.
    assert any(e.name == "exception" for e in spans[0].events)
