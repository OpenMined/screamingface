"""Phase 9b (OME-479 §5.1/§Phase 9 step 1-2): Gemini bounded Discovery parser (PURE).

FEATURE: Gemini P1 observation overlay. Turns Google's PUBLIC Discovery document
(``$discovery/rest?version=v1beta``) into labelled parameter evidence, and keeps
that PUBLIC-API evidence (``gemini:discovery``) separate from the OAuth Code Assist
evidence (``gemini:code-assist``) — the Code Assist path has no public schema, so
its only honest evidence is the reviewed builder mapping.

INVARIANT (bounded schema): the parser reads ONLY the allowlisted
``GenerationConfig`` schema, extracts its SCALAR sampling properties, SKIPS every
``$ref`` property (they point outside the allowlisted scalar surface — "reject
external refs"), and REFUSES a suspiciously large properties map rather than
silently truncating (no silent cap).
INVARIANT (§5.1): PUBLIC evidence and OAuth evidence carry DISTINCT source labels;
the public set is a SUPERSET of the OAuth set, so Discovery never overclaims OAuth.
INVARIANT (SOLID/hexagonal): pure functions over an already-fetched, already-
bounded document — NO network, NO clock, NO credentials here.
"""

from __future__ import annotations

import pytest

from aigateway.core.parameter_discovery import DiscoveryError
from aigateway.plugins.gemini_provider.discovery import (
    CODE_ASSIST_SOURCE,
    DISCOVERY_SOURCE,
    GEMINI_CODE_ASSIST_OBSERVATIONS,
    GEMINI_DISCOVERY_STATIC_OBSERVATIONS,
    parse_generation_config_params,
)

# A faithful slice of the LIVE Gemini Discovery document: schemas keyed by bare
# name, GenerateContentRequest.generationConfig referencing GenerationConfig by a
# bare ``$ref``, and GenerationConfig carrying scalar sampling props ALONGSIDE
# complex ``$ref`` props (thinkingConfig/responseSchema/speechConfig) that must be
# skipped. Non-allowlisted schemas (ThinkingConfig) are present but never traversed.
_DISCOVERY = {
    "schemas": {
        "GenerateContentRequest": {
            "id": "GenerateContentRequest",
            "type": "object",
            "properties": {
                "model": {"type": "string"},
                "contents": {"type": "array", "items": {"$ref": "Content"}},
                "systemInstruction": {"$ref": "Content"},
                "tools": {"type": "array", "items": {"$ref": "Tool"}},
                "generationConfig": {"$ref": "GenerationConfig"},
            },
        },
        "GenerationConfig": {
            "id": "GenerationConfig",
            "type": "object",
            "properties": {
                "temperature": {"type": "number", "format": "float"},
                "topP": {"type": "number", "format": "float"},
                "topK": {"type": "integer", "format": "int32"},
                "maxOutputTokens": {"type": "integer", "format": "int32"},
                "stopSequences": {"type": "array", "items": {"type": "string"}},
                "frequencyPenalty": {"type": "number", "format": "float"},
                "presencePenalty": {"type": "number", "format": "float"},
                "seed": {"type": "integer", "format": "int32"},
                "candidateCount": {"type": "integer", "format": "int32"},
                # complex $ref properties — MUST be skipped (external to scalar surface).
                "thinkingConfig": {"$ref": "ThinkingConfig"},
                "responseSchema": {"$ref": "Schema"},
                "speechConfig": {"$ref": "SpeechConfig"},
            },
        },
        "ThinkingConfig": {
            "type": "object",
            "properties": {"thinkingBudget": {"type": "integer"}},
        },
    }
}


def test_parses_scalar_generation_config_params() -> None:
    names = set(parse_generation_config_params(_DISCOVERY))
    assert {
        "temperature",
        "topP",
        "topK",
        "maxOutputTokens",
        "stopSequences",
        "frequencyPenalty",
        "presencePenalty",
        "seed",
        "candidateCount",
    } <= names


def test_parser_skips_complex_ref_properties() -> None:
    # "reject external refs": a $ref property points outside the scalar param
    # surface, so it is never surfaced as a parameter (no fabricated support).
    names = set(parse_generation_config_params(_DISCOVERY))
    assert "thinkingConfig" not in names
    assert "responseSchema" not in names
    assert "speechConfig" not in names


def test_parser_never_dereferences_a_ref_value() -> None:
    # a malicious/external $ref value is skipped wholesale — the parser never
    # follows it, so a URL or nested payload behind $ref cannot influence output.
    doc = {
        "schemas": {
            "GenerateContentRequest": {
                "properties": {"generationConfig": {"$ref": "GenerationConfig"}}
            },
            "GenerationConfig": {
                "properties": {
                    "temperature": {"type": "number"},
                    "evil": {"$ref": "https://attacker.example/inject"},
                }
            },
        }
    }
    names = set(parse_generation_config_params(doc))
    assert names == {"temperature"}


def test_parser_requires_request_to_reference_generation_config() -> None:
    # allowlist linkage: without GenerateContentRequest.generationConfig -> $ref
    # GenerationConfig, we are not looking at the real document → honest absence.
    doc = {"schemas": {"GenerationConfig": {"properties": {"temperature": {"type": "number"}}}}}
    assert parse_generation_config_params(doc) == ()


def test_parser_returns_empty_on_malformed_document() -> None:
    assert parse_generation_config_params({}) == ()
    assert parse_generation_config_params({"schemas": "nope"}) == ()
    assert parse_generation_config_params([]) == ()  # type: ignore[arg-type]


def test_parser_refuses_an_oversized_properties_map() -> None:
    # no silent cap: a suspiciously large GenerationConfig is REFUSED (bounded
    # schema), not partially trusted — a truncated parse would hide params.
    huge = {f"field_{i}": {"type": "number"} for i in range(10_000)}
    doc = {
        "schemas": {
            "GenerateContentRequest": {
                "properties": {"generationConfig": {"$ref": "GenerationConfig"}}
            },
            "GenerationConfig": {"properties": huge},
        }
    }
    with pytest.raises(DiscoveryError):
        parse_generation_config_params(doc)


def test_discovery_static_observations_are_corroborated_by_the_parser() -> None:
    # the reviewed labelled-static PUBLIC observations are not fabricated: every
    # native they encode is one the parser actually extracts from a faithful doc.
    parsed = set(parse_generation_config_params(_DISCOVERY))
    for obs in GEMINI_DISCOVERY_STATIC_OBSERVATIONS:
        assert obs.support == "supported"
        assert obs.source == DISCOVERY_SOURCE
    # every discovery observation resolves to a real native GenerationConfig field
    # (caller-path aliases map back to the camelCase native the parser extracts).
    _alias = {
        "temperature": "temperature",
        "top_p": "topP",
        "max_tokens": "maxOutputTokens",
        "stop": "stopSequences",
        "provider_params.top_k": "topK",
        "provider_params.frequencyPenalty": "frequencyPenalty",
        "provider_params.presencePenalty": "presencePenalty",
        "provider_params.seed": "seed",
        "provider_params.candidateCount": "candidateCount",
    }
    for obs in GEMINI_DISCOVERY_STATIC_OBSERVATIONS:
        assert _alias[obs.request_path] in parsed, obs.request_path


def test_public_and_code_assist_sources_are_distinct_and_labelled() -> None:
    assert DISCOVERY_SOURCE == "gemini:discovery"
    assert CODE_ASSIST_SOURCE == "gemini:code-assist"
    assert DISCOVERY_SOURCE != CODE_ASSIST_SOURCE
    assert all(o.source == DISCOVERY_SOURCE for o in GEMINI_DISCOVERY_STATIC_OBSERVATIONS)
    assert all(o.source == CODE_ASSIST_SOURCE for o in GEMINI_CODE_ASSIST_OBSERVATIONS)


def test_code_assist_evidence_is_the_builder_mapped_subset() -> None:
    # Code Assist has NO public schema; the ONLY honest evidence is the reviewed
    # build_generate_content_body mapping — the five fields it renames.
    paths = {o.request_path for o in GEMINI_CODE_ASSIST_OBSERVATIONS}
    assert paths == {"temperature", "top_p", "max_tokens", "stop", "provider_params.top_k"}


def test_public_discovery_is_a_superset_that_never_overclaims_oauth() -> None:
    # test-matrix "Gemini": public Discovery does not overclaim OAuth — the OAuth
    # set is the SMALLER, safer set; public evidence exposes strictly more.
    public = {o.request_path for o in GEMINI_DISCOVERY_STATIC_OBSERVATIONS}
    code_assist = {o.request_path for o in GEMINI_CODE_ASSIST_OBSERVATIONS}
    assert code_assist < public  # strict subset
    assert {"provider_params.frequencyPenalty", "provider_params.seed"} <= public
    assert {"provider_params.frequencyPenalty", "provider_params.seed"} & code_assist == set()
