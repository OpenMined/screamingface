"""Independent identity pins for OpenRouter's fixed discovery sources."""

from __future__ import annotations

from aigateway.plugins.openrouter_provider.discovery import (
    ALLOWED_ORIGINS,
    MODELS_URL,
    OPENAPI_URL,
)


def test_openrouter_discovery_sources_match_the_reviewed_literals() -> None:
    # INVARIANT: expected values stay independent of transport fixtures that consume
    # these constants, so a typo in a source cannot make both sides change together.
    assert MODELS_URL == "https://openrouter.ai/api/v1/models"
    assert OPENAPI_URL == "https://openrouter.ai/openapi.json"
    assert ALLOWED_ORIGINS == frozenset({"https://openrouter.ai"})
