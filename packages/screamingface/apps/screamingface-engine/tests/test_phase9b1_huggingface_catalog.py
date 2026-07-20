from __future__ import annotations

import json
from typing import cast

import httpx
import pytest

from screamingface_engine.app import create_app
from screamingface_engine.catalog import (
    PROVIDER_ROUTES,
    GatewayModel,
    ModelRoute,
    registry_document,
    resolve_model_routes,
)
from screamingface_engine.gateway import GatewayClient
from screamingface_engine.settings import Settings

GATEWAY_MODEL = "huggingface/deepseek-ai/DeepSeek-V4-Pro:deepinfra"
PUBLIC_MODEL = "huggingface/deepseek-ai/DeepSeek-V4-Pro~deepinfra"


def _route() -> ModelRoute:
    return resolve_model_routes((GatewayModel(GATEWAY_MODEL, "huggingface"),))[0]


def test_huggingface_provider_is_api_key_only_without_a_fake_callback() -> None:
    provider = next(item for item in PROVIDER_ROUTES if item.id == "huggingface")

    assert provider.display_name == "Hugging Face"
    assert provider.gateway_provider == "huggingface"
    assert provider.auth_methods == ("api_key",)
    assert provider.callback_path is None


def test_pinned_huggingface_model_gets_a_url4_safe_public_alias() -> None:
    route = _route()

    assert route == ModelRoute(
        id=PUBLIC_MODEL,
        gateway_model=GATEWAY_MODEL,
        provider="huggingface",
        tool_capabilities=(),
    )
    assert route.route == f"/{PUBLIC_MODEL}"


@pytest.mark.parametrize(
    "model_id",
    [
        "huggingface/deepseek-ai/DeepSeek-V4-Pro",
        "huggingface/deepseek-ai/DeepSeek-V4-Pro:",
        "huggingface//DeepSeek-V4-Pro:deepinfra",
        "huggingface/deepseek-ai/:deepinfra",
        "huggingface/deepseek-ai/family/DeepSeek-V4-Pro:deepinfra",
        "huggingface/deepseek-ai/DeepSeek~V4-Pro:deepinfra",
        "huggingface/deepseek-ai/DeepSeek-V4-Pro:deepinfra:extra",
        "huggingface/deepseek-ai/DeepSeek-V4-Pro:deepinfra/extra",
        "deepseek-ai/DeepSeek-V4-Pro:deepinfra",
    ],
)
def test_malformed_or_unpinned_huggingface_models_fail_catalog_resolution(
    model_id: str,
) -> None:
    with pytest.raises(ValueError, match="cannot derive public model ID"):
        resolve_model_routes((GatewayModel(model_id, "huggingface"),))


def test_duplicate_huggingface_public_aliases_fail_startup() -> None:
    model = GatewayModel(GATEWAY_MODEL, "huggingface")

    with pytest.raises(ValueError, match="duplicate public model ID"):
        resolve_model_routes((model, model))


def test_huggingface_registry_records_claim_no_tools_before_tavily() -> None:
    registry = registry_document((_route(),), enabled_tools=("web_search", "web_fetch"))

    assert registry["models"] == [
        {"id": PUBLIC_MODEL, "provider": "huggingface", "supported_tools": []}
    ]
    providers = cast(list[object], registry["providers"])
    assert {
        "id": "huggingface",
        "display_name": "Hugging Face",
        "auth_methods": ["api_key"],
    } in providers


@pytest.mark.asyncio
async def test_huggingface_public_route_dispatches_the_exact_gateway_pin() -> None:
    requests: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "answer"}}]})

    gateway = GatewayClient(
        "http://gateway.test", timeout=5, transport=httpx.MockTransport(handler)
    )
    app = create_app(
        model_routes=(_route(),),
        settings=Settings(gateway_url="http://gateway.test"),
        gateway=gateway,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        response = await client.get(f"/{PUBLIC_MODEL}", params={"q": "(Research this)"})
    await gateway.aclose()

    assert response.status_code == 200
    assert response.text == "answer"
    assert requests == [
        {
            "model": GATEWAY_MODEL,
            "messages": [{"role": "user", "content": "Research this"}],
        }
    ]
