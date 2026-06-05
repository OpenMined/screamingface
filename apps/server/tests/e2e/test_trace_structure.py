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

    def test_terminal_message_span_no_upstream_request_body(
        self, claude_client: ClaudeCodeClient, otlp_collector: OTLPCollector
    ):
        """Terminal /v1/messages emits the FastAPI server span + url4 spans, no upstream.

        Under the terminal cutover there is no upstream inference forward, so the
        old ``anthropic.request_body`` span no longer exists. Instead assert the
        terminal span set: the auto-instrumented ``POST /v1/messages`` server
        span (tagged ``sf.plugin=claude-frontend`` with the resolved
        ``url4.result_length``) plus the in-process ``url4.evaluate`` resolution
        span — and explicitly assert NO ``anthropic.request_body`` span.
        """
        claude_client.send_message("Hello body trace")

        spans = otlp_collector.wait_for_spans(3, timeout=15)
        all_names = [s.name for s in spans]

        # The upstream request-body span is GONE under the terminal cutover.
        assert otlp_collector.find_spans(name="anthropic.request_body") == [], (
            f"anthropic.request_body span should not exist under terminal cutover. "
            f"All spans: {all_names}"
        )

        # The terminal server span for the inference route exists and is tagged
        # by the frontend plugin (set via the handler's tracer.set_attrs).
        msg_spans = otlp_collector.find_spans(name="POST /v1/messages")
        assert len(msg_spans) >= 1, (
            f"No 'POST /v1/messages' server span found. All spans: {all_names}"
        )
        msg_span = msg_spans[0]
        assert msg_span.attributes.get("sf.plugin") == "claude-frontend"
        assert "url4.result_length" in msg_span.attributes, (
            f"resolved result length missing from server span. "
            f"Attributes: {list(msg_span.attributes.keys())}"
        )

        # The in-process url4 resolution span exists (terminal resolution ran).
        eval_spans = otlp_collector.find_spans(name="url4.evaluate")
        assert len(eval_spans) >= 1, f"No 'url4.evaluate' span found. All spans: {all_names}"

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
