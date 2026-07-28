"""NATS subject and JetStream stream naming, built from one prefix so subject strings aren't
hand-formatted at each call site.

A SHARED LEAF: both `url4-cloud serve` (which subscribes) and `url4-cloud run` (which publishes)
import this, and the layering gate names it as one of the three modules allowed to sit on that
line. It used to be duplicated across two distributions with a contract test pinning the copies
together; one module means there is nothing left to drift.
"""

from __future__ import annotations

PREFIX = "url4-cloud"


def subject_for(topic: str) -> str:
    return f"{PREFIX}.{topic}"


def stream_for(topic: str) -> str:
    return f"{PREFIX}_{topic}"


__all__ = ["stream_for", "subject_for"]
