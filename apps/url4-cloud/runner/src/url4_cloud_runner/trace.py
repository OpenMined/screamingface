"""Shared W3C ``traceparent`` parsing/validation (trace PRD §7.4/§7.5).

STRICT format only: ``00-<32-hex trace-id>-<16-hex parent-id>-<2-hex flags>`` — the W3C "restart"
rule applies to anything else (absent or malformed inbound trace context never propagates; a fresh
trace is minted downstream instead). Reused by :mod:`~url4_cloud_runner.publish` (establishing the
run-root context from an inbound ``traceparent``) and ``url4_cloud.rest.routes`` (deciding whether
an inbound request header is valid enough to forward into ``JobRunner.schedule``) — factored here,
in the package both already depend on (``url4_cloud`` already imports ``url4_cloud_runner``, e.g.
``InProcessJobRunner``), so the pattern isn't copied three times.
"""

from __future__ import annotations

import re

_TRACEPARENT_RE = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}$")
_ALL_ZERO_TRACE = "0" * 32
_ALL_ZERO_SPAN = "0" * 16


def parse_traceparent(value: str | None) -> str | None:
    """The trace-id (32-hex) from a strictly W3C-valid ``traceparent``, or ``None`` when ``value``
    is absent or malformed (any deviation from the strict format — never a garbage-in echo).

    Per W3C Trace Context §3.2.2.3 an all-zero trace-id or parent-id is invalid and is treated as
    malformed here too (restart with a fresh trace downstream), so the null sentinel never
    propagates and poisons a run's ``trace_id``."""
    if not value:
        return None
    match = _TRACEPARENT_RE.match(value)
    if match is None or match.group(1) == _ALL_ZERO_TRACE or match.group(2) == _ALL_ZERO_SPAN:
        return None
    return match.group(1)


__all__ = ["parse_traceparent"]
