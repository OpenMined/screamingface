"""NATS subject and JetStream stream naming, built from one prefix so subject
strings aren't hand-formatted at each call site.

A SHARED LEAF: both `screamingface-engine serve` (which subscribes) and
`screamingface-engine run` (which publishes) import this, and the layering gate
names it as one of the three modules allowed to sit on that line. It used to be
duplicated across two distributions with a contract test pinning the copies
together; one module means there is nothing left to drift.
"""

from __future__ import annotations

PREFIX = "url4-cloud"


def subject_for(topic: str) -> str:
    return f"{PREFIX}.{topic}"


def stream_for(topic: str) -> str:
    return f"{PREFIX}_{topic}"


def owns_stream(stream_name: str) -> bool:
    """Whether a stream on the broker is one of ours.

    INVARIANT: the NATS store may be shared with other workloads. Reclamation enumerates every
    stream the broker holds, so this is what keeps a sweep from deleting a stranger's data.
    """
    return stream_name.startswith(f"{PREFIX}_")


def topic_of(stream_name: str) -> str:
    """Inverse of :func:`stream_for`. Callers must check :func:`owns_stream` first."""
    return stream_name.removeprefix(f"{PREFIX}_")


__all__ = ["owns_stream", "stream_for", "subject_for", "topic_of"]
