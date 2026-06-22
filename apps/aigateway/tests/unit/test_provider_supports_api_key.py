"""Per-provider API-key capability flag (SF-291).

The desktop UI is capability-driven: it only offers the API-key option for
providers whose gateway plugin reports ``supports_api_key()``. Anthropic and
Gemini accept raw keys; Codex rides the ChatGPT subscription endpoint and does
not.
"""

from __future__ import annotations

from aigateway.plugins.anthropic_provider.plugin import PLUGIN as ANTHROPIC
from aigateway.plugins.codex_provider.plugin import PLUGIN as CODEX
from aigateway.plugins.gemini_provider.plugin import PLUGIN as GEMINI
from aigateway.plugins.ollama_provider.plugin import PLUGIN as OLLAMA


def test_anthropic_supports_api_key() -> None:
    assert ANTHROPIC.supports_api_key() is True


def test_gemini_supports_api_key() -> None:
    assert GEMINI.supports_api_key() is True


def test_codex_does_not_support_api_key() -> None:
    assert CODEX.supports_api_key() is False


def test_ollama_does_not_support_api_key() -> None:
    # Ollama is local/no-auth; it does not take a provider API key.
    assert OLLAMA.supports_api_key() is False
