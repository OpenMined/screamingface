"""Composition root for SF Engine transport adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from screamingface._authentication import _CallerAuth
from screamingface._ports import AsyncRunTransport, SyncRunTransport


class _SyncTransportFactory(Protocol):
    def __call__(self, engine_url: str, caller_auth: _CallerAuth) -> SyncRunTransport: ...


class _AsyncTransportFactory(Protocol):
    def __call__(self, engine_url: str, caller_auth: _CallerAuth) -> AsyncRunTransport: ...


@dataclass(frozen=True, slots=True)
class _TransportRegistry:
    """Factories selected once at the Client composition boundary."""

    sync: _SyncTransportFactory
    async_: _AsyncTransportFactory


def _default_transport_registry() -> _TransportRegistry:
    """Register the confirmed REST + WebSocket Engine adapters."""

    from screamingface._transport import AsyncUrl4CloudTransport, Url4CloudTransport

    return _TransportRegistry(
        sync=Url4CloudTransport,
        async_=AsyncUrl4CloudTransport,
    )


__all__: list[str] = []
