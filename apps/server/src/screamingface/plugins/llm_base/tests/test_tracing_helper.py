"""Unit tests for the shared provider HTTP-span helper (SF-278)."""

from __future__ import annotations

import httpx
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind

from screamingface.plugins.llm_base._tracing import (
    record_llm_call,
    set_llm_io,
    set_provider_attrs,
    traced_provider_post,
)


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


# ---------------------------------------------------------------------------
# OpenInference LLM semantics (SF-278, 2nd commit)
# ---------------------------------------------------------------------------


def test_set_llm_io_marks_llm_kind_and_fields(exporter: InMemorySpanExporter) -> None:
    with traced_provider_post("aigw", "http://gw/v1/chat/completions"):
        set_llm_io(
            provider="aigw",
            input_value='{"model":"x"}',
            output_value="hi",
            model="x",
            prompt_tokens=3,
            completion_tokens=2,
        )
    spans = [s for s in exporter.get_finished_spans() if s.name == "llm.POST aigw"]
    assert len(spans) == 1
    attrs = dict(spans[0].attributes or {})
    assert attrs["openinference.span.kind"] == "LLM"
    assert attrs["llm.provider"] == "aigw"
    assert attrs["llm.model_name"] == "x"
    assert attrs["llm.token_count.prompt"] == 3
    assert attrs["llm.token_count.completion"] == 2
    assert attrs["input.value"] == '{"model":"x"}'
    assert attrs["output.value"] == "hi"


@pytest.mark.parametrize(
    ("usage_body", "want_prompt", "want_completion"),
    [
        ({"usage": {"prompt_tokens": 10, "completion_tokens": 5}}, 10, 5),  # OpenAI/gateway
        ({"usage": {"input_tokens": 8, "output_tokens": 4}}, 8, 4),  # Anthropic
        ({"usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 3}}, 7, 3),  # Gemini
    ],
)
def test_record_llm_call_extracts_tokens_across_shapes(
    exporter: InMemorySpanExporter, usage_body: dict, want_prompt: int, want_completion: int
) -> None:
    with traced_provider_post("p", "http://x"):
        record_llm_call("p", {"model": "m", "messages": []}, httpx.Response(200, json=usage_body))
    spans = [s for s in exporter.get_finished_spans() if s.name == "llm.POST p"]
    assert len(spans) == 1
    attrs = dict(spans[0].attributes or {})
    assert attrs["openinference.span.kind"] == "LLM"
    assert attrs["llm.model_name"] == "m"
    assert attrs["llm.token_count.prompt"] == want_prompt
    assert attrs["llm.token_count.completion"] == want_completion
    assert attrs["input.value"]  # request body serialized
    assert attrs["output.value"]  # response text captured
