"""OpenRouter discovery source identity and cardinality limits."""

from __future__ import annotations

import json

import pytest

from aigateway.core.parameter_discovery import DiscoveryError, RawResponse
from aigateway.plugins.openrouter_provider.discovery import (
    CHAT_REQUEST_SCHEMA,
    MODELS_URL,
    OPENAPI_URL,
    discover_openrouter_snapshot,
    parse_model_catalog_observations,
    parse_openapi_endpoint_observations,
)

_MODEL = "anthropic/claude-fable-5"


class _Client:
    def __init__(self, bodies: dict[str, object]) -> None:
        self._bodies = bodies

    async def get(self, url: str, *, timeout_s: float, max_bytes: int) -> RawResponse:
        del timeout_s, max_bytes
        return RawResponse(
            status=200,
            content_type="application/json",
            body=json.dumps(self._bodies[url]),
        )


def test_chat_request_schema_name_is_pinned_to_live_literal() -> None:
    assert CHAT_REQUEST_SCHEMA == "ChatRequest"


@pytest.mark.asyncio
async def test_missing_openapi_schema_raises_instead_of_caching_fresh_silence() -> None:
    client = _Client(
        {
            MODELS_URL: {"data": [{"id": _MODEL, "supported_parameters": []}]},
            OPENAPI_URL: {"components": {"schemas": {}}},
        }
    )

    with pytest.raises(DiscoveryError) as excinfo:
        await discover_openrouter_snapshot(_MODEL, client=client)

    assert excinfo.value.reason == "schema_not_found"


@pytest.mark.asyncio
async def test_empty_openapi_schema_raises_instead_of_caching_fresh_silence() -> None:
    client = _Client(
        {
            MODELS_URL: {"data": [{"id": _MODEL, "supported_parameters": []}]},
            OPENAPI_URL: {"components": {"schemas": {"ChatRequest": {"properties": {}}}}},
        }
    )

    with pytest.raises(DiscoveryError) as excinfo:
        await discover_openrouter_snapshot(_MODEL, client=client)

    assert excinfo.value.reason == "schema_not_found"


def test_model_catalog_count_is_bounded() -> None:
    catalog = {
        "data": [
            {"id": f"author/model-{index}", "supported_parameters": ["temperature"]}
            for index in range(10_001)
        ]
    }

    with pytest.raises(DiscoveryError) as excinfo:
        parse_model_catalog_observations(catalog, upstream_model_id="author/model-0")

    assert excinfo.value.reason == "model_catalog_too_large"


def test_catalog_parameter_vocabulary_is_bounded() -> None:
    parameters = [f"parameter_{index}" for index in range(513)]
    catalog = {"data": [{"id": _MODEL, "supported_parameters": parameters}]}

    with pytest.raises(DiscoveryError) as excinfo:
        parse_model_catalog_observations(catalog, upstream_model_id=_MODEL)

    assert excinfo.value.reason == "parameter_catalog_too_large"


def test_catalog_parameter_vocabulary_is_bounded_across_models() -> None:
    catalog = {
        "data": [
            {
                "id": _MODEL,
                "supported_parameters": [f"first_{index}" for index in range(300)],
            },
            {
                "id": "another/model",
                "supported_parameters": [f"second_{index}" for index in range(300)],
            },
        ]
    }

    with pytest.raises(DiscoveryError) as excinfo:
        parse_model_catalog_observations(catalog, upstream_model_id=_MODEL)

    assert excinfo.value.reason == "parameter_catalog_too_large"


def test_openapi_request_property_count_is_bounded() -> None:
    openapi: dict[str, object] = {
        "components": {
            "schemas": {
                "ChatRequest": {"properties": {f"parameter_{index}": {} for index in range(513)}}
            }
        }
    }

    with pytest.raises(DiscoveryError) as excinfo:
        parse_openapi_endpoint_observations(openapi, schema_name="ChatRequest")

    assert excinfo.value.reason == "openapi_schema_too_large"
