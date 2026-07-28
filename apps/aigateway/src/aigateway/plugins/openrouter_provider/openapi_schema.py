"""OME-647 — reading the OpenRouter OpenAPI document's chat request schema.

FEATURE: OpenRouter endpoint evidence. Reports each accepted optional field of
the chat request body together with its SHAPE and its LIFECYCLE verdict, as the
public document declares them.

INVARIANT: pure over an already-fetched, already-bounded document — no network,
no clock, no credentials. The transport, its measured bounds and the fetch
orchestration all live in ``discovery``.

INVARIANT: this is EVIDENCE. A schema published here describes what the ENDPOINT
accepts; it never validates a caller's value, and a ``deprecated`` verdict
disables nothing.

AIDEV-NOTE: import ``parse_openapi_endpoint_observations`` from ``discovery`` —
it is re-exported there so one module remains the import path for both parsers.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aigateway.core.chat_parameters import (
    ParameterSchema,
    ProviderParameterObservation,
    SchemaItemType,
    SchemaType,
)
from aigateway.core.parameter_projection import GATEWAY_OWNED_FIELDS

from .observations import ENDPOINT_SOURCE, _dedup_sorted, _observation, _request_path

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
