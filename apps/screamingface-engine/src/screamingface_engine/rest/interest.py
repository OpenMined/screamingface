"""The port ``routes.py`` uses to check whether a topic has an attached WebSocket subscriber.

``start_run`` requires a subscriber to be attached before scheduling a run (spec precondition,
returned as a 428 problem otherwise); the real implementation lives with the WebSocket transport
and is wired into ``app.state.interest``.
"""

from typing import Protocol


class SubscriberGate(Protocol):
    """Port for checking whether a topic currently has an attached WebSocket subscriber."""

    async def has_subscriber(self, topic: str) -> bool: ...


class DenyAllGate:
    """Fail-closed default: reports no topic as having a subscriber.

    Used when no real gate has been wired into app state, so runs are refused rather than
    started without anyone attached to observe them.
    """

    async def has_subscriber(self, topic: str) -> bool:
        return False
