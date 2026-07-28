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
    ParameterSchema,
    ProviderDiscoverySnapshot,
    ProviderParameterObservation,
    ProviderSupport,
    SchemaItemType,
    SchemaType,
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

# The component holding the chat endpoint's request body in OpenRouter's document.
# AIDEV-NOTE: verified against the live document 2026-07-28 — it is ``ChatRequest``,
# NOT the OpenAI-ish ``ChatCompletionRequest`` one might assume. A wrong name here
# does not raise: ``parse_openapi_endpoint_observations`` returns () for a schema it
# cannot find, so the whole endpoint source would go silently empty. That failure
# mode is exactly why this name is pinned by a wiring test through the real route
# and not by a fixture alone.
CHAT_REQUEST_SCHEMA = "ChatRequest"

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


# --- OpenAPI shape reading (OME-647) -----------------------------------------
#
# The gateway's ``ParameterSchema`` is deliberately small (scalars, typed arrays,
# top-level unions). These helpers map the SUBSET of JSON Schema the OpenRouter
# document actually uses onto it, and return None for anything outside that
# subset rather than approximating — an approximate published schema is worse
# than an absent one, because a client cannot tell the two apart.
# AIDEV-NOTE: keyed by the document's spelling and VALUED by the gateway's own
# literal type, so the lookup is the narrowing step — a JSON string only becomes a
# schema type by being found here. Written as maps rather than sets because a set
# of strings cannot narrow, and the alternative is a cast that would silently pass
# an unmodelled type name straight into ParameterSchema.
_MODELLED_TYPES: dict[str, SchemaType] = {
    "number": "number",
    "integer": "integer",
    "string": "string",
    "boolean": "boolean",
    "array": "array",
    "object": "object",
}
_MODELLED_ITEM_TYPES: dict[str, SchemaItemType] = {
    "number": "number",
    "integer": "integer",
    "string": "string",
    "boolean": "boolean",
    "object": "object",
}
_REF_PREFIX = "#/components/schemas/"


def _resolve_ref(node: Mapping[str, Any], schemas: Any) -> Mapping[str, Any]:
    """Follow ONE ``$ref`` hop into ``components.schemas``; never a chain.

    # WHY exactly one hop: the document keeps a property's real shape and its
    # lifecycle flag behind a single named component (``route`` → ``DeprecatedRoute``),
    # so refusing to dereference means reading none of it. Following an unbounded
    # CHAIN, on the other hand, is a cycle risk on a document this module treats as
    # untrusted input — and one hop is all OpenRouter's chat schema uses.
    """
    ref = node.get("$ref")
    if not isinstance(ref, str) or not ref.startswith(_REF_PREFIX):
        return node
    target = schemas.get(ref[len(_REF_PREFIX) :]) if isinstance(schemas, Mapping) else None
    return target if isinstance(target, Mapping) else node


def _union_members(node: Mapping[str, Any], schemas: Any) -> tuple[Mapping[str, Any], ...]:
    """A property's alternatives: its ``anyOf`` branches, or the node itself."""
    members = node.get("anyOf")
    if not isinstance(members, list):
        return (node,)
    return tuple(_resolve_ref(m, schemas) for m in members if isinstance(m, Mapping))


def _declared_types(node: Mapping[str, Any]) -> tuple[SchemaType, ...]:
    """The node's modelled types, sorted.

    # WHY ``null`` is dropped: ``"type": ["number", "null"]`` is JSON Schema's
    # NULLABILITY idiom, not a third value type. Carrying it across would publish a
    # schema claiming the endpoint accepts a null temperature.
    """
    raw = node.get("type")
    names = (raw,) if isinstance(raw, str) else tuple(raw) if isinstance(raw, list) else ()
    return tuple(
        sorted(
            {
                modelled
                for name in names
                if isinstance(name, str)
                for modelled in (_MODELLED_TYPES.get(name),)
                if modelled is not None
            }
        )
    )


def _member_item_type(members: tuple[Mapping[str, Any], ...]) -> SchemaItemType | None:
    """The single element type shared by every array member, if it is modelled."""
    found: set[SchemaItemType] = set()
    for member in members:
        items = member.get("items")
        if not isinstance(items, Mapping):
            continue
        declared = _declared_types(items)
        if len(declared) != 1:
            continue
        item_type = _MODELLED_ITEM_TYPES.get(declared[0])
        if item_type is not None:
            found.add(item_type)
    return found.pop() if len(found) == 1 else None


def _member_enum(members: tuple[Mapping[str, Any], ...]) -> tuple[str, ...] | None:
    """The allowed values — but only when EVERY typed alternative constrains them.

    # INVARIANT: an enum is published only if it is exhaustive. ``tool_choice`` is a
    # union of three string enums AND two object forms; taking the enums alone would
    # publish "must be none|auto|required" and silently deny the named-tool object the
    # endpoint accepts. A partial enum is a fabricated restriction, so it is withheld.
    """
    typed = [m for m in members if _declared_types(m)]
    if not typed or not all(isinstance(m.get("enum"), list) for m in typed):
        return None
    values: list[str] = []
    for member in typed:
        # a ``null`` entry is nullability again, never an allowed VALUE.
        values.extend(v for v in member["enum"] if isinstance(v, str))
    return tuple(dict.fromkeys(values)) or None


def _endpoint_schema(members: tuple[Mapping[str, Any], ...]) -> ParameterSchema | None:
    """Render the union onto the gateway's schema vocabulary, or None if unmodelled.

    # AIDEV-NOTE: no ``minimum``/``maximum`` is ever produced. The document states
    # ranges in PROSE only ("Sampling temperature (0-2)") and declares no numeric
    # bounds; parsing a description into a machine-readable constraint would invent
    # structure the source never committed to. Gateway-owned bounds live in the RULES.
    """
    declared: set[SchemaType] = {name for member in members for name in _declared_types(member)}
    types = tuple(sorted(declared))
    if not types:
        return None
    return ParameterSchema(
        type=types[0] if len(types) == 1 else types,
        item_type=_member_item_type(members) if "array" in types else None,
        enum=_member_enum(members),
    )


def _is_deprecated(members: tuple[Mapping[str, Any], ...]) -> bool:
    """Whether any alternative carries the document's own ``deprecated`` flag.

    # WHY a plain bool here while the observation field is tri-state: this source
    # DOES model lifecycle, so an unflagged property is a positive statement that the
    # field is current (OpenAPI's ``deprecated`` defaults to false). Silence belongs
    # to sources that never speak of lifecycle at all — they leave the field None.
    """
    return any(member.get("deprecated") is True for member in members)


def parse_openapi_endpoint_observations(
    openapi: Any, *, schema_name: str
) -> tuple[ProviderParameterObservation, ...]:
    """Endpoint-level evidence: the request schema's accepted optional fields.

    # WHY: required-protocol / gateway-owned fields (model, messages, stream, …)
    # are not optional model parameters, so they are excluded here — otherwise the
    # overlay would surface them as disabled "parameters", which is misleading.

    Each observation carries the field's SHAPE and its LIFECYCLE verdict as declared
    by the document (OME-647 / §6.1), both resolved through at most one ``$ref`` hop
    — OpenRouter states neither inline on the chat request properties.

    # INVARIANT: this is still pure EVIDENCE. A schema published here describes what
    # the ENDPOINT accepts; it never validates a caller's value (only a rule's
    # gateway-owned schema does that) and a ``deprecated`` verdict disables nothing.
    """
    if not isinstance(openapi, Mapping):
        return ()
    components = openapi.get("components")
    schemas = components.get("schemas") if isinstance(components, Mapping) else None
    schema = schemas.get(schema_name) if isinstance(schemas, Mapping) else None
    properties = schema.get("properties") if isinstance(schema, Mapping) else None
    if not isinstance(properties, Mapping):
        return ()
    observed: list[ProviderParameterObservation] = []
    for name, node in properties.items():
        if not isinstance(name, str) or name in GATEWAY_OWNED_FIELDS:
            continue
        if not isinstance(node, Mapping):
            observed.append(_observation(name, source=ENDPOINT_SOURCE))
            continue
        members = _union_members(_resolve_ref(node, schemas), schemas)
        observed.append(
            ProviderParameterObservation(
                request_path=_request_path(name),
                support="supported",
                source=ENDPOINT_SOURCE,
                schema=_endpoint_schema(members),
                deprecated=_is_deprecated(members),
            )
        )
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
# The closed-world tag marks the OME-629 per-model reading; the source-pair tag
# marks OME-647, where a snapshot stopped being one document and became two. In
# both cases the same bytes now yield a different snapshot, so entries cached
# under the previous label must not be reused — that is what the guard is for.
SNAPSHOT_SOURCE_REVISION = "openrouter:models+openapi:closed-world-source-pair-2026-07"

# Source-specific bounds for the OpenAPI document (§5.2 stays enforced — these are
# the bounds, not an exemption from them). MEASURED against the live document on
# 2026-07-28: 1,660,091 bytes, max depth 22, 38,055 nodes. The shared defaults
# (1,000,000 bytes / depth 16) reject it outright on TWO axes, and its node count
# already sits at 76% of the shared node ceiling.
# WHY per-source rather than a global increase: the models catalog is small and flat,
# and raising the envelope for every provider's every fetch to accommodate one large
# document would spend the safety margin where it was not needed. These values give
# the measured document roughly 2.4x headroom on bytes and nodes so ordinary upstream
# growth does not silently degrade the contract, while still capping memory.
# The timeout is widened for the same measured reason: reading 1.6 MB inside the 3s
# budget sized for the catalog needs a sustained ~550 KB/s, and a miss degrades the
# WHOLE snapshot (see the partial-source note below), not just this half.
_OPENAPI_MIN_TIMEOUT_S = 10.0
_OPENAPI_MIN_BYTES = 4_000_000
_OPENAPI_MIN_DEPTH = 32
_OPENAPI_MIN_NODES = 150_000


def openapi_discovery_limits(limits: DiscoveryLimits) -> DiscoveryLimits:
    """The operator's bounds, WIDENED where the OpenAPI document provably needs it.

    # INVARIANT (widen, never narrow): every axis is a ``max`` against what the
    # operator configured, so an installation that has deliberately raised a bound
    # keeps it. This helper can only ever admit more, never silently tighten a
    # limit an operator chose.
    """
    return DiscoveryLimits(
        timeout_s=max(limits.timeout_s, _OPENAPI_MIN_TIMEOUT_S),
        max_bytes=max(limits.max_bytes, _OPENAPI_MIN_BYTES),
        max_json_depth=max(limits.max_json_depth, _OPENAPI_MIN_DEPTH),
        max_json_nodes=max(limits.max_json_nodes, _OPENAPI_MIN_NODES),
    )


async def discover_openrouter_snapshot(
    upstream_model_id: str,
    *,
    client: DiscoveryHttpClient,
    limits: DiscoveryLimits | None = None,
) -> ProviderDiscoverySnapshot:
    """Fetch BOTH fixed public documents and return the provider's live evidence.

    §5.1 names a source PAIR: the ``/api/v1/models`` catalog for what one model
    supports, and the public OpenAPI document for what the endpoint accepts, its
    field shapes, and their lifecycle. Both are fetched through the injected bounded
    transport; the OpenAPI half under its own measured bounds.

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
    # WHY a PARTIAL failure also propagates: one snapshot is one revision's evidence
    # from both documents, and the cache stores whatever is returned as a successful
    # refresh. Returning the half that succeeded would therefore cache a contract
    # that is silently missing the other half — the same swallowing bug in a new
    # place. Trade-off, accepted deliberately: the catalog evidence that ships today
    # now degrades whenever the larger OpenAPI document is unreachable, which the
    # stale/degraded machinery already handles honestly.
    # INVARIANT (§5.1): the two kinds stay in SEPARATE snapshot fields and keep
    # DISTINCT source labels; nothing here merges them into one support verdict.
    """
    effective = limits or DiscoveryLimits()
    catalog = await fetch_discovery_json(
        MODELS_URL,
        allowed_origins=ALLOWED_ORIGINS,
        client=client,
        limits=effective,
    )
    openapi = await fetch_discovery_json(
        OPENAPI_URL,
        allowed_origins=ALLOWED_ORIGINS,
        client=client,
        limits=openapi_discovery_limits(effective),
    )
    return ProviderDiscoverySnapshot(
        source_revision=SNAPSHOT_SOURCE_REVISION,
        endpoint_observations=parse_openapi_endpoint_observations(
            openapi, schema_name=CHAT_REQUEST_SCHEMA
        ),
        model_observations=parse_model_catalog_observations(
            catalog, upstream_model_id=upstream_model_id
        ),
    )
