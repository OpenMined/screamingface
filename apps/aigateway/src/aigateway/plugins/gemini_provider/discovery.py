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
from typing import Any

from aigateway.core.chat_parameters import ProviderParameterObservation
from aigateway.core.parameter_discovery import DiscoveryError
from aigateway.core.parameter_projection import WRAPPER_KEY

# Distinct provenance so a reader can tell public-API evidence from OAuth Code Assist
# evidence (§5.1 "labelled"); the auth-scoped plugin hook picks one per auth mode.
DISCOVERY_SOURCE = "gemini:discovery"
CODE_ASSIST_SOURCE = "gemini:code-assist"

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


def parse_generation_config_params(document: Any) -> tuple[str, ...]:
    """Return the native scalar ``GenerationConfig`` property names, sorted.

    Honest absence (``()``) for a malformed/unlinked document; ``DiscoveryError`` for a
    suspiciously oversized properties map (bounded schema, no silent truncation).
    """
    if not isinstance(document, Mapping):
        return ()
    schemas = document.get("schemas")
    if not isinstance(schemas, Mapping):
        return ()
    if not _references_config(schemas.get(_REQUEST_SCHEMA)):
        return ()
    config = schemas.get(_CONFIG_SCHEMA)
    if not isinstance(config, Mapping):
        return ()
    properties = config.get("properties")
    if not isinstance(properties, Mapping):
        return ()
    if len(properties) > _MAX_CONFIG_PROPERTIES:
        raise DiscoveryError("generation_config_schema_too_large")
    return tuple(sorted(name for name, spec in properties.items() if _is_scalar_property(spec)))


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
