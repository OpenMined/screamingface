"""OME-479 §6.1 — OpenRouter public-catalog discovery parsers (PURE).

FEATURE: OpenRouter P0 observation overlay. Turns OpenRouter's two FIXED public
documents into raw ``ProviderParameterObservation`` evidence:

- the per-model ``/api/v1/models`` catalog → per-model ``supported_parameters``;
- the public OpenAPI 3 document → the chat request schema's accepted fields.

INVARIANT (SOLID/hexagonal): these are pure functions over already-fetched,
already-bounded documents. They own NO network, NO clock, NO credentials — the
bounded transport (``core/parameter_discovery``) and the async provider hook
supply the documents. Keeping parsing pure makes every shape deterministic and
fixture-testable, and keeps the safety envelope in one place.

INVARIANT (§5.1): endpoint and per-model evidence carry DISTINCT source labels and
are never merged into one support verdict here.
INVARIANT (§5.3): a model missing from the catalog, or a malformed row, yields NO
observations — honest absence, never fabricated support.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aigateway.core.chat_parameters import (
    ProviderDiscoverySnapshot,
    ProviderParameterObservation,
)
from aigateway.core.parameter_discovery import (
    DiscoveryError,
    DiscoveryHttpClient,
    DiscoveryLimits,
    fetch_discovery_json,
)
from aigateway.core.parameter_projection import GATEWAY_OWNED_FIELDS, WRAPPER_KEY

# Fixed public sources (the async fetch step passes these to the bounded
# transport; the parsers below never dereference a URL themselves).
MODELS_URL = "https://openrouter.ai/api/v1/models"
OPENAPI_URL = "https://openrouter.ai/openapi.json"
ALLOWED_ORIGINS: frozenset[str] = frozenset({"https://openrouter.ai"})

MODEL_SOURCE = "openrouter:models"
ENDPOINT_SOURCE = "openrouter:openapi"

# OpenRouter params AIGateway addresses through the ``provider_params.*`` wrapper
# (native, non-OpenAI-standard). Mirrors the provider_native rule paths so a
# wrapped field's observation lines up with its rule in the detail overlay — this
# is what lets ``top_k`` show a clean observed→ruled promotion while standard
# fields (``top_p``) surface observed-but-unruled at their identity path.
# AIDEV-NOTE: grows with each native rule added in parameters.py; keep in sync.
_WRAPPED_NATIVE_PARAMS: frozenset[str] = frozenset({"top_k"})


def _request_path(catalog_param: str) -> str:
    if catalog_param in _WRAPPED_NATIVE_PARAMS:
        return f"{WRAPPER_KEY}.{catalog_param}"
    return catalog_param


def _observation(catalog_param: str, *, source: str) -> ProviderParameterObservation:
    return ProviderParameterObservation(
        request_path=_request_path(catalog_param),
        support="supported",
        source=source,
    )


def _dedup_sorted(
    obs: list[ProviderParameterObservation],
) -> tuple[ProviderParameterObservation, ...]:
    by_path: dict[str, ProviderParameterObservation] = {}
    for observation in obs:
        by_path.setdefault(observation.request_path, observation)
    return tuple(by_path[path] for path in sorted(by_path))


def parse_model_catalog_observations(
    catalog: Any, *, upstream_model_id: str
) -> tuple[ProviderParameterObservation, ...]:
    """Per-model evidence from the public ``/api/v1/models`` catalog.

    ``supported_parameters`` for the matching row becomes positive per-model
    evidence; the catalog only lists SUPPORTED fields, so an unlisted field is
    left unknown (no observation), never marked unsupported.
    """
    if not isinstance(catalog, Mapping):
        return ()
    data = catalog.get("data")
    if not isinstance(data, list):
        return ()
    row = next(
        (m for m in data if isinstance(m, Mapping) and m.get("id") == upstream_model_id),
        None,
    )
    if row is None:
        return ()
    params = row.get("supported_parameters")
    if not isinstance(params, list):
        return ()
    observed = [
        _observation(param, source=MODEL_SOURCE) for param in params if isinstance(param, str)
    ]
    return _dedup_sorted(observed)


def parse_openapi_endpoint_observations(
    openapi: Any, *, schema_name: str
) -> tuple[ProviderParameterObservation, ...]:
    """Endpoint-level evidence: the request schema's accepted optional fields.

    # WHY: required-protocol / gateway-owned fields (model, messages, stream, …)
    # are not optional model parameters, so they are excluded here — otherwise the
    # overlay would surface them as disabled "parameters", which is misleading.
    """
    if not isinstance(openapi, Mapping):
        return ()
    components = openapi.get("components")
    schemas = components.get("schemas") if isinstance(components, Mapping) else None
    schema = schemas.get(schema_name) if isinstance(schemas, Mapping) else None
    properties = schema.get("properties") if isinstance(schema, Mapping) else None
    if not isinstance(properties, Mapping):
        return ()
    observed = [
        _observation(name, source=ENDPOINT_SOURCE)
        for name in properties
        if isinstance(name, str) and name not in GATEWAY_OWNED_FIELDS
    ]
    return _dedup_sorted(observed)


# Provenance label for REVIEWED labelled-local evidence — deliberately DISTINCT
# from the live labels (openrouter:models / openrouter:openapi) so a reader can
# tell reviewed-static evidence from a live network fetch (§5.1 "labelled").
LOCAL_SOURCE = "openrouter:static"

# OME-479 §5.3 — REVIEWED labelled-local endpoint evidence (NO network). The
# OpenRouter chat endpoint's accepted optional SAMPLING/GENERATION fields, used
# as the detail contract's observation source in v1. Each name is backed by
# verified public ``supported_parameters``; native fields map through the wrapper
# so an observation lines up with its rule. Tool capabilities are reported in their
# own contract section, and the ``tools`` / ``tool_choice`` request-path observations
# are contributed at the plugin level (``tool_parameter_observations`` over the
# plugin's tool capabilities, OME-583) — kept OUT of this sampling constant so it
# stays a pure sampling-field inventory.
# AIDEV-NOTE: provider-local REVIEWED evidence, not a central inventory — extend
# deliberately, and only for a SAMPLING field the public catalog proves the endpoint
# takes; tool request paths are added via the plugin's tool observations, never here.
_REVIEWED_ENDPOINT_PARAMS: tuple[str, ...] = (
    "temperature",
    "top_p",
    "top_k",
    "max_tokens",
    "frequency_penalty",
    "presence_penalty",
    "seed",
    "stop",
)

REVIEWED_ENDPOINT_OBSERVATIONS: tuple[ProviderParameterObservation, ...] = _dedup_sorted(
    [_observation(name, source=LOCAL_SOURCE) for name in _REVIEWED_ENDPOINT_PARAMS]
)


# Source identity for a LIVE snapshot's revision. The cache TTL — not this
# constant — governs freshness; the revision distinguishes source IDENTITY (live
# catalog vs a labelled-static fallback), so a stable label is the right value.
_LIVE_REVISION = "openrouter:models:live"


async def discover_openrouter_snapshot(
    upstream_model_id: str,
    *,
    client: DiscoveryHttpClient,
    limits: DiscoveryLimits | None = None,
) -> ProviderDiscoverySnapshot | None:
    """Fetch the FIXED public catalog and return per-model evidence, or None.

    # INVARIANT (§5.3): a sanitized ``DiscoveryError`` (unreachable / bad shape)
    # means discovery could observe nothing — return None so the caller falls
    # back to labelled-local evidence. A SUCCESSFUL fetch whose catalog lacks the
    # model returns a present-but-empty snapshot (honest "reached, found
    # nothing"), which is distinct from a failure and never fabricates support.
    # INVARIANT (§5.1): only per-model evidence is populated here; endpoint
    # evidence keeps its own (empty) field — the live OpenAPI fetch is wired
    # separately and must not be conflated with per-model support.
    """
    try:
        catalog = await fetch_discovery_json(
            MODELS_URL,
            allowed_origins=ALLOWED_ORIGINS,
            client=client,
            limits=limits or DiscoveryLimits(),
        )
    except DiscoveryError:
        return None
    model_observations = parse_model_catalog_observations(
        catalog, upstream_model_id=upstream_model_id
    )
    return ProviderDiscoverySnapshot(
        source_revision=_LIVE_REVISION,
        model_observations=model_observations,
    )
