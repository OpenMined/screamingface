"""OME-479 §Phase 9 step 1-2 — Gemini bounded Discovery parser + labelled evidence (PURE).

Two kinds of parameter evidence, kept DELIBERATELY apart by source label:

- PUBLIC-API evidence (``gemini:discovery``): the SCALAR sampling properties Google's
  public Discovery document declares on ``GenerationConfig``. Parsed by
  ``parse_generation_config_params`` from an already-fetched, already-bounded document
  (the core bounded transport supplies it; this module only parses).
- OAuth Code Assist evidence (``gemini:code-assist``): the Code Assist endpoint has NO
  public schema, so its ONLY honest evidence is the reviewed
  ``build_generate_content_body`` mapping — the five fields that builder renames into
  ``generationConfig``. This set is a STRICT SUBSET of the public set, so public
  Discovery never overclaims what OAuth can prove.

INVARIANT (bounded schema): the parser reads only the allowlisted ``GenerationConfig``
schema, extracts SCALAR properties, SKIPS every ``$ref`` property (external to the scalar
surface — "reject external refs"; the ref is never dereferenced), and REFUSES a
suspiciously large properties map (``DiscoveryError``) rather than silently truncating.
INVARIANT (SOLID/hexagonal): pure functions + module constants — NO network, NO clock,
NO credentials, NO provider-name switch. The plugin selects this evidence; core composes.
INVARIANT (§4.4): an observation NEVER enables a parameter — only a rule does. The
public-only fields (frequencyPenalty/presencePenalty/seed/candidateCount) are UNRULED, so
they surface visible-but-DISABLED.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from aigateway.core.chat_parameters import (
    ProviderDiscoverySnapshot,
    ProviderParameterObservation,
    ProviderSupport,
)
from aigateway.core.parameter_discovery import (
    DiscoveryError,
    DiscoveryHttpClient,
    DiscoveryLimits,
    fetch_discovery_json,
)
from aigateway.core.parameter_projection import WRAPPER_KEY

# Distinct provenance so a reader can tell public-API evidence from OAuth Code Assist
# evidence (§5.1 "labelled"); the auth-scoped plugin hook picks one per auth mode.
DISCOVERY_SOURCE = "gemini:discovery"
CODE_ASSIST_SOURCE = "gemini:code-assist"

# Fixed public source (the async fetch step passes this to the bounded transport; the
# parsers below never dereference a URL themselves). This describes the PUBLIC
# generativelanguage API only — the Code Assist envelope has no equivalent.
DISCOVERY_URL = "https://generativelanguage.googleapis.com/$discovery/rest?version=v1beta"
ALLOWED_ORIGINS: frozenset[str] = frozenset({"https://generativelanguage.googleapis.com"})

# INVARIANT: the revision names the SOURCE **and the gateway-side reading** of it,
# because the observation cache decides a stored entry's trustworthiness by matching
# it. Bump this whenever the projection below changes what the same bytes mean.
# AIDEV-NOTE: deliberately NOT the document's own ``revision`` field. A revision read
# off the payload can only be compared after paying for the fetch, and would let the
# source decide when its own old evidence stays valid.
DISCOVERY_SOURCE_REVISION = "gemini:discovery:generation-config-v1beta-2026-07"

# Google Discovery references other schemas by BARE name; the request must link to the
# config schema this way for us to trust we are parsing the real document.
_CONFIG_SCHEMA = "GenerationConfig"
_REQUEST_SCHEMA = "GenerateContentRequest"
_SCALAR_TYPES = frozenset({"number", "integer", "string", "boolean"})
_SCALAR_ITEM_TYPES = _SCALAR_TYPES
# Defensive schema-node bound (the transport already bounds the whole document; this is
# defense in depth on the one subtree we read). Google's real GenerationConfig has ~25
# properties, so this is a very wide safety margin, not a functional limit.
_MAX_CONFIG_PROPERTIES = 512


def _is_scalar_property(spec: Any) -> bool:
    # A $ref property points at another schema (thinkingConfig, responseSchema, ...); it
    # is NOT a scalar sampling param and is never dereferenced — skip it.
    if not isinstance(spec, Mapping) or "$ref" in spec:
        return False
    declared = spec.get("type")
    if declared in _SCALAR_TYPES:
        return True
    if declared == "array":
        items = spec.get("items")
        return isinstance(items, Mapping) and items.get("type") in _SCALAR_ITEM_TYPES
    return False


def _references_config(request_schema: Any) -> bool:
    if not isinstance(request_schema, Mapping):
        return False
    properties = request_schema.get("properties")
    if not isinstance(properties, Mapping):
        return False
    generation_config = properties.get("generationConfig")
    return (
        isinstance(generation_config, Mapping) and generation_config.get("$ref") == _CONFIG_SCHEMA
    )


@dataclass(frozen=True)
class GenerationConfigSchema:
    """The allowlisted ``GenerationConfig`` property map, split by shape.

    # WHY two sets rather than one: "absent from the schema" and "declared but not a
    # scalar" are DIFFERENT claims, and only the first may become a negative verdict.
    # The scalar subset is not a vocabulary — negating against it would fabricate
    # ``unsupported`` for every ``$ref`` field the schema plainly declares.
    """

    declared: frozenset[str]
    scalar: tuple[str, ...]


def parse_generation_config_schema(document: Any) -> GenerationConfigSchema | None:
    """Read the allowlisted ``GenerationConfig`` property map, or ``None``.

    ``None`` means the document is malformed, or its ``GenerationConfig`` is not
    reachable from ``GenerateContentRequest`` — so it is not provably the schema this
    request uses. ``DiscoveryError`` for a suspiciously oversized properties map
    (bounded schema, no silent truncation).

    # INVARIANT: ``None`` and an EMPTY map must stay distinguishable. A closed-world
    # reader handed "empty" for a malformed document would negate every reviewed
    # field at once — the exact fabrication this reading exists to prevent.
    """
    if not isinstance(document, Mapping):
        return None
    schemas = document.get("schemas")
    if not isinstance(schemas, Mapping):
        return None
    if not _references_config(schemas.get(_REQUEST_SCHEMA)):
        return None
    config = schemas.get(_CONFIG_SCHEMA)
    if not isinstance(config, Mapping):
        return None
    properties = config.get("properties")
    if not isinstance(properties, Mapping):
        return None
    if len(properties) > _MAX_CONFIG_PROPERTIES:
        raise DiscoveryError("generation_config_schema_too_large")
    return GenerationConfigSchema(
        declared=frozenset(properties),
        scalar=tuple(
            sorted(name for name, spec in properties.items() if _is_scalar_property(spec))
        ),
    )


def parse_generation_config_params(document: Any) -> tuple[str, ...]:
    """Return the native scalar ``GenerationConfig`` property names, sorted.

    Honest absence (``()``) for a malformed/unlinked document; ``DiscoveryError`` for a
    suspiciously oversized properties map (bounded schema, no silent truncation).
    """
    schema = parse_generation_config_schema(document)
    return () if schema is None else schema.scalar


# Reviewed native ``GenerationConfig`` name → caller-facing request path. The five fields
# ``build_generate_content_body`` renames use the gateway's caller path; every other
# native rides the ``provider_params.*`` wrapper under its Discovery (camelCase) name.
_NATIVE_TO_REQUEST_PATH: dict[str, str] = {
    "temperature": "temperature",
    "topP": "top_p",
    "maxOutputTokens": "max_tokens",
    "stopSequences": "stop",
    "topK": f"{WRAPPER_KEY}.top_k",
}

# Reviewed sampling natives surfaced from the PUBLIC Discovery schema. Tool capabilities
# remain a SEPARATE contract section, and the ``tools`` request-path observation is now
# contributed at the plugin level (``tool_parameter_observations`` over the plugin's tool
# capabilities, OME-583) — kept OUT of this sampling constant so the discovery-parser tests
# keep their narrow meaning. Structured-output / modality / response machinery likewise
# live in their own sections. ``build_generate_content_body`` renames the first five; the
# rest are public-only (the builder drops them today) → visible-but-DISABLED evidence.
_PUBLIC_SAMPLING_NATIVES: tuple[str, ...] = (
    "temperature",
    "topP",
    "topK",
    "maxOutputTokens",
    "stopSequences",
    "frequencyPenalty",
    "presencePenalty",
    "seed",
    "candidateCount",
)
# The Code Assist envelope has no public schema; only the builder-mapped fields are
# honestly evidenced there (a strict subset of the public natives).
_CODE_ASSIST_NATIVES: tuple[str, ...] = (
    "temperature",
    "topP",
    "topK",
    "maxOutputTokens",
    "stopSequences",
)


def _request_path(native: str) -> str:
    return _NATIVE_TO_REQUEST_PATH.get(native, f"{WRAPPER_KEY}.{native}")


def _observations(
    natives: tuple[str, ...], source: str
) -> tuple[ProviderParameterObservation, ...]:
    return tuple(
        sorted(
            (
                ProviderParameterObservation(
                    request_path=_request_path(native), support="supported", source=source
                )
                for native in natives
            ),
            key=lambda obs: obs.request_path,
        )
    )


# PUBLIC-API evidence (api-key / generativelanguage) — richer surface.
GEMINI_DISCOVERY_STATIC_OBSERVATIONS: tuple[ProviderParameterObservation, ...] = _observations(
    _PUBLIC_SAMPLING_NATIVES, DISCOVERY_SOURCE
)
# OAuth Code Assist evidence — the reviewed builder-mapped subset only.
GEMINI_CODE_ASSIST_OBSERVATIONS: tuple[ProviderParameterObservation, ...] = _observations(
    _CODE_ASSIST_NATIVES, CODE_ASSIST_SOURCE
)

_REVIEWED_NATIVES: frozenset[str] = frozenset(_PUBLIC_SAMPLING_NATIVES)


def project_generation_config(
    schema: GenerationConfigSchema | None,
) -> tuple[ProviderParameterObservation, ...]:
    """Turn the live property map into published evidence (OME-632).

    FEATURE: the detailed contract reports what Google's schema declares today,
    instead of repeating this repository's reviewed list back to the caller.

    Three outcomes per reviewed native, because two would have to lie about one of
    them:

    - declared AND scalar -> ``supported``;
    - ABSENT from the property map -> ``unsupported``. The map is generated from the
      service definition and is exhaustive for the schema, so an absent name is a
      real negative — closed-world, but over THAT map only;
    - declared and NOT scalar -> no observation. The field exists; only its shape is
      outside the reviewed scalar surface, so denying it would contradict the schema.

    A scalar the reviewed list never named is ADDITIVE evidence on the provider
    wrapper path: no rule enables it, so it surfaces visible-but-DISABLED rather than
    being dropped (§4.4 — an observation NEVER enables a parameter).
    """
    if schema is None:
        return ()
    scalar = frozenset(schema.scalar)
    observations: list[ProviderParameterObservation] = []
    for native in sorted(_REVIEWED_NATIVES | scalar):
        if native in scalar:
            support: ProviderSupport = "supported"
        elif native in schema.declared:
            continue
        else:
            support = "unsupported"
        observations.append(
            ProviderParameterObservation(
                request_path=_request_path(native), support=support, source=DISCOVERY_SOURCE
            )
        )
    return tuple(sorted(observations, key=lambda obs: obs.request_path))


def parse_discovery_snapshot(document: Any) -> ProviderDiscoverySnapshot:
    """Read the public Discovery document into a snapshot.

    INVARIANT (§5.1): this is ENDPOINT evidence. One document describes the whole
    ``v1beta`` surface and says nothing model-specific, so it lands in
    ``endpoint_observations`` — the LESS specific claim, which a genuinely per-model
    verdict may later outrank. Contrast the OpenRouter and Hugging Face catalogs,
    which are keyed by model.
    """
    return ProviderDiscoverySnapshot(
        source_revision=DISCOVERY_SOURCE_REVISION,
        endpoint_observations=project_generation_config(parse_generation_config_schema(document)),
    )


async def discover_gemini_snapshot(
    *, client: DiscoveryHttpClient, limits: DiscoveryLimits | None = None
) -> ProviderDiscoverySnapshot:
    """Fetch the fixed public Discovery document and project its schema.

    INVARIANT (§5.3): a transport failure PROPAGATES as ``DiscoveryError``. An empty
    snapshot means "reached the source; it declares nothing we can read" — letting a
    failure return one would have the cache store an outage labelled fresh.

    AIDEV-NOTE: the live document is ~354 KB / ~6,300 JSON nodes at depth 11 against
    transport bounds of 1 MB / 50,000 nodes / depth 16 (measured 2026-07-27). Byte
    size is dominated by prose descriptions, not structure, so the node and depth
    headroom is what a future Google expansion would eat into first.
    """
    document = await fetch_discovery_json(
        DISCOVERY_URL,
        allowed_origins=ALLOWED_ORIGINS,
        client=client,
        limits=limits or DiscoveryLimits(),
    )
    return parse_discovery_snapshot(document)
