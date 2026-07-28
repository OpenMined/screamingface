"""The single source of protocol-event constants (which events flow which direction, their
CloudEvents `type` strings) and the JSON Schema generated from their pydantic models — shared
by the AsyncAPI and OpenAPI doc builders so both describe the same wire shapes."""

from typing import Any

from pydantic.json_schema import models_json_schema

from url4.streaming.protocol import (
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

COST_USAGE_EXAMPLE: dict[str, Any] = {
    "scope": "self",
    "gen_ai.provider.name": "anthropic",
    "gen_ai.response.model": "claude-opus-4-8",
    "pricing_version": "2026-07-01",
    "usage": {"gen_ai.usage.input_tokens": 1200, "gen_ai.usage.output_tokens": 340},
    "cost": {"input_usd": "0.0180", "output_usd": "0.0255", "total_usd": "0.0435"},
}


def protocol_component_schemas() -> dict[str, Any]:
    """Generates the `components/schemas` map for every protocol event (by-alias serialization
    shape), with a worked example spliced onto `CostUsageData` for the docs."""
    _, top = models_json_schema(
        [(model, "serialization") for model in ALL_EVENTS],
        by_alias=True,
        ref_template=REF_TEMPLATE,
    )
    schemas: dict[str, Any] = dict(top.get("$defs", {}))
    if "CostUsageData" in schemas:
        schemas["CostUsageData"] = {**schemas["CostUsageData"], "examples": [COST_USAGE_EXAMPLE]}
    return schemas
