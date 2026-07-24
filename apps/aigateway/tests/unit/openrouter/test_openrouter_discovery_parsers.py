"""Phase 6a (OME-479 §6.1): pure OpenRouter public-catalog discovery parsers.

FEATURE: OpenRouter P0 observation overlay. These tests pin the PURE parsers that
turn OpenRouter's two fixed public documents into raw evidence, BEFORE any network
fetch (that seam is a later step). Fixtures mirror the verified live shape.

INVARIANT (§5.1): endpoint evidence (what the API accepts) and per-model evidence
(what one model supports) stay DISTINCT — never conflated into one support verdict.
INVARIANT (§5.3): a model absent from the catalog, or a malformed row, yields NO
observations — honest absence, never fabricated support.
"""

from __future__ import annotations

from aigateway.core.chat_parameters import ProviderDiscoverySnapshot, ProviderParameterObservation
from aigateway.plugins.openrouter_provider.discovery import (
    parse_model_catalog_observations,
    parse_openapi_endpoint_observations,
)

_MODEL = "google/gemini-2.0-flash-001"

# Representative slice of the verified live /api/v1/models shape.
_CATALOG = {
    "data": [
        {
            "id": _MODEL,
            "name": "Google: Gemini 2.0 Flash",
            "context_length": 1_000_000,
            "architecture": {
                "modality": "text+image->text",
                "input_modalities": ["text", "image"],
                "output_modalities": ["text"],
                "tokenizer": "Gemini",
            },
            "top_provider": {
                "context_length": 1_000_000,
                "max_completion_tokens": 8192,
                "is_moderated": False,
            },
            "supported_parameters": [
                "max_tokens",
                "temperature",
                "top_p",
                "top_k",
                "frequency_penalty",
                "presence_penalty",
                "seed",
                "stop",
                "tools",
                "tool_choice",
                "repetition_penalty",
            ],
        },
        {
            "id": "anthropic/claude-fable-5",
            "name": "Anthropic: Claude Fable 5",
            "supported_parameters": ["max_tokens", "temperature", "top_p"],
        },
    ]
}

# Minimal standard OpenAPI-3 fragment: the request-body schema's properties are the
# endpoint-accepted fields (OpenRouter publishes OpenAPI 3.0 under components.schemas).
_OPENAPI_SCHEMA = "ChatCompletionRequest"
_OPENAPI = {
    "openapi": "3.0.0",
    "components": {
        "schemas": {
            _OPENAPI_SCHEMA: {
                "type": "object",
                "properties": {
                    "model": {"type": "string"},
                    "messages": {"type": "array"},
                    "stream": {"type": "boolean"},
                    "temperature": {"type": "number"},
                    "top_p": {"type": "number"},
                    "top_k": {"type": "integer"},
                    "max_tokens": {"type": "integer"},
                },
            }
        }
    },
}


def _paths(obs: tuple[ProviderParameterObservation, ...]) -> set[str]:
    return {o.request_path for o in obs}


def test_model_catalog_extracts_supported_parameters() -> None:
    obs = parse_model_catalog_observations(_CATALOG, upstream_model_id=_MODEL)
    paths = _paths(obs)
    # standard OpenAI-compatible fields keep their identity path
    assert {"temperature", "top_p", "max_tokens", "tools", "tool_choice"} <= paths
    # every observation is per-model evidence, positively supported
    assert all(o.source == "openrouter:models" for o in obs)
    assert all(o.support == "supported" for o in obs)


def test_native_param_maps_to_provider_params_wrapper_path() -> None:
    obs = parse_model_catalog_observations(_CATALOG, upstream_model_id=_MODEL)
    paths = _paths(obs)
    # top_k is OpenRouter-native; AIGateway addresses it via the wrapper, so its
    # observation must align with the rule path provider_params.top_k.
    assert "provider_params.top_k" in paths
    assert "top_k" not in paths  # never surfaced under the bare native name


def test_standard_param_keeps_identity_path() -> None:
    obs = parse_model_catalog_observations(_CATALOG, upstream_model_id=_MODEL)
    # top_p is standard OpenAI — NOT wrapped.
    assert "top_p" in _paths(obs)
    assert "provider_params.top_p" not in _paths(obs)


def test_model_absent_from_catalog_yields_no_observations() -> None:
    # honest absence: no fabricated support for a model the catalog does not list.
    assert parse_model_catalog_observations(_CATALOG, upstream_model_id="nope/not-real") == ()


def test_malformed_catalog_is_bounded_not_raised() -> None:
    assert parse_model_catalog_observations({}, upstream_model_id=_MODEL) == ()
    assert parse_model_catalog_observations({"data": "x"}, upstream_model_id=_MODEL) == ()
    assert (
        parse_model_catalog_observations(
            {"data": [{"id": _MODEL, "supported_parameters": "nope"}]},
            upstream_model_id=_MODEL,
        )
        == ()
    )
    # a non-string entry inside the list is skipped, not raised
    obs = parse_model_catalog_observations(
        {"data": [{"id": _MODEL, "supported_parameters": ["temperature", 5, None]}]},
        upstream_model_id=_MODEL,
    )
    assert _paths(obs) == {"temperature"}


def test_duplicate_supported_param_is_deduped() -> None:
    obs = parse_model_catalog_observations(
        {"data": [{"id": _MODEL, "supported_parameters": ["temperature", "temperature"]}]},
        upstream_model_id=_MODEL,
    )
    assert len([o for o in obs if o.request_path == "temperature"]) == 1


def test_observations_are_deterministically_ordered() -> None:
    obs = parse_model_catalog_observations(_CATALOG, upstream_model_id=_MODEL)
    paths = [o.request_path for o in obs]
    assert paths == sorted(paths)


def test_openapi_extracts_endpoint_params_excluding_gateway_owned() -> None:
    obs = parse_openapi_endpoint_observations(_OPENAPI, schema_name=_OPENAPI_SCHEMA)
    paths = _paths(obs)
    # endpoint-accepted optional fields present
    assert {"temperature", "top_p", "max_tokens", "provider_params.top_k"} <= paths
    # required-protocol / gateway-owned fields are NOT model-parameter evidence
    assert "model" not in paths
    assert "messages" not in paths
    assert "stream" not in paths
    assert all(o.source == "openrouter:openapi" for o in obs)


def test_openapi_missing_schema_is_bounded_not_raised() -> None:
    assert parse_openapi_endpoint_observations({}, schema_name=_OPENAPI_SCHEMA) == ()
    assert parse_openapi_endpoint_observations(_OPENAPI, schema_name="Nonexistent") == ()


def test_endpoint_and_model_evidence_stay_distinct() -> None:
    # Phase 6 task 2: a field accepted by the endpoint AND supported by the model
    # produces TWO observations with DIFFERENT sources — never merged into one.
    endpoint = parse_openapi_endpoint_observations(_OPENAPI, schema_name=_OPENAPI_SCHEMA)
    model = parse_model_catalog_observations(_CATALOG, upstream_model_id=_MODEL)
    ep_temp = [o for o in endpoint if o.request_path == "temperature"]
    md_temp = [o for o in model if o.request_path == "temperature"]
    assert len(ep_temp) == 1 and len(md_temp) == 1
    assert ep_temp[0].source == "openrouter:openapi"
    assert md_temp[0].source == "openrouter:models"


def test_snapshot_keeps_endpoint_and_model_evidence_in_separate_fields() -> None:
    endpoint = parse_openapi_endpoint_observations(_OPENAPI, schema_name=_OPENAPI_SCHEMA)
    model = parse_model_catalog_observations(_CATALOG, upstream_model_id=_MODEL)
    snap = ProviderDiscoverySnapshot(
        source_revision="or-rev-1",
        endpoint_observations=endpoint,
        model_observations=model,
    )
    assert snap.endpoint_observations == endpoint
    assert snap.model_observations == model
    # frozen value object — distinctness cannot be mutated away. `.get` is the
    # type-safe read of the non-total ConfigDict; `is True` keeps the assertion.
    assert snap.model_config.get("frozen") is True
