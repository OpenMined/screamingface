from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from url4.streaming.protocol import OutboundFrame


class EventPublisher(ABC):
    @abstractmethod
    async def ensure_stream(self, topic: str) -> None:
        pass

    @abstractmethod
    async def publish(self, topic: str, event: OutboundFrame) -> None:
        pass

    async def close(self) -> None:
        pass


class EventConsumer(ABC):
    @abstractmethod
    async def ensure_stream(self, topic: str) -> None:
        pass

    @abstractmethod
    def subscribe(
        self, topic: str, from_sequence: int | None = None
    ) -> AsyncIterator[OutboundFrame]:
        pass

    @abstractmethod
    async def purge(self, topic: str) -> None:
        pass

    async def delete_stream(self, topic: str) -> None:
        """Reclaim a topic for good — called once, on the terminal DELETE, never mid-run.

        Distinct from :meth:`purge` because for a broker-backed adapter they are different
        operations with different costs: purging empties a stream but leaves the stream object,
        its consumer state and its on-disk directory behind, so a purge-only teardown still
        accumulates one permanent stream per run. `purge` cannot simply be made to delete —
        `assert_stream_conformance` requires it to leave the sequence counter intact, and a
        recreated stream restarts at 1.

        Defaults to :meth:`purge` so an adapter with nothing broker-side to reclaim (the
        in-process log) needs no override, and so adding this never broke an existing
        implementer. Must be idempotent: a topic that is already gone is success, not an error.
        """
        await self.purge(topic)

    async def close(self) -> None:
        pass


class EventStream(EventPublisher, EventConsumer, ABC):
    pass


def validate_from_sequence(from_sequence: int | None) -> None:
    if from_sequence is not None and from_sequence < 1:
        raise ValueError(
            f"from_sequence must be >= 1 (1-based stream sequence), got {from_sequence}"
        )


__all__ = ["EventConsumer", "EventPublisher", "EventStream", "validate_from_sequence"]
