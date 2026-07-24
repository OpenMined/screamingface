"""``ConnectionRegistry`` — the live-WS ``SubscriberGate`` behind the REST ``428`` guard (spec §4).

The WebSocket endpoint registers a topic while a client is attached and deregisters on close; the
REST plane's ``SubscriberGate.has_subscriber`` reads this count. This is the real interest source
the ``428`` guard (``rest/interest.py``) was written to accept — a run must not begin with nobody
listening (spec §4). Single event loop, so a plain counter is sufficient (no locking).
"""


class ConnectionRegistry:
    """Counts live WebSocket connections per topic; satisfies the ``SubscriberGate`` port."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    def add(self, topic: str) -> None:
        self._counts[topic] = self._counts.get(topic, 0) + 1

    def remove(self, topic: str) -> None:
        # INVARIANT: never go negative; drop the key at zero so has_subscriber stays a membership.
        remaining = self._counts.get(topic, 0) - 1
        if remaining > 0:
            self._counts[topic] = remaining
        else:
            self._counts.pop(topic, None)

    async def has_subscriber(self, topic: str) -> bool:
        return self._counts.get(topic, 0) > 0
