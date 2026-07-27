"""OME-632 (OME-479 §Phase 9): Gemini's live public schema as contract evidence.

FEATURE: the detailed contract reports what Google's published `GenerationConfig`
schema actually declares, instead of a hand-maintained list that silently drifts.

STORY: as an API consumer I ask /v1/model-parameters about a Gemini model on an
api-key profile and learn that a sampling field our reviewed list still names is
no longer part of the request schema — rather than being told it is supported
because a constant in this repository says so.

INVARIANT (bounded, allowlisted): only `GenerateContentRequest` → `GenerationConfig`
is read, `$ref` properties are never dereferenced, and an oversized property map
fails rather than truncating.
INVARIANT (auth separation): this document describes the PUBLIC generativelanguage
API. The OAuth Code Assist envelope publishes no schema, so this evidence must never
reach it — the api-key path declares the source, the OAuth path declares none.
INVARIANT (closed-world over the property map ONLY): the map is exhaustive for the
schema, so an absent name is a real negative. The SCALAR subset is not a vocabulary —
negating against it would fabricate `unsupported` for every `$ref` field.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from aigateway.core.parameter_discovery import (
    DiscoveryError,
    DiscoveryLimits,
    RawResponse,
)
from aigateway.plugins.gemini_provider.discovery import (
    DISCOVERY_SOURCE,
    DISCOVERY_SOURCE_REVISION,
    DISCOVERY_URL,
    discover_gemini_snapshot,
    parse_discovery_snapshot,
    parse_generation_config_params,
    parse_generation_config_schema,
)
from aigateway.plugins.gemini_provider.plugin import PLUGIN

_MODEL = "gemini-cli/gemini-2.5-pro"

# A faithful slice of the live v1beta document (fetched 2026-07-27: 210 schemas,
# 6,332 nodes, depth 11). What is REAL here and drives the unit:
#   - the eight reviewed natives Google still declares as scalars;
#   - `candidateCount` REMOVED, standing in for the drift this unit detects;
#   - `responseMimeType` / `responseLogprobs`: live scalars our list never reviewed;
#   - `thinkingConfig` ($ref) and `responseJsonSchema` (untyped): never dereferenced.
_DOC: dict[str, Any] = {
    "id": "generativelanguage:v1beta",
    "revision": "20260727",
    "schemas": {
        "GenerateContentRequest": {
            "type": "object",
            "properties": {
                "contents": {"type": "array", "items": {"$ref": "Content"}},
                "generationConfig": {"$ref": "GenerationConfig"},
            },
        },
        "GenerationConfig": {
            "type": "object",
            "properties": {
                "temperature": {"type": "number"},
                "topP": {"type": "number"},
                "topK": {"type": "integer"},
                "maxOutputTokens": {"type": "integer"},
                "stopSequences": {"type": "array", "items": {"type": "string"}},
                "frequencyPenalty": {"type": "number"},
                "presencePenalty": {"type": "number"},
                "seed": {"type": "integer"},
                "responseMimeType": {"type": "string"},
                "responseLogprobs": {"type": "boolean"},
                "thinkingConfig": {"$ref": "ThinkingConfig"},
                "responseJsonSchema": {"description": "untyped Any"},
            },
        },
    },
}


def _verdicts(snapshot) -> dict[str, str]:
    return {o.request_path: o.support for o in snapshot.endpoint_observations}


# --- the richer reading -------------------------------------------------------


def test_the_schema_reading_reports_declared_and_scalar_names_apart() -> None:
    # WHY two sets: "absent from the schema" and "present but not a scalar" are
    # different claims, and only the first may become a negative verdict.
    schema = parse_generation_config_schema(_DOC)

    assert schema is not None
    assert "thinkingConfig" in schema.declared
    assert "thinkingConfig" not in schema.scalar
    assert "candidateCount" not in schema.declared


def test_a_malformed_document_is_distinguishable_from_an_empty_schema() -> None:
    # THE reason this reading exists: the older parser returns () for both, and a
    # closed-world reader handed () would negate every reviewed field at once.
    assert parse_generation_config_schema({"schemas": "nope"}) is None

    empty = parse_generation_config_schema(
        {
            "schemas": {
                "GenerateContentRequest": {
                    "properties": {"generationConfig": {"$ref": "GenerationConfig"}}
                },
                "GenerationConfig": {"properties": {}},
            }
        }
    )
    assert empty is not None
    assert empty.declared == frozenset()


def test_the_existing_scalar_parser_reads_the_same_schema() -> None:
    # The older entry point is kept and delegates, so the two readings can never
    # disagree about what counts as a scalar.
    schema = parse_generation_config_schema(_DOC)

    assert schema is not None
    assert parse_generation_config_params(_DOC) == schema.scalar


# --- projection: three outcomes, not two --------------------------------------


def test_a_declared_scalar_is_reported_supported_at_its_caller_path() -> None:
    verdicts = _verdicts(parse_discovery_snapshot(_DOC))

    assert verdicts["temperature"] == "supported"
    assert verdicts["top_p"] == "supported"
    assert verdicts["max_tokens"] == "supported"
    assert verdicts["stop"] == "supported"
    assert verdicts["provider_params.top_k"] == "supported"


def test_a_field_the_schema_does_not_declare_is_reported_unsupported() -> None:
    # Closed-world over the property map: Google generates it from the service
    # definition, so an absent name is a real negative, not silence.
    assert _verdicts(parse_discovery_snapshot(_DOC))["provider_params.candidateCount"] == (
        "unsupported"
    )


def test_a_reviewed_field_declared_as_a_ref_yields_no_verdict() -> None:
    # The field EXISTS; only its shape is outside the reviewed scalar surface.
    # Reporting it unsupported would deny a field the schema plainly declares.
    document = json.loads(json.dumps(_DOC))
    document["schemas"]["GenerationConfig"]["properties"]["stopSequences"] = {
        "$ref": "StopSequenceSpec"
    }

    assert "stop" not in _verdicts(parse_discovery_snapshot(document))


def test_a_scalar_beyond_the_reviewed_list_is_surfaced_on_the_wrapper_path() -> None:
    # Additive evidence: the gateway rules nothing here, so these arrive as
    # visible-but-DISABLED rows rather than being dropped on the floor.
    verdicts = _verdicts(parse_discovery_snapshot(_DOC))

    assert verdicts["provider_params.responseMimeType"] == "supported"
    assert verdicts["provider_params.responseLogprobs"] == "supported"


def test_a_ref_property_is_never_surfaced_at_all() -> None:
    verdicts = _verdicts(parse_discovery_snapshot(_DOC))

    assert "provider_params.thinkingConfig" not in verdicts
    assert "provider_params.responseJsonSchema" not in verdicts


def test_every_verdict_is_labelled_as_public_discovery_evidence() -> None:
    # §5.1 "labelled": a reader must be able to tell this from the Code Assist
    # evidence, which describes a different upstream entirely.
    snapshot = parse_discovery_snapshot(_DOC)

    assert {o.source for o in snapshot.endpoint_observations} == {DISCOVERY_SOURCE}
    assert snapshot.source_revision == DISCOVERY_SOURCE_REVISION


def test_the_evidence_is_endpoint_scoped_not_per_model() -> None:
    # ONE document describes the whole v1beta surface — unlike the OpenRouter and
    # Hugging Face catalogs, it says nothing model-specific. Filing it as per-model
    # evidence would let it outrank a genuinely model-scoped verdict later.
    snapshot = parse_discovery_snapshot(_DOC)

    assert snapshot.model_observations == ()
    assert snapshot.tool_observations == ()
    assert snapshot.endpoint_observations != ()


# --- silence and refusal ------------------------------------------------------


@pytest.mark.parametrize(
    "document",
    [
        None,
        {},
        {"schemas": "nope"},
        {"schemas": {"GenerationConfig": {"properties": {"temperature": {"type": "number"}}}}},
    ],
)
def test_a_document_we_cannot_trust_produces_no_verdicts(document: Any) -> None:
    # The last case is the important one: a config schema NOT linked from
    # GenerateContentRequest is not provably the schema this request uses.
    snapshot = parse_discovery_snapshot(document)

    assert snapshot.endpoint_observations == ()
    assert snapshot.source_revision == DISCOVERY_SOURCE_REVISION


def test_an_oversized_property_map_refuses_rather_than_truncating() -> None:
    document = json.loads(json.dumps(_DOC))
    document["schemas"]["GenerationConfig"]["properties"] = {
        f"field{i}": {"type": "number"} for i in range(600)
    }

    with pytest.raises(DiscoveryError):
        parse_discovery_snapshot(document)


# --- the bounded fetch --------------------------------------------------------


class _FakeClient:
    def __init__(self, body: str, *, status: int = 200) -> None:
        self.body = body
        self.status = status
        self.calls: list[str] = []

    async def get(self, url: str, *, timeout_s: float, max_bytes: int) -> RawResponse:
        self.calls.append(url)
        return RawResponse(status=self.status, content_type="application/json", body=self.body)


@pytest.mark.asyncio
async def test_the_fetch_reads_the_fixed_public_document() -> None:
    client = _FakeClient(json.dumps(_DOC))

    snapshot = await discover_gemini_snapshot(client=client, limits=DiscoveryLimits())

    assert client.calls == [DISCOVERY_URL]
    assert _verdicts(snapshot)["temperature"] == "supported"


@pytest.mark.asyncio
async def test_a_failed_fetch_propagates_instead_of_returning_empty() -> None:
    # §5.3: an empty snapshot means "reached it, nothing listed". A failure must NOT
    # wear that costume, or the cache stores an outage labelled fresh.
    client = _FakeClient("{}", status=503)

    with pytest.raises(DiscoveryError):
        await discover_gemini_snapshot(client=client)


# --- the auth-scoped predicate ------------------------------------------------


def test_the_api_key_path_declares_the_public_document() -> None:
    ref = PLUGIN.chat_discovery_source(model=_MODEL, auth_type="api_key")

    assert ref is not None
    assert (ref.source, ref.revision) == (DISCOVERY_SOURCE, DISCOVERY_SOURCE_REVISION)


def test_the_oauth_path_declares_no_source_at_all() -> None:
    # Code Assist publishes no schema. Declaring the public document here would
    # present evidence about a DIFFERENT upstream — and would publish a freshness
    # window for a fetch whose result the contract then had to discard.
    assert PLUGIN.chat_discovery_source(model=_MODEL, auth_type="oauth") is None


def test_an_unresolved_mode_declares_no_source() -> None:
    assert PLUGIN.chat_discovery_source(model=_MODEL) is None


def test_a_model_this_provider_does_not_serve_declares_no_source() -> None:
    assert PLUGIN.chat_discovery_source(model="openrouter/x/y", auth_type="api_key") is None


@pytest.mark.asyncio
async def test_the_declaration_and_the_fetch_share_one_predicate() -> None:
    # INVARIANT: a provider that declares a source commits to answering with a
    # snapshot or a DiscoveryError. If these disagreed the runtime would see
    # "promised evidence, then NOT ATTEMPTED" — which it cannot tell from an outage.
    client = _FakeClient(json.dumps(_DOC))

    assert (
        await PLUGIN.discover_chat_parameter_snapshot(
            model=_MODEL, client=client, auth_type="oauth"
        )
        is None
    )
    assert client.calls == []


@pytest.mark.asyncio
async def test_the_api_key_fetch_hook_reaches_the_document() -> None:
    client = _FakeClient(json.dumps(_DOC))

    snapshot = await PLUGIN.discover_chat_parameter_snapshot(
        model=_MODEL, client=client, auth_type="api_key"
    )

    assert snapshot is not None
    assert client.calls == [DISCOVERY_URL]
