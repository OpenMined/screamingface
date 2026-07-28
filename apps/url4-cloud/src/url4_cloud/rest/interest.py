"""The ``SubscriberGate`` port — the stateless NATS-interest check behind the ``428`` guard (§4).

A run must not begin with nobody listening (spec §4): ``GET`` is rejected ``428 Precondition
Required`` unless a live subscriber already has interest in the topic. In prod this is a NATS
subject-interest query; here it is a narrow injectable port (interface segregation — interest is
not the pub/sub transport's job) so the REST layer stays headless and the real gate can wire in
with the WebSocket bridge (OME-521) without touching this code.
"""

from typing import Protocol


class SubscriberGate(Protocol):
    """Reports whether a live subscriber currently has interest in ``topic`` (spec §4)."""

    async def has_subscriber(self, topic: str) -> bool: ...


class DenyAllGate:
    """Default gate: no subscriber is ever present.

    INVARIANT: a safe conservative default — until a real interest source is wired, every start is
    rejected ``428`` rather than allowed to run unobserved. Never reports a false positive.
    """

    async def has_subscriber(self, topic: str) -> bool:
        return False
