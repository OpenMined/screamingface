from __future__ import annotations

import re

_TRACEPARENT_RE = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}$")
_ALL_ZERO_TRACE = "0" * 32
_ALL_ZERO_SPAN = "0" * 16

_VERSION = "00"
_SAMPLED = "01"


def format_traceparent(trace_id: str, span_id: str) -> str:
    return f"{_VERSION}-{trace_id}-{span_id}-{_SAMPLED}"


def format_parent_tracestate(parent_span_id: str) -> str:
    return f"url4.parent={parent_span_id}"


def parse_traceparent(value: str | None) -> str | None:
    if not value:
        return None
    match = _TRACEPARENT_RE.match(value)
    if match is None or match.group(1) == _ALL_ZERO_TRACE or match.group(2) == _ALL_ZERO_SPAN:
        return None
    return match.group(1)


def valid_traceparent(value: str | None) -> str | None:
    return value if parse_traceparent(value) is not None else None


__all__ = [
    "format_parent_tracestate",
    "format_traceparent",
    "parse_traceparent",
    "valid_traceparent",
]
