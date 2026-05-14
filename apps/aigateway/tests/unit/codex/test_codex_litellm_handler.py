from __future__ import annotations

from typing import cast

import litellm
import pytest
from litellm.llms.custom_llm import CustomLLMError
from litellm.types.utils import ModelResponse

from aigateway.plugins.codex_provider import litellm_handler as handler_module
from aigateway.plugins.codex_provider.litellm_handler import HANDLER
from aigateway.plugins.codex_provider.oauth_config import CODEX_CHATGPT_RESPONSES_URL


async def _completion(api_key: str, optional_params: dict | None = None) -> ModelResponse:
    return await HANDLER.acompletion(
        model="codex/gpt-5.4-mini",
        messages=[
            {"role": "system", "content": "Be concise."},
            {"role": "user", "content": "Hello"},
        ],
        api_base="",
        custom_prompt_dict={},
        model_response=ModelResponse(),
        print_verbose=lambda *args, **kwargs: None,
        encoding=None,
        api_key=api_key,
        logging_obj=None,
        optional_params=optional_params or {},
    )


@pytest.mark.asyncio
async def test_codex_handler_builds_allowed_chatgpt_payload(monkeypatch) -> None:
    captured: dict = {}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url, *, json, headers):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return handler_module.httpx.Response(
                200,
                text=(
                    'data: {"type":"response.output_text.delta","delta":"hel"}\n\n'
                    'data: {"type":"response.output_text.delta","delta":"lo"}\n\n'
                    'data: {"type":"response.completed","response":{}}\n\n'
                ),
            )

    monkeypatch.setattr(handler_module.httpx, "AsyncClient", FakeAsyncClient)

    response = await _completion(
        "oauth-token-1",
        {
            "extra_headers": {"ChatGPT-Account-Id": "acct-1"},
            "max_tokens": 100,
            "temperature": 0.5,
            "metadata": {"drop": True},
            "reasoning": {"effort": "high"},
        },
    )

    assert captured["url"] == CODEX_CHATGPT_RESPONSES_URL
    assert captured["headers"]["Authorization"] == "Bearer oauth-token-1"
    assert captured["headers"]["ChatGPT-Account-Id"] == "acct-1"
    assert captured["json"]["model"] == "gpt-5.4-mini"
    assert captured["json"]["instructions"] == "Be concise."
    assert captured["json"]["stream"] is True
    assert captured["json"]["store"] is False
    assert captured["json"]["reasoning"] == {"effort": "high"}
    assert "max_tokens" not in captured["json"]
    assert "temperature" not in captured["json"]
    assert "metadata" not in captured["json"]
    assert response.choices[0].message.content == "hello"
    assert response.model == "codex/gpt-5.4-mini"


@pytest.mark.asyncio
async def test_litellm_dispatches_codex_slug_to_custom_handler(monkeypatch) -> None:
    captured: dict = {}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url, *, json, headers):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return handler_module.httpx.Response(
                200,
                text='data: {"type":"response.output_text.delta","delta":"custom"}\n\n',
            )

    monkeypatch.setattr(handler_module.httpx, "AsyncClient", FakeAsyncClient)

    response = cast(
        ModelResponse,
        await litellm.acompletion(
            model="codex/gpt-5.4-mini",
            messages=[{"role": "user", "content": "hi"}],
            api_key="oauth-token-1",
            reasoning={"effort": "high"},
        ),
    )

    assert captured["url"] == CODEX_CHATGPT_RESPONSES_URL
    assert captured["json"]["model"] == "gpt-5.4-mini"
    assert captured["json"]["reasoning"] == {"effort": "high"}
    assert response.choices[0].message.content == "custom"
    assert response.model == "codex/gpt-5.4-mini"


@pytest.mark.asyncio
async def test_codex_handler_rejects_openai_api_keys_before_network(monkeypatch) -> None:
    def _unexpected_client(*args, **kwargs):
        raise AssertionError("network client should not be constructed")

    monkeypatch.setattr(handler_module.httpx, "AsyncClient", _unexpected_client)

    with pytest.raises(CustomLLMError) as exc_info:
        await _completion("sk-proj-test")

    assert exc_info.value.status_code == 400
    assert "not available via OpenAI API key" in str(exc_info.value)
