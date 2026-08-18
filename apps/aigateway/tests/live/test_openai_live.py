"""Owner-gated direct OpenAI API-key readiness smoke (OME-864).

Skipped unless AIGW_LIVE=1 and OPENAI_API_KEY are both present. The validation
request can consume quota; the credential is passed only to the production
validator and is never included in assertions.
"""

from __future__ import annotations

import os

import pytest

from aigateway.core.api_key_validation import ApiKeyValidationStage, ApiKeyValidationState
from aigateway.plugins.openai_provider.api_key_validation import OpenAIApiKeyValidator
from aigateway.plugins.openai_provider.settings import OpenAIPluginSettings

pytestmark = pytest.mark.live


def _live_enabled() -> bool:
    return os.environ.get("AIGW_LIVE") == "1"


def _live_openai_key() -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        pytest.skip("Live OpenAI test requires OPENAI_API_KEY")
    assert key is not None
    return key


@pytest.mark.skipif(not _live_enabled(), reason="AIGW_LIVE=1 not set")
@pytest.mark.asyncio
async def test_openai_api_key_reaches_reasoning_model_readiness() -> None:
    result = await OpenAIApiKeyValidator(settings=OpenAIPluginSettings()).validate(
        _live_openai_key()
    )

    # INVARIANT: a key is persistable only after the configured model produces
    # a structurally valid Chat Completions response, not after listing models.
    assert result.state is ApiKeyValidationState.VALID
    assert result.stage is ApiKeyValidationStage.READINESS
    assert result.probe_model == "openai/gpt-5-nano"
