"""Client-owned ports for SF Engine integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from screamingface._evaluation import Candidate
    from screamingface.events import Event
    from screamingface.report import Usage

type SyncEventObserver = Callable[[Event], None]
type AsyncEventObserver = Callable[[Event], None | Awaitable[None]]


@dataclass(frozen=True, slots=True)
class _RunOutcome:
    """Transport-neutral root result retained for strict Report decoding."""

    run_id: str
    started_at: datetime
    completed_at: datetime
    result_body: str
    media_type: str | None
    root_usage: Usage | None


class SyncRunTransport(Protocol):
    """Execute one inspected Candidate through an SF Engine."""

    def run(
        self,
        candidate: Candidate,
        on_event: SyncEventObserver | None,
    ) -> _RunOutcome: ...

    def close(self) -> None: ...


class AsyncRunTransport(Protocol):
    """Asynchronous counterpart of :class:`SyncRunTransport`."""

    async def run(
        self,
        candidate: Candidate,
        on_event: AsyncEventObserver | None,
    ) -> _RunOutcome: ...

    async def close(self) -> None: ...


__all__: list[str] = []
