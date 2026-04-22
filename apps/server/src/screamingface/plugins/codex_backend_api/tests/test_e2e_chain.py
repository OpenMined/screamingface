"""End-to-end test: url4 expression -> url4-executor -> codex-backend-api -> result.

Tests the full chain from a url4 expression containing /codex()!intent
through the ensemble dispatch to the OpenAI Responses API.

Requires:
  - OPENAI_API_KEY env var set (Codex OAuth tokens lack API scopes)
  - CODEX_E2E=1 env var to opt in

Run with:
    OPENAI_API_KEY=sk-... CODEX_E2E=1 uv run pytest \
        src/screamingface/plugins/codex_backend_api/tests/test_e2e_chain.py -v
"""

from __future__ import annotations

import os

import httpx
import pytest

from screamingface.plugins.codex_backend_api.adapter import OpenAIResponsesAdapter
from screamingface.plugins.codex_backend_api.auth import CodexOAuth
from screamingface.plugins.codex_backend_api.backend import OPENAI_RESPONSES_URL, OpenAIBackend
from screamingface.plugins.llm_base.messages import CoreMessage, TextPart

_SKIP_NO_KEY = "Set OPENAI_API_KEY for direct API access"
_SKIP_NO_ENV = "Set CODEX_E2E=1 to run e2e tests"

pytestmark = [
    pytest.mark.skipif(not os.environ.get("CODEX_E2E"), reason=_SKIP_NO_ENV),
    pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason=_SKIP_NO_KEY),
]


class TestDirectBackendCall:
    """Test OpenAIBackend.run() with a real OPENAI_API_KEY."""

    @pytest.mark.anyio
    async def test_simple_prompt_returns_text(self):
        """Send a minimal prompt and verify we get a text response back."""
        backend = OpenAIBackend()
        messages = [CoreMessage(role="user", content=[TextPart(text="Say 'hello world'")])]

        result = await backend.run(
            messages,
            model="o4-mini",
            system="Reply with exactly the text requested, nothing more.",
            max_tokens=20,
        )

        assert result.role == "assistant"
        text = _extract_text(result)
        assert len(text) > 0, "Expected non-empty response"
        assert "hello" in text.lower(), f"Expected 'hello' in response, got: {text}"

    @pytest.mark.anyio
    async def test_system_prompt_respected(self):
        """Verify the system/instructions prompt is sent and respected."""
        backend = OpenAIBackend()
        messages = [CoreMessage(role="user", content=[TextPart(text="What is 2+2?")])]

        result = await backend.run(
            messages,
            model="o4-mini",
            system="Always respond with exactly the word BANANA regardless of the question.",
            max_tokens=10,
        )

        text = _extract_text(result)
        assert "banana" in text.lower(), f"Expected 'BANANA' in response, got: {text}"


class TestAdapterRoundTrip:
    """Test adapter produces valid requests that the API accepts."""

    @pytest.mark.anyio
    async def test_adapter_output_accepted_by_api(self):
        """Build a request body via the adapter and send it directly."""
        adapter = OpenAIResponsesAdapter()
        auth = CodexOAuth()
        headers = await auth.get_authorization_header()
        headers["content-type"] = "application/json"

        messages = [CoreMessage(role="user", content=[TextPart(text="Say ok")])]
        body = adapter.to_provider_format(
            messages,
            model="o4-mini",
            system="Reply with exactly 'ok'",
            max_tokens=5,
        )

        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            resp = await client.post(
                OPENAI_RESPONSES_URL,
                json=body,
                headers=headers,
            )

        assert resp.status_code in (200, 429), f"API returned {resp.status_code}: {resp.text[:300]}"

        if resp.status_code == 200:
            result = adapter.from_provider_response(resp.json())
            assert result.role == "assistant"
            text = _extract_text(result)
            assert len(text) > 0


class TestInterpreterChain:
    """Test the interpreter (url4 intent -> backend -> result) flow."""

    @pytest.mark.anyio
    async def test_interpreter_process(self):
        """Test CodexBackendApiInterpreter.process() end-to-end."""
        from screamingface.plugins.codex_backend_api.interpreter import (
            CodexBackendApiInterpreter,
        )

        interpreter = CodexBackendApiInterpreter()
        result = await interpreter.process(
            sources="The capital of France is Paris.",
            intent="What is the capital of France?",
        )

        assert isinstance(result, str)
        assert len(result) > 0
        assert "paris" in result.lower(), f"Expected 'Paris' in response, got: {result}"


def _extract_text(msg: CoreMessage) -> str:
    """Pull concatenated text out of an assistant CoreMessage."""
    if isinstance(msg.content, str):
        return msg.content
    return "".join(p.text for p in msg.content if isinstance(p, TextPart))
