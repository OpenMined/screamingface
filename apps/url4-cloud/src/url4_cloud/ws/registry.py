"""In-process bookkeeping of active WebSocket subscribers per topic."""


class ConnectionRegistry:
    """Tracks how many live WS connections are attached to each topic.

    Counts, rather than sets of connection ids, so concurrent connections on the
    same topic are supported without the endpoint having to hand back a token.
    """

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    def add(self, topic: str) -> None:
        self._counts[topic] = self._counts.get(topic, 0) + 1

    def remove(self, topic: str) -> None:
        remaining = self._counts.get(topic, 0) - 1
        if remaining > 0:
            self._counts[topic] = remaining
        else:
            self._counts.pop(topic, None)

    async def has_subscriber(self, topic: str) -> bool:
        return self._counts.get(topic, 0) > 0
