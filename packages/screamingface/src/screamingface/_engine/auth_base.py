"""Authentication interface consumed by Engine HTTP and WebSocket transports."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping

import httpx


class _TransportAuth(httpx.Auth, ABC):
    """Credentials required by the Engine HTTP and WebSocket transport."""

    requires_request_body = True

    @abstractmethod
    def reauthenticate(self, *, timeout: float = 300.0) -> None: ...

    @abstractmethod
    async def reauthenticate_async(self, *, timeout: float = 300.0) -> None: ...

    @abstractmethod
    def websocket_headers(self) -> Mapping[str, str]: ...

    @abstractmethod
    async def websocket_headers_async(self) -> Mapping[str, str]: ...

    @abstractmethod
    def close(self) -> None: ...


__all__: list[str] = []
