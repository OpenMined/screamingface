from __future__ import annotations

import asyncio
import logging

import httpx
import pytest

from aigateway.core.api_key_validation import (
    ApiKeyValidationStage,
    ApiKeyValidationState,
)
from aigateway.plugins.anthropic_provider.api_key_validation import AnthropicApiKeyValidator
from aigateway.plugins.anthropic_provider.settings import AnthropicPluginSettings
from aigateway.plugins.huggingface_provider.api_key_validation import HuggingFaceApiKeyValidator
from aigateway.plugins.huggingface_provider.settings import HuggingFacePluginSettings

_ANTHROPIC_KEY = "sk-ant-api03-parallel-isolation-secret"
_HUGGINGFACE_KEY = "hf_parallel_isolation_secret"


class _OverlapBarrier:
    def __init__(self) -> None:
        self.arrivals = 0
        self._ready = asyncio.Event()

    async def wait(self) -> None:
        self.arrivals += 1
        if self.arrivals == 2:
            self._ready.set()
        await self._ready.wait()


@pytest.mark.asyncio
async def test_parallel_validations_isolate_keys_clients_results_and_logs(caplog) -> None:
    barrier = _OverlapBarrier()
    anthropic_requests: list[httpx.Request] = []
    huggingface_requests: list[httpx.Request] = []

    async def anthropic_handler(request: httpx.Request) -> httpx.Response:
        anthropic_requests.append(request)
        if len(anthropic_requests) == 1:
            await barrier.wait()
            return httpx.Response(200, json={"data": []})
        return httpx.Response(200, json={"type": "message", "content": []})

    async def huggingface_handler(request: httpx.Request) -> httpx.Response:
        huggingface_requests.append(request)
        await barrier.wait()
        return httpx.Response(401, json={"error": "invalid"})

    anthropic_settings = AnthropicPluginSettings()
    anthropic = AnthropicApiKeyValidator(
        settings=anthropic_settings,
        registered_models=list(anthropic_settings.models),
        transport=httpx.MockTransport(anthropic_handler),
    )
    huggingface = HuggingFaceApiKeyValidator(
        settings=HuggingFacePluginSettings(),
        transport=httpx.MockTransport(huggingface_handler),
    )

    with caplog.at_level(logging.DEBUG):
        anthropic_result, huggingface_result = await asyncio.gather(
            anthropic.validate(_ANTHROPIC_KEY),
            huggingface.validate(_HUGGINGFACE_KEY),
        )

    assert barrier.arrivals == 2
    assert anthropic_result.state is ApiKeyValidationState.VALID
    assert anthropic_result.stage is ApiKeyValidationStage.READINESS
    assert huggingface_result.state is ApiKeyValidationState.INVALID
    assert huggingface_result.stage is ApiKeyValidationStage.AUTHENTICATION
    assert [request.url.host for request in anthropic_requests] == ["api.anthropic.com"] * 2
    assert [request.url.host for request in huggingface_requests] == ["huggingface.co"]
    assert all(request.headers["x-api-key"] == _ANTHROPIC_KEY for request in anthropic_requests)
    assert all(
        request.headers["authorization"] == f"Bearer {_HUGGINGFACE_KEY}"
        for request in huggingface_requests
    )
    evidence = caplog.text + repr(anthropic_result) + repr(huggingface_result)
    assert _ANTHROPIC_KEY not in evidence
    assert _HUGGINGFACE_KEY not in evidence
