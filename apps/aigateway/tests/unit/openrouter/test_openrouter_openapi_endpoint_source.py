"""OME-647 (OME-479 §5.1/§6.1): the OpenAPI endpoint source, parsed and WIRED.

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
"""

from __future__ import annotations

import json
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aigateway.core.chat_parameters import ProviderParameterObservation, overlay_observations
from aigateway.core.discovery_runtime import DiscoveryRuntime
from aigateway.core.parameter_discovery import (
    DiscoveryError,
    DiscoveryHttpClient,
    DiscoveryLimits,
    RawResponse,
    fetch_discovery_json,
)
from aigateway.core.parameter_discovery_cache import CacheLimits, ObservationCache
from aigateway.core.profile_index import ProfileIndexStore
from aigateway.core.profile_models import Profile, ProfileState, profile_id_for
from aigateway.plugins.openrouter_provider.discovery import (
    ALLOWED_ORIGINS,
    CHAT_REQUEST_SCHEMA,
    MODELS_URL,
    OPENAPI_URL,
    openapi_discovery_limits,
    parse_openapi_endpoint_observations,
)
from aigateway.plugins.openrouter_provider.settings import OpenRouterPluginSettings

_UPSTREAM = "google/gemini-2.0-flash-001"
_MODEL = f"openrouter/{_UPSTREAM}"

# Slice of the VERIFIED live document (fetched and measured 2026-07-28). Every shape
# below is copied from it, not invented: the ``["number", "null"]`` type unions, the
# prose-only ranges, the ``anyOf`` on stop, the enum-plus-null on service_tier, and
# `route`'s deprecation hidden one `$ref` hop away in ``DeprecatedRoute``.
_OPENAPI: dict[str, Any] = {
    "openapi": "3.1.0",
    "components": {
        "schemas": {
            CHAT_REQUEST_SCHEMA: {
                "type": "object",
                "required": ["messages"],
                "properties": {
                    "model": {"$ref": "#/components/schemas/ModelName"},
                    "messages": {"type": "array"},
                    "stream": {"type": "boolean", "default": False},
                    "temperature": {
                        "description": "Sampling temperature (0-2)",
                        "format": "double",
                        "type": ["number", "null"],
                    },
                    "top_k": {"type": ["integer", "null"]},
                    "seed": {"type": ["integer", "null"]},
                    "stop": {
                        "anyOf": [
                            {"type": "string"},
                            {"items": {"type": "string"}, "maxItems": 4, "type": "array"},
                            {"type": "null"},
                        ],
                        "description": "Stop sequences (up to 4)",
                    },
                    "service_tier": {
                        "enum": ["auto", "default", "flex", None],
                        "type": ["string", "null"],
                    },
                    "tool_choice": {"$ref": "#/components/schemas/ChatToolChoice"},
                    "response_format": {
                        "description": "Response format configuration",
                        "discriminator": {"propertyName": "type"},
                        "oneOf": [{"$ref": "#/components/schemas/ChatFormatJsonObject"}],
                    },
                    "route": {"$ref": "#/components/schemas/DeprecatedRoute"},
                    "max_tokens": {
                        "description": "Maximum tokens (deprecated, use max_completion_tokens).",
                        "type": ["integer", "null"],
                    },
                },
            },
            "ModelName": {"type": "string"},
            "DeprecatedRoute": {
                "deprecated": True,
                "enum": ["fallback", "sort", None],
                "type": ["string", "null"],
                "x-speakeasy-deprecation-message": "Use providers.sort.partition instead",
            },
            "ChatToolChoice": {
                "anyOf": [
                    {"enum": ["none"], "type": "string"},
                    {"enum": ["auto"], "type": "string"},
                    {"$ref": "#/components/schemas/ChatNamedToolChoice"},
                ]
            },
            "ChatNamedToolChoice": {"type": "object"},
            "ChatFormatJsonObject": {"type": "object"},
        }
    },
}

_CATALOG = {
    "data": [
        {
            "id": _UPSTREAM,
            "supported_parameters": ["temperature", "max_tokens", "seed", "top_k"],
        }
    ]
}


def _by_path(obs: tuple[ProviderParameterObservation, ...]) -> dict[str, Any]:
    return {o.request_path: o for o in obs}


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


class _RoutingClient(DiscoveryHttpClient):
    """Canned JSON per URL; records the URL and bounds of every dial."""

    def __init__(self, bodies: dict[str, Any], *, fail: str | None = None) -> None:
        self._bodies = bodies
        self._fail = fail
        self.seen: list[tuple[str, float, int]] = []

    @property
    def calls(self) -> list[str]:
        return [url for url, _timeout, _max_bytes in self.seen]

    async def get(self, url: str, *, timeout_s: float, max_bytes: int) -> RawResponse:
        self.seen.append((url, timeout_s, max_bytes))
        if self._fail == url:
            raise DiscoveryError("unreachable")
        return RawResponse(
            status=200, content_type="application/json", body=json.dumps(self._bodies[url])
        )


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


# --- production wiring: the route, not a fixture -----------------------------
#
# WHY this section exists: `parse_openapi_endpoint_observations` returns () for a
# schema name it cannot find. A wiring that used the wrong component name would
# raise nothing, log nothing, and pass every fixture test above while publishing an
# empty endpoint source. Only a test that walks the real route can catch that.


@pytest.fixture
def openrouter_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    # patches the singleton INSTANCE, not the environment: `load_plugins` hands the
    # same object to every app, so env vars set after import cannot reach it.
    from aigateway.plugins.openrouter_provider import plugin as plugin_module

    monkeypatch.setattr(
        plugin_module.PLUGIN,
        "settings",
        OpenRouterPluginSettings(enabled=True, default_models=[_MODEL]),
    )


def _install_runtime(client: TestClient, http: DiscoveryHttpClient) -> None:
    app = cast(FastAPI, client.app)
    app.state.discovery_runtime = DiscoveryRuntime(
        client=http,
        cache=ObservationCache(
            clock=_Clock(), limits=CacheLimits(ttl_s=60.0, stale_ttl_s=120.0, max_entries=8)
        ),
        limits=DiscoveryLimits(),
    )


class _Clock:
    def now(self) -> float:
        return 1000.0


async def _contract(credential_blobs, client: TestClient) -> dict[str, Any]:
    account_id = client.get("/v1/auth/me").json()["id"]
    await ProfileIndexStore(credential_store=credential_blobs.store).upsert(
        Profile(
            id=profile_id_for(account_id, "openrouter", "default"),
            account_id=account_id,
            provider="openrouter",
            name="default",
            state=ProfileState.AUTHENTICATED,
            auth_type="api_key",
        )
    )
    resp = client.get("/v1/model-parameters", params={"model": _MODEL})
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_the_route_publishes_evidence_sourced_from_the_openapi_document(
    openrouter_enabled, authenticated_client, credential_blobs
) -> None:
    _install_runtime(
        authenticated_client, _RoutingClient({MODELS_URL: _CATALOG, OPENAPI_URL: _OPENAPI})
    )
    body = await _contract(credential_blobs, authenticated_client)
    sources = {row["provider"]["source"] for row in body["parameters"].values()}
    assert "openrouter:openapi" in sources


@pytest.mark.asyncio
async def test_the_route_publishes_the_declared_shape_of_an_unprojected_field(
    openrouter_enabled, authenticated_client, credential_blobs
) -> None:
    # service_tier has no gateway rule, so this row is visible-but-DISABLED — and the
    # endpoint schema is the only shape a client can see for it.
    _install_runtime(
        authenticated_client, _RoutingClient({MODELS_URL: _CATALOG, OPENAPI_URL: _OPENAPI})
    )
    row = (await _contract(credential_blobs, authenticated_client))["parameters"]["service_tier"]
    assert row["gateway"]["status"] == "disabled"
    assert row["gateway"]["reason"] == "projection_not_implemented"
    assert row["schema"] == {"type": "string", "enum": ["auto", "default", "flex"]}


@pytest.mark.asyncio
async def test_the_route_publishes_the_providers_deprecation_verdict(
    openrouter_enabled, authenticated_client, credential_blobs
) -> None:
    _install_runtime(
        authenticated_client, _RoutingClient({MODELS_URL: _CATALOG, OPENAPI_URL: _OPENAPI})
    )
    params = (await _contract(credential_blobs, authenticated_client))["parameters"]
    assert params["route"]["provider"]["deprecated"] is True
    assert params["temperature"]["provider"]["deprecated"] is False


@pytest.mark.asyncio
async def test_a_gateway_owned_rule_schema_still_outranks_the_endpoints(
    openrouter_enabled, authenticated_client, credential_blobs
) -> None:
    # the endpoint declares a bare `{"type": "number"}` for temperature; the gateway's
    # own rule carries the bounds it VALIDATES against. Evidence must never displace
    # the schema the gateway actually enforces.
    _install_runtime(
        authenticated_client, _RoutingClient({MODELS_URL: _CATALOG, OPENAPI_URL: _OPENAPI})
    )
    row = (await _contract(credential_blobs, authenticated_client))["parameters"]["temperature"]
    assert row["gateway"]["status"] == "enabled"
    assert row["schema"]["maximum"] is not None


def test_the_source_revision_and_lifecycle_both_reach_contract_identity() -> None:
    """Reading DIFFERENT documents must move the opaque ids, even byte-for-byte.

    Two distinct inputs, one property: a contract_id that did not move would tell a
    client "nothing changed" while the evidence underneath it came from a different
    source, or carried a lifecycle verdict it did not carry before.
    """
    from aigateway.core.model_parameter_contract import build_model_parameter_document

    def _document(*, source_revision: str, deprecated: bool | None) -> dict[str, Any]:
        return build_model_parameter_document(
            canonical_id=_MODEL,
            gateway_provider="openrouter",
            auth_mode="api_key",
            scope="account_profile",
            context_identity="acct:test|prof:1",
            rules=(),
            observations=(
                ProviderParameterObservation(
                    request_path="route",
                    support="supported",
                    source="openrouter:openapi",
                    deprecated=deprecated,
                ),
            ),
            tools=(),
            transport=(),
            freshness={"stale": False, "degraded": False},
            source_revision=source_revision,
        )

    baseline = _document(source_revision="rev-a", deprecated=False)

    # 1. the source pair changed; the observations are byte-identical.
    moved_source = _document(source_revision="rev-b", deprecated=False)
    assert moved_source["contract_id"] != baseline["contract_id"]
    assert moved_source["context"]["revision"] != baseline["context"]["revision"]

    # 2. the lifecycle verdict changed; everything else is identical. Both
    #    transitions count — including the one OUT of silence, which is why the
    #    tri-state is encoded distinctly rather than collapsed to a bool.
    for verdict in (True, None):
        moved_lifecycle = _document(source_revision="rev-a", deprecated=verdict)
        assert moved_lifecycle["contract_id"] != baseline["contract_id"], verdict
        assert moved_lifecycle["context"]["revision"] != baseline["context"]["revision"], verdict


@pytest.mark.asyncio
async def test_the_new_source_moves_no_gateway_decision(
    openrouter_enabled, authenticated_client, credential_blobs
) -> None:
    # F12 semantics, owner-locked: dynamic observations move the EVIDENCE axis only.
    # A deprecated, endpoint-observed `route` must not become dispatchable, and the
    # summary must not learn anything from a document the gateway merely read.
    _install_runtime(
        authenticated_client, _RoutingClient({MODELS_URL: _CATALOG, OPENAPI_URL: _OPENAPI})
    )
    params = (await _contract(credential_blobs, authenticated_client))["parameters"]
    assert params["route"]["gateway"]["status"] == "disabled"

    row = next(
        r for r in authenticated_client.get("/v1/models").json()["data"] if r["id"] == _MODEL
    )
    assert set(row["supported_parameters"]).isdisjoint({"route", "service_tier", "tool_choice_x"})
