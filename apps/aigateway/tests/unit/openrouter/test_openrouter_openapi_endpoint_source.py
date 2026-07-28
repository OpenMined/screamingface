"""OME-647 (OME-479 §5.1/§6.1): the OpenAPI endpoint source, parsed.

FEATURE: OpenRouter's source PAIR. §5.1 names two fixed public documents — the
per-model catalog for what a model supports, and the public OpenAPI document for
what the endpoint accepts, in what SHAPE, and with what LIFECYCLE. Only the catalog
half reached production: ``parse_openapi_endpoint_observations`` existed but its
only callers were fixtures, so ``endpoint_observations`` was always empty.

STORY: as an API consumer I read /v1/model-parameters and see, for a field the
gateway does not project, the shape OpenRouter itself declares for it — and I am
told when OpenRouter has deprecated a field, before I build a UI around it.

INVARIANT (evidence only): a schema published here describes what the ENDPOINT
accepts and a deprecation verdict describes what the PROVIDER declares. Neither
enables a parameter, moves gateway.status, changes the /v1/models summary, or
touches dispatch — only a rule does.
INVARIANT (§5.2): every fetch goes through the bounded transport under an INJECTED
client. No test in this file reaches the network.

AIDEV-NOTE: the production wiring lives in ``test_openrouter_openapi_endpoint_route``
— a parser that is correct against a fixture and never reached by the route is the
exact failure this pair of files exists to separate.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from aigateway.core.chat_parameters import ProviderParameterObservation, overlay_observations
from aigateway.core.parameter_discovery import (
    DiscoveryError,
    DiscoveryHttpClient,
    DiscoveryLimits,
    RawResponse,
    fetch_discovery_json,
)
from aigateway.plugins.openrouter_provider.discovery import (
    ALLOWED_ORIGINS,
    CHAT_REQUEST_SCHEMA,
    MODELS_URL,
    OPENAPI_URL,
    openapi_discovery_limits,
    parse_openapi_endpoint_observations,
)

from ._openapi_document import _CATALOG, _OPENAPI, _UPSTREAM, _by_path, _RoutingClient


def _endpoint() -> dict[str, Any]:
    return _by_path(parse_openapi_endpoint_observations(_OPENAPI, schema_name=CHAT_REQUEST_SCHEMA))


# --- the parser: shapes ------------------------------------------------------


def test_endpoint_observation_carries_the_declared_shape() -> None:
    temperature = _endpoint()["temperature"]
    assert temperature.parameter_schema is not None
    # "null" in the type union is JSON-Schema NULLABILITY, not a value type: a
    # published `["number", "null"]` would claim the endpoint takes a null.
    assert temperature.parameter_schema.to_json_schema() == {"type": "number"}


def test_a_prose_only_range_is_never_turned_into_a_bound() -> None:
    # the live document states "Sampling temperature (0-2)" in DESCRIPTION only and
    # declares no minimum/maximum. Inferring 0..2 from the sentence would publish a
    # machine-readable constraint the source never committed to.
    schema = _endpoint()["temperature"].parameter_schema
    assert schema is not None
    assert schema.minimum is None and schema.maximum is None


def test_a_top_level_union_publishes_both_forms_with_its_item_type() -> None:
    stop = _endpoint()["stop"].parameter_schema
    assert stop is not None
    assert stop.to_json_schema() == {"type": ["array", "string"], "items": {"type": "string"}}


def test_an_exhaustive_enum_is_published_without_its_null_member() -> None:
    tier = _endpoint()["service_tier"].parameter_schema
    assert tier is not None
    assert tier.to_json_schema() == {"type": "string", "enum": ["auto", "default", "flex"]}


def test_a_partial_enum_across_a_union_is_withheld_not_merged() -> None:
    # tool_choice is three string enums AND an object form. Publishing just the
    # enums would deny the named-tool object the endpoint really accepts — a
    # FABRICATED restriction, so no enum is published at all.
    schema = _endpoint()["tool_choice"].parameter_schema
    assert schema is not None
    assert schema.enum is None
    assert schema.to_json_schema() == {"type": ["object", "string"]}


def test_an_unmodelled_shape_publishes_no_schema_rather_than_an_approximation() -> None:
    # response_format is a discriminated oneOf with no top-level type. The gateway's
    # schema vocabulary cannot express it, and an approximation a client could not
    # distinguish from a real constraint is worse than an honest absence.
    assert _endpoint()["response_format"].parameter_schema is None


def test_a_native_field_keeps_the_wrapper_request_path() -> None:
    # endpoint evidence must line up with the rule path, exactly as catalog evidence
    # does, or the overlay would file two rows for one parameter.
    endpoint = _endpoint()
    assert "provider_params.top_k" in endpoint
    assert "top_k" not in endpoint


def test_gateway_owned_protocol_fields_are_still_excluded() -> None:
    endpoint = _endpoint()
    for path in ("model", "messages", "stream"):
        assert path not in endpoint, path


# --- the parser: lifecycle ---------------------------------------------------


def test_a_deprecation_declared_only_behind_a_ref_is_detected() -> None:
    # the live document flags NOTHING inline on a ChatRequest property; `route`'s
    # deprecation lives in the DeprecatedRoute component it points at. A parser that
    # refused to dereference would report the whole endpoint as current.
    assert _endpoint()["route"].deprecated is True


def test_an_undeprecated_field_is_declared_current_not_unknown() -> None:
    # this source DOES model lifecycle (OpenAPI's `deprecated` defaults to false), so
    # an unflagged property is a positive statement, distinct from silence.
    assert _endpoint()["temperature"].deprecated is False


def test_a_deprecation_stated_only_in_prose_is_not_reported() -> None:
    # max_tokens' description says "deprecated, use max_completion_tokens" with NO
    # flag. Reading a verdict out of free text would fabricate structure the source
    # deliberately did not commit to — and would be unfalsifiable for the next agent.
    assert _endpoint()["max_tokens"].deprecated is False


def test_a_source_that_does_not_model_lifecycle_stays_silent() -> None:
    # the tri-state exists for this: the catalog lists supported parameter NAMES and
    # says nothing about deprecation, so it must not publish "current" either.
    catalog_obs = ProviderParameterObservation(
        request_path="temperature", support="supported", source="openrouter:models"
    )
    assert catalog_obs.deprecated is None


# --- the overlay: per-field silence ------------------------------------------


def test_per_model_support_wins_without_erasing_endpoint_shape_or_lifecycle() -> None:
    # THE merge bug this unit had to avoid: the catalog speaks only about SUPPORT.
    # Letting it win wholesale would delete the endpoint schema and lifecycle it
    # never contradicted — "a partial source read as a denial", one level down.
    endpoint = parse_openapi_endpoint_observations(_OPENAPI, schema_name=CHAT_REQUEST_SCHEMA)
    catalog = (
        ProviderParameterObservation(
            request_path="temperature", support="unsupported", source="openrouter:models"
        ),
    )
    merged = _by_path(overlay_observations(endpoint, catalog))["temperature"]
    assert (merged.support, merged.source) == ("unsupported", "openrouter:models")
    assert merged.parameter_schema is not None  # endpoint fact survived
    assert merged.deprecated is False


def test_lifecycle_evidence_served_from_the_stale_window_is_labelled_stale() -> None:
    # last-good endpoint evidence still STANDS after the TTL — a deprecation does not
    # stop being true because a refresh failed — but it must say it is not fresh, or a
    # client cannot tell a current verdict from one read minutes ago.
    endpoint = parse_openapi_endpoint_observations(_OPENAPI, schema_name=CHAT_REQUEST_SCHEMA)
    merged = _by_path(overlay_observations((), endpoint, stale=True))
    assert merged["route"].deprecated is True
    assert merged["route"].stale is True
    # and the carry-forward path is labelled too, not just the direct one.
    catalog = (
        ProviderParameterObservation(
            request_path="temperature", support="supported", source="openrouter:models"
        ),
    )
    carried = _by_path(overlay_observations(endpoint, catalog, stale=True))["temperature"]
    assert carried.deprecated is False and carried.stale is True


def test_an_overlay_that_does_speak_about_lifecycle_still_wins() -> None:
    # carry-forward applies to SILENCE only; a source with its own verdict decides.
    base = (
        ProviderParameterObservation(
            request_path="route", support="supported", source="a", deprecated=False
        ),
    )
    overlay = (
        ProviderParameterObservation(
            request_path="route", support="supported", source="b", deprecated=True
        ),
    )
    assert _by_path(overlay_observations(base, overlay))["route"].deprecated is True


# --- the bounds: measured, not guessed ---------------------------------------
#
# The live document measures 1,660,091 bytes / max depth 22 / 38,055 nodes. The
# shared defaults reject it on TWO axes — a remediation that raised only max_bytes
# would pass every fixture test here and then fail the first real fetch with
# `too_deep`. These tests exercise the bound rather than asserting the constant.
_REAL_BYTES = 1_660_091
_REAL_DEPTH = 22
_REAL_NODES = 38_055


def _document_of(*, depth: int, padding_bytes: int) -> Any:
    """A JSON value with a known nesting depth, padded to a known size."""
    node: Any = {"pad": "x" * padding_bytes}
    for _ in range(depth - 1):
        node = {"n": node}
    return node


class _SizedClient(DiscoveryHttpClient):
    """Serves one document; records the bounds the transport asked it to honour."""

    def __init__(self, document: Any) -> None:
        self._body = json.dumps(document)
        self.seen: list[tuple[str, float, int]] = []

    async def get(self, url: str, *, timeout_s: float, max_bytes: int) -> RawResponse:
        self.seen.append((url, timeout_s, max_bytes))
        return RawResponse(status=200, content_type="application/json", body=self._body)


@pytest.mark.asyncio
async def test_the_shared_defaults_reject_the_real_documents_shape() -> None:
    # the premise. Without this the widened bound below proves nothing.
    client = _SizedClient(_document_of(depth=_REAL_DEPTH, padding_bytes=_REAL_BYTES))
    with pytest.raises(DiscoveryError) as exc:
        await fetch_discovery_json(
            OPENAPI_URL,
            allowed_origins=ALLOWED_ORIGINS,
            client=client,
            limits=DiscoveryLimits(),
        )
    assert exc.value.reason == "oversized"


@pytest.mark.asyncio
async def test_the_source_specific_bounds_admit_the_real_documents_shape() -> None:
    document = _document_of(depth=_REAL_DEPTH, padding_bytes=_REAL_BYTES)
    client = _SizedClient(document)
    fetched = await fetch_discovery_json(
        OPENAPI_URL,
        allowed_origins=ALLOWED_ORIGINS,
        client=client,
        limits=openapi_discovery_limits(DiscoveryLimits()),
    )
    assert fetched == document


def test_a_depth_only_or_bytes_only_increase_would_not_be_enough() -> None:
    # guards the finding the review itself missed: BOTH axes are violated.
    widened = openapi_discovery_limits(DiscoveryLimits())
    assert widened.max_bytes > _REAL_BYTES
    assert widened.max_json_depth > _REAL_DEPTH
    assert widened.max_json_nodes > _REAL_NODES
    assert DiscoveryLimits().max_bytes < _REAL_BYTES
    assert DiscoveryLimits().max_json_depth < _REAL_DEPTH


def test_the_helper_widens_and_never_narrows_an_operators_choice() -> None:
    # an installation that deliberately raised a bound keeps it.
    generous = DiscoveryLimits(
        timeout_s=60.0, max_bytes=99_000_000, max_json_depth=256, max_json_nodes=9_000_000
    )
    assert openapi_discovery_limits(generous) == generous


@pytest.mark.asyncio
async def test_the_catalog_fetch_keeps_the_operators_bounds() -> None:
    # source-SPECIFIC: the small, flat catalog must not inherit the large document's
    # envelope — a global increase is what the review ruled out.
    from aigateway.plugins.openrouter_provider.discovery import discover_openrouter_snapshot

    client = _RoutingClient({MODELS_URL: _CATALOG, OPENAPI_URL: _OPENAPI})
    await discover_openrouter_snapshot(_UPSTREAM, client=client, limits=DiscoveryLimits())
    asked = dict((url, max_bytes) for url, _timeout, max_bytes in client.seen)
    assert asked[MODELS_URL] == DiscoveryLimits().max_bytes
    assert asked[OPENAPI_URL] > DiscoveryLimits().max_bytes


# --- the snapshot ------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_snapshot_now_carries_endpoint_evidence_from_the_openapi_document() -> None:
    from aigateway.plugins.openrouter_provider.discovery import discover_openrouter_snapshot

    snap = await discover_openrouter_snapshot(
        _UPSTREAM, client=_RoutingClient({MODELS_URL: _CATALOG, OPENAPI_URL: _OPENAPI})
    )
    assert snap.endpoint_observations != ()
    assert all(o.source == "openrouter:openapi" for o in snap.endpoint_observations)
    # §5.1 still holds: the two kinds are DISTINCT, not merged.
    assert all(o.source == "openrouter:models" for o in snap.model_observations)


@pytest.mark.asyncio
async def test_a_failure_of_either_document_propagates_rather_than_half_caching() -> None:
    # the cache reads any normal return as a SUCCESSFUL refresh, so returning the half
    # that worked would store a contract silently missing the other half.
    from aigateway.plugins.openrouter_provider.discovery import discover_openrouter_snapshot

    client = _RoutingClient({MODELS_URL: _CATALOG, OPENAPI_URL: _OPENAPI}, fail=OPENAPI_URL)
    with pytest.raises(DiscoveryError) as exc:
        await discover_openrouter_snapshot(_UPSTREAM, client=client)
    assert exc.value.reason == "unreachable"


@pytest.mark.asyncio
async def test_only_the_two_fixed_public_documents_are_ever_dialed() -> None:
    from aigateway.plugins.openrouter_provider.discovery import discover_openrouter_snapshot

    client = _RoutingClient({MODELS_URL: _CATALOG, OPENAPI_URL: _OPENAPI})
    await discover_openrouter_snapshot(_UPSTREAM, client=client)
    assert client.calls == [MODELS_URL, OPENAPI_URL]  # no retry storm, no third host
