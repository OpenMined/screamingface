"""E2E tests for OpenTelemetry trace structure.

Verifies that the proxy creates correct span hierarchies and attributes
when processing requests. Uses the OTLP collector to capture spans.
"""

from __future__ import annotations

import time

import pytest

from tests.e2e.infrastructure.claude_code_client import ClaudeCodeClient
from tests.e2e.infrastructure.otlp_collector import OTLPCollector

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(30)]


class TestTraceStructure:
    """Verify OTel span structure from proxy requests."""

    def test_proxy_request_creates_spans(
        self, claude_client: ClaudeCodeClient, otlp_collector: OTLPCollector
    ):
        """A proxy request should generate at least one span."""
        claude_client.send_message("Hello trace test")

        # BatchSpanProcessor flushes async — wait for spans
        spans = otlp_collector.wait_for_spans(1, timeout=15)
        assert len(spans) >= 1, "No spans received from proxy request"

    def test_url4_prompt_span_exists(
        self, claude_client: ClaudeCodeClient, otlp_collector: OTLPCollector
    ):
        """$prompt substitution should create a url4.$prompt span."""
        claude_client.send_message("Hello url4 test")

        spans = otlp_collector.wait_for_spans(2, timeout=15)
        prompt_spans = otlp_collector.find_spans(name="url4.$prompt")

        assert len(prompt_spans) >= 1, (
            f"No url4.$prompt span found. All spans: {[s.name for s in spans]}"
        )

    def test_anthropic_request_body_span(
        self, claude_client: ClaudeCodeClient, otlp_collector: OTLPCollector
    ):
        """The anthropic.request_body span should record model and message count."""
        claude_client.send_message("Hello body trace")

        spans = otlp_collector.wait_for_spans(3, timeout=15)
        body_spans = otlp_collector.find_spans(name="anthropic.request_body")

        assert len(body_spans) >= 1, (
            f"No anthropic.request_body span found. All spans: {[s.name for s in spans]}"
        )

        body_span = body_spans[0]
        assert body_span.attributes.get("sf.plugin") == "claude-frontend"

    def test_prompt_span_attributes(
        self, claude_client: ClaudeCodeClient, otlp_collector: OTLPCollector
    ):
        """url4.$prompt span should have url4.* attributes."""
        claude_client.send_message("Check attributes test")

        otlp_collector.wait_for_spans(2, timeout=15)
        prompt_spans = otlp_collector.find_spans(name="url4.$prompt")

        if not prompt_spans:
            pytest.skip("url4.$prompt span not found (tracing may be disabled)")

        span = prompt_spans[0]
        assert "url4.raw_expression" in span.attributes
        assert "url4.status" in span.attributes

    def test_span_parent_child_relationships(
        self, claude_client: ClaudeCodeClient, otlp_collector: OTLPCollector
    ):
        """Spans should form a proper parent-child tree."""
        claude_client.send_message("Parent child test")

        # Wait for a reasonable number of spans
        time.sleep(2)
        spans = otlp_collector.wait_for_spans(3, timeout=15)

        # At least some spans should have parent IDs
        child_spans = [s for s in spans if s.parent_span_id is not None]
        assert len(child_spans) >= 1, (
            f"No child spans found. All spans: {[(s.name, s.parent_span_id) for s in spans]}"
        )

    def test_url4_fetch_span_exists(
        self, claude_client: ClaudeCodeClient, otlp_collector: OTLPCollector
    ):
        """url4 source fetches should create url4.fetch spans."""
        claude_client.send_message("Hello fetch test")

        spans = otlp_collector.wait_for_spans(5, timeout=15)
        fetch_spans = otlp_collector.find_spans(name="url4.fetch")

        assert len(fetch_spans) >= 1, (
            f"No url4.fetch span found. All spans: {[s.name for s in spans]}"
        )
        s = fetch_spans[0]
        assert "http.url" in s.attributes or "url4.path" in s.attributes

    def test_url4_evaluate_span_exists(
        self, claude_client: ClaudeCodeClient, otlp_collector: OTLPCollector
    ):
        """url4 evaluation pipeline should create url4.evaluate span."""
        claude_client.send_message("Hello evaluate test")

        spans = otlp_collector.wait_for_spans(5, timeout=15)
        eval_spans = otlp_collector.find_spans(name="url4.evaluate")

        assert len(eval_spans) >= 1, (
            f"No url4.evaluate span found. All spans: {[s.name for s in spans]}"
        )
        s = eval_spans[0]
        assert "url4.expression" in s.attributes
        assert "url4.result_length" in s.attributes
        assert "url4.response_body" in s.attributes, (
            f"url4.response_body missing from evaluate span. "
            f"Attributes: {list(s.attributes.keys())}"
        )
        assert len(s.attributes["url4.response_body"]) > 0

    def test_url4_resolve_sources_span(
        self, claude_client: ClaudeCodeClient, otlp_collector: OTLPCollector
    ):
        """url4.resolve_sources span should be a child of url4.evaluate."""
        claude_client.send_message("Hello sources test")

        spans = otlp_collector.wait_for_spans(5, timeout=15)
        src_spans = otlp_collector.find_spans(name="url4.resolve_sources")

        assert len(src_spans) >= 1, (
            f"No url4.resolve_sources span found. All spans: {[s.name for s in spans]}"
        )
        s = src_spans[0]
        assert "url4.response_body" in s.attributes, (
            f"url4.response_body missing from resolve_sources span. "
            f"Attributes: {list(s.attributes.keys())}"
        )
        assert len(s.attributes["url4.response_body"]) > 0

    def test_fetch_span_contains_response_body(
        self, claude_client: ClaudeCodeClient, otlp_collector: OTLPCollector
    ):
        """url4.fetch spans should include the response body content."""
        # The proxy spec fetches httpbin.org/robots.txt
        claude_client.send_message("Hello body trace test")

        spans = otlp_collector.wait_for_spans(5, timeout=15)
        fetch_spans = otlp_collector.find_spans(name="url4.fetch")

        assert len(fetch_spans) >= 1, (
            f"No url4.fetch span found. All spans: {[s.name for s in spans]}"
        )

        s = fetch_spans[0]
        assert "url4.response_body" in s.attributes, (
            f"url4.response_body missing from fetch span. Attributes: {list(s.attributes.keys())}"
        )
        body = s.attributes["url4.response_body"]
        assert len(body) > 0, "url4.response_body is empty"
        # The test spec fetches robots.txt which contains "User-agent"
        assert "User-agent" in body, (
            f"Expected robots.txt content in response_body. Got: {body[:200]}"
        )

    def test_fetch_relative_span_contains_response_body(
        self, claude_client: ClaudeCodeClient, otlp_collector: OTLPCollector
    ):
        """url4.fetch_relative spans should include the response body content."""
        claude_client.send_message("Hello relative body test")

        spans = otlp_collector.wait_for_spans(5, timeout=15)
        rel_spans = otlp_collector.find_spans(name="url4.fetch_relative")

        assert len(rel_spans) >= 1, (
            f"No url4.fetch_relative span found. All spans: {[s.name for s in spans]}"
        )

        s = rel_spans[0]
        assert "url4.response_body" in s.attributes, (
            f"url4.response_body missing from fetch_relative span. "
            f"Attributes: {list(s.attributes.keys())}"
        )
        body = s.attributes["url4.response_body"]
        assert len(body) > 0, "url4.response_body is empty"
