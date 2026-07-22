"""Shared CloudEvents JSON-Schema (2020-12) component set (spec §12, docs/protocol.md §4).

One authored source of truth for both the OpenAPI (REST) and AsyncAPI (WS) documents: the ten
``url4_streaming_protocol`` event models, emitted with their nested payloads/taxonomy hoisted into a
flat ``components.schemas`` map whose ``$ref``s already point at ``#/components/schemas/{model}``.
"""

from typing import Any

from pydantic.json_schema import models_json_schema

from url4_streaming_protocol import (
    AttachEvent,
    CostUsageEvent,
    ErrorEvent,
    HeartbeatEvent,
    LogEvent,
    ResultEvent,
    SpanEvent,
    StartedEvent,
    StopEvent,
    TerminatedEvent,
)

# INVARIANT: order = outbound (engine→app→client) then inbound (client→app→engine), protocol.md §4.
OUTBOUND_EVENTS: tuple[type, ...] = (
    StartedEvent,
    LogEvent,
    SpanEvent,
    CostUsageEvent,
    HeartbeatEvent,
    ResultEvent,
    TerminatedEvent,
    ErrorEvent,
)
INBOUND_EVENTS: tuple[type, ...] = (StopEvent, AttachEvent)
ALL_EVENTS: tuple[type, ...] = OUTBOUND_EVENTS + INBOUND_EVENTS

REF_TEMPLATE = "#/components/schemas/{model}"

# The CloudEvents `type` (reverse-DNS) each event class fixes — used as the AsyncAPI message name.
EVENT_TYPE: dict[str, str] = {
    "StartedEvent": "ai.url4.started",
    "LogEvent": "ai.url4.log",
    "SpanEvent": "ai.url4.span",
    "CostUsageEvent": "ai.url4.cost.usage",
    "HeartbeatEvent": "ai.url4.heartbeat",
    "ResultEvent": "ai.url4.result",
    "TerminatedEvent": "ai.url4.terminated",
    "ErrorEvent": "ai.url4.error",
    "StopEvent": "ai.url4.stop",
    "AttachEvent": "ai.url4.attach",
}

# WHY: the implemented `CostUsageData` model carries no class example (§7.1 authoring is deferred to
# the served docs, keeping the protocol package free of doc concerns); attach a realistic one here
# so Scalar's sample pane — and the §12 DOC-GATE — see every field on the wire (with OTel aliases).
COST_USAGE_EXAMPLE: dict[str, Any] = {
    "scope": "self",
    "gen_ai.provider.name": "anthropic",
    "gen_ai.response.model": "claude-opus-4-8",
    "pricing_version": "2026-07-01",
    "usage": {"gen_ai.usage.input_tokens": 1200, "gen_ai.usage.output_tokens": 340},
    "cost": {"input_usd": "0.0180", "output_usd": "0.0255", "total_usd": "0.0435"},
}


def protocol_component_schemas() -> dict[str, Any]:
    """The flat ``{name: json-schema}`` map for every CloudEvents event + its nested payloads."""
    _, top = models_json_schema(
        [(model, "serialization") for model in ALL_EVENTS],
        by_alias=True,
        ref_template=REF_TEMPLATE,
    )
    schemas: dict[str, Any] = dict(top.get("$defs", {}))
    # Author the CostUsageData example onto its component (never mutating the protocol model).
    if "CostUsageData" in schemas:
        schemas["CostUsageData"] = {**schemas["CostUsageData"], "example": COST_USAGE_EXAMPLE}
    return schemas
