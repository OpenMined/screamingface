"""Client-owned ports for SF Engine integration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

import httpx

if TYPE_CHECKING:
    from screamingface._evaluation.model import Candidate
    from screamingface.events import Event
    from screamingface.report import Usage

type SyncEventObserver = Callable[[Event], None]
type AsyncEventObserver = Callable[[Event], None | Awaitable[None]]


class _CallerAuth(httpx.Auth, ABC):
    """Core-owned caller credential port shared by HTTP and WebSocket adapters."""

    requires_request_body = True

    @property
    @abstractmethod
    def authenticated(self) -> bool: ...

    @property
    @abstractmethod
    def authenticating(self) -> bool: ...

    @abstractmethod
    def login(self, *, timeout: float = 300.0) -> None: ...

    @abstractmethod
    async def login_async(self, *, timeout: float = 300.0) -> None: ...

    @abstractmethod
    def cancel_login(self) -> None: ...

    @abstractmethod
    def access_required(self) -> bool: ...

    @abstractmethod
    def reauthenticate(self, *, timeout: float = 300.0) -> None: ...

    @abstractmethod
    async def reauthenticate_async(self, *, timeout: float = 300.0) -> None: ...

    @abstractmethod
    def logout(self) -> None: ...

    @abstractmethod
    async def logout_async(self) -> None: ...

    @abstractmethod
    def websocket_headers(self) -> Mapping[str, str]: ...

    @abstractmethod
    async def websocket_headers_async(self) -> Mapping[str, str]: ...

    @abstractmethod
    def close(self) -> None: ...


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
