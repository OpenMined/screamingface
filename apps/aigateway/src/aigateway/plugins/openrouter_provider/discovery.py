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
    ProviderSupport,
)
from aigateway.core.parameter_discovery import (
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


def _observation(
    catalog_param: str, *, source: str, support: ProviderSupport = "supported"
) -> ProviderParameterObservation:
    return ProviderParameterObservation(
        request_path=_request_path(catalog_param),
        support=support,
        source=source,
    )


def _dedup_sorted(
    obs: list[ProviderParameterObservation],
) -> tuple[ProviderParameterObservation, ...]:
    by_path: dict[str, ProviderParameterObservation] = {}
    for observation in obs:
        by_path.setdefault(observation.request_path, observation)
    return tuple(by_path[path] for path in sorted(by_path))


def _listed_parameters(row: Any) -> set[str] | None:
    """The row's ``supported_parameters`` as a name set, or None when unreadable."""
    if not isinstance(row, Mapping):
        return None
    params = row.get("supported_parameters")
    if not isinstance(params, list):
        return None
    # Gateway-owned fields are protocol plumbing, never model parameters; excluding
    # them here keeps them out of BOTH the vocabulary and the verdicts, so a row
    # that omits one can never produce an "unsupported stream" contract row.
    return {
        param
        for param in params
        if isinstance(param, str) and param and param not in GATEWAY_OWNED_FIELDS
    }


def _catalog_vocabulary(rows: list[Any]) -> frozenset[str]:
    """Every parameter name this catalog DOCUMENT tracks, across all its rows.

    # WHY derived from the payload instead of a reviewed constant: it is what makes
    # the closed-world reading below sound. A name some row lists is demonstrably
    # part of OpenRouter's capability vocabulary, so another row's omission of it
    # is a real signal. A name NO row mentions is one the catalog does not model at
    # all (``n``, ``logprobs``), and calling that "unsupported" would fabricate a
    # negative — and wrongly overwrite reviewed labelled-local evidence for a field
    # the endpoint does accept. A constant would also silently rot as OpenRouter's
    # vocabulary grows; the document cannot.
    """
    vocabulary: set[str] = set()
    for row in rows:
        listed = _listed_parameters(row)
        if listed is not None:
            vocabulary |= listed
    return frozenset(vocabulary)


def parse_model_catalog_observations(
    catalog: Any, *, upstream_model_id: str
) -> tuple[ProviderParameterObservation, ...]:
    """Per-model evidence from the public ``/api/v1/models`` catalog.

    CLOSED-WORLD INSIDE A PRESENT ROW (OME-629). OpenRouter documents
    ``supported_parameters`` as "array of supported API parameters for this model"
    and lets the catalog be FILTERED by it (``/models?supported_parameters=tools``),
    which only works if each array is complete enough for negative filtering. So
    within a row that exists and parses, an omission is a genuine ``unsupported``
    verdict — but only for a name the document's own vocabulary proves the catalog
    tracks (see ``_catalog_vocabulary``); outside that vocabulary the source is
    SILENT, and silence yields no observation in either direction.

    # AIDEV-NOTE: this REPLACES the earlier open-world reading ("an unlisted field
    # is left unknown, never marked unsupported"), which made every model's
    # evidence a subset of the same static inventory and could never report a
    # per-model gap. Reverting it would silently re-break that.
    # INVARIANT: an unreadable document, an absent row, or a malformed array yields
    # NO observations — the labelled-local evidence then serves. Absence of a
    # readable source is never turned into a wall of negatives.
    # INVARIANT: this is EVIDENCE. A negative verdict here narrows what the contract
    # CLAIMS; it never disables a rule and never blocks dispatch.
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
    supported = _listed_parameters(row)
    if supported is None:
        return ()
    return _dedup_sorted(
        [
            _observation(
                param,
                source=MODEL_SOURCE,
                support="supported" if param in supported else "unsupported",
            )
            for param in _catalog_vocabulary(data)
        ]
    )


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


# Source identity for a LIVE snapshot, and the cache revision it is stored under.
# The cache TTL — not this constant — governs freshness; the revision identifies
# the SOURCE together with the gateway-side READING of it.
# AIDEV-NOTE: bump this whenever the reading changes, not only when the URL does.
# The 2026-07 value marks the closed-world reading (OME-629): the same bytes now
# yield different verdicts, so entries cached under the previous open-world label
# must not be reused. That is precisely what the revision guard is for.
MODEL_SOURCE_REVISION = "openrouter:models:closed-world-2026-07"


async def discover_openrouter_snapshot(
    upstream_model_id: str,
    *,
    client: DiscoveryHttpClient,
    limits: DiscoveryLimits | None = None,
) -> ProviderDiscoverySnapshot:
    """Fetch the FIXED public catalog and return per-model evidence.

    # INVARIANT (§5.3): reaching the source and failing to reach it are DIFFERENT
    # outcomes and get different signals. A successful fetch whose catalog lacks
    # the model returns a present-but-empty snapshot — the honest "reached it,
    # found nothing" — while a sanitized ``DiscoveryError`` PROPAGATES.
    # AIDEV-NOTE: do not reintroduce a ``return None`` here. Swallowing made a
    # failure indistinguishable from "no evidence", and ``ObservationCache`` reads
    # any normal return as a successful refresh — so a swallowed outage was stored
    # labelled ``fresh``, evicting the last good snapshot. Raising is precisely
    # what routes it to the stale/degraded paths. It also preserves the reason
    # code, which ``None`` discards.
    # INVARIANT (§5.1): only per-model evidence is populated here; endpoint
    # evidence keeps its own (empty) field — the live OpenAPI fetch is wired
    # separately and must not be conflated with per-model support.
    """
    catalog = await fetch_discovery_json(
        MODELS_URL,
        allowed_origins=ALLOWED_ORIGINS,
        client=client,
        limits=limits or DiscoveryLimits(),
    )
    model_observations = parse_model_catalog_observations(
        catalog, upstream_model_id=upstream_model_id
    )
    return ProviderDiscoverySnapshot(
        source_revision=MODEL_SOURCE_REVISION,
        model_observations=model_observations,
    )
