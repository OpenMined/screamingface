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
