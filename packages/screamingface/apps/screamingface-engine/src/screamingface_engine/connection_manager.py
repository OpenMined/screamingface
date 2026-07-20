"""Public connection control composed from Gateway and engine-owned backends."""

from __future__ import annotations

from screamingface_engine.catalog import PUBLIC_PROVIDERS, PublicProvider
from screamingface_engine.connection_contract import ConnectionControlError
from screamingface_engine.connection_gateway import ConnectionGateway
from screamingface_engine.tavily import TAVILY_PROVIDER_ID, TavilyService


class ConnectionManager:
    """Route each advertised connection to its owning internal service."""

    def __init__(self, gateway: ConnectionGateway, tavily: TavilyService) -> None:
        self._gateway = gateway
        self._tavily = tavily

    def provider(self, provider_id: str) -> PublicProvider:
        provider = next((item for item in PUBLIC_PROVIDERS if item.id == provider_id), None)
        if provider is None:
            raise ConnectionControlError(
                404,
                "unknown_provider",
                f"The engine does not advertise provider {provider_id!r}.",
                provider=provider_id,
            )
        return provider

    async def list_public(self) -> dict[str, object]:
        gateway_payload = await self._gateway.list_public()
        gateway_connections = gateway_payload.get("connections")
        if not isinstance(gateway_connections, list):  # pragma: no cover - Gateway invariant
            raise ConnectionControlError(
                502,
                "gateway_unavailable",
                "AI Gateway returned an invalid connection response.",
                retryable=True,
            )
        return {
            "schema": "screamingface.connections.v1",
            "connections": [*gateway_connections, await self._tavily.get_public()],
        }

    async def get_public(self, provider: PublicProvider) -> dict[str, object]:
        if provider.id == TAVILY_PROVIDER_ID:
            return await self._tavily.get_public()
        return await self._gateway.get_public(self._gateway.provider(provider.id))

    async def start_oauth(self, provider: PublicProvider) -> dict[str, object]:
        if provider.id == TAVILY_PROVIDER_ID:
            raise ConnectionControlError(
                400,
                "auth_method_not_supported",
                "Tavily does not support 'oauth' authentication.",
                provider=TAVILY_PROVIDER_ID,
            )
        return await self._gateway.start_oauth(self._gateway.provider(provider.id))

    async def set_api_key(self, provider: PublicProvider, api_key: str) -> dict[str, object]:
        if provider.id == TAVILY_PROVIDER_ID:
            # INVARIANT: Tavily is an engine-owned tool connection. Its credential is never
            # forwarded to AI Gateway, URL4 evaluation, or a model message.
            return await self._tavily.set_api_key(api_key)
        return await self._gateway.set_api_key(self._gateway.provider(provider.id), api_key)

    async def disconnect(self, provider: PublicProvider) -> None:
        if provider.id == TAVILY_PROVIDER_ID:
            await self._tavily.disconnect()
            return
        await self._gateway.disconnect(self._gateway.provider(provider.id))

    async def complete_callback(self, path: str, code: str, state: str) -> None:
        await self._gateway.complete_callback(path, code, state)

    async def aclose(self) -> None:
        await self._tavily.aclose()


__all__ = ["ConnectionManager"]
