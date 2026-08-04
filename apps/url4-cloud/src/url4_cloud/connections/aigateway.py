"""AI Gateway adapter for the SF Engine provider-connection port."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from url4_cloud.connections.port import (
    AuthMethod,
    Caller,
    Connection,
    ConnectionBadResponse,
    ConnectionConflict,
    ConnectionMethodUnsupported,
    ConnectionNotFound,
    ConnectionRateLimited,
    ConnectionRejected,
    ConnectionStatus,
    ConnectionTimeout,
    ConnectionUnavailable,
    OAuthAuthorization,
)

logger = logging.getLogger(__name__)

_PROVIDERS_PATH = "/v1/providers"
_CONNECTIONS_PATH = "/v1/oauth/connections"
_API_KEY_PATH = f"{_CONNECTIONS_PATH}/api-key"
_MANAGED_LABEL = "screamingface"


@dataclass(frozen=True, slots=True)
class _Provider:
    id: str
    display_name: str
    auth_methods: tuple[AuthMethod, ...]


class AigatewayConnections:
    """Combine AI Gateway provider capabilities with caller-scoped connection state."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def list(self, caller: Caller) -> tuple[Connection, ...]:
        providers = await self._providers(caller)
        rows = await self._rows(caller)
        return tuple(
            _disconnected(provider)
            if (selected := _select(rows, provider.id)) is None
            else _public(selected, provider)
            for provider in providers
        )

    async def connect(self, caller: Caller, provider: str, api_key: str) -> Connection:
        selected_provider = _provider(await self._providers(caller), provider)
        if "api_key" not in selected_provider.auth_methods:
            raise ConnectionMethodUnsupported()
        rows = await self._rows(caller, provider=provider)
        selected = _select(rows, provider)
        if selected is None:
            response = await self._request(
                "POST",
                _API_KEY_PATH,
                caller,
                json={"provider": provider, "label": _MANAGED_LABEL, "api_key": api_key},
            )
        else:
            response = await self._request(
                "PUT",
                f"{_CONNECTIONS_PATH}/{selected['id']}/api-key",
                caller,
                json={"api_key": api_key},
            )
        return _public(_decode_row(response), selected_provider)

    async def start_oauth(self, caller: Caller, provider: str) -> OAuthAuthorization:
        selected_provider = _provider(await self._providers(caller), provider)
        if "oauth" not in selected_provider.auth_methods:
            raise ConnectionMethodUnsupported()
        rows = await self._rows(caller, provider=provider)
        selected = _select(rows, provider)
        if selected is not None:
            await self._request(
                "DELETE",
                f"{_CONNECTIONS_PATH}/{selected['id']}",
                caller,
            )
        response = await self._request(
            "POST",
            _CONNECTIONS_PATH,
            caller,
            json={"provider": provider, "label": _MANAGED_LABEL},
        )
        return _decode_oauth_authorization(response, provider)

    async def disconnect(self, caller: Caller, provider: str) -> Connection:
        selected_provider = _provider(await self._providers(caller), provider)
        rows = await self._rows(caller, provider=provider)
        selected = _select(rows, provider)
        if selected is None:
            return _disconnected(selected_provider)
        await self._request("DELETE", f"{_CONNECTIONS_PATH}/{selected['id']}", caller)
        return _disconnected(selected_provider)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _providers(self, caller: Caller) -> tuple[_Provider, ...]:
        response = await self._request("GET", _PROVIDERS_PATH, caller)
        body = _decode_object(response)
        if body.get("object") != "list" or not isinstance(body.get("data"), list):
            raise ConnectionBadResponse()
        providers = tuple(_validate_provider(row) for row in body["data"])
        ids = tuple(provider.id for provider in providers)
        if len(ids) != len(set(ids)):
            raise ConnectionBadResponse()
        return providers

    async def _rows(self, caller: Caller, *, provider: str | None = None) -> list[dict[str, Any]]:
        response = await self._request(
            "GET",
            _CONNECTIONS_PATH,
            caller,
            params={"provider": provider} if provider is not None else None,
        )
        body = _decode_object(response)
        rows = body.get("connections")
        if not isinstance(rows, list):
            raise ConnectionBadResponse()
        return [_validate_row(row) for row in rows]

    async def _request(
        self,
        method: str,
        path: str,
        caller: Caller,
        *,
        params: Mapping[str, str] | None = None,
        json: dict[str, str] | None = None,
    ) -> httpx.Response:
        try:
            response = await self._client.request(
                method,
                path,
                headers=dict(caller.identity),
                params=params,
                json=json,
            )
        except httpx.TimeoutException as exc:
            logger.warning("AI Gateway provider-connection request timed out")
            raise ConnectionTimeout() from exc
        except httpx.HTTPError as exc:
            logger.warning(
                "AI Gateway provider-connection transport failure (%s)", type(exc).__name__
            )
            raise ConnectionUnavailable() from exc
        _raise_for_status(response)
        return response


def _provider(providers: tuple[_Provider, ...], provider: str) -> _Provider:
    selected = next((item for item in providers if item.id == provider), None)
    if selected is None:
        raise ConnectionNotFound()
    return selected


def _select(rows: list[dict[str, Any]], provider: str) -> dict[str, Any] | None:
    matching = [row for row in rows if row["provider"] == provider]
    managed = [row for row in matching if row["label"] == _MANAGED_LABEL]
    if len(managed) == 1:
        return managed[0]
    if len(managed) > 1:
        raise ConnectionConflict()
    if len(matching) == 1:
        return matching[0]
    return None


def _disconnected(provider: _Provider) -> Connection:
    return Connection(
        provider=provider.id,
        display_name=provider.display_name,
        auth_methods=provider.auth_methods,
        status="not_connected",
    )


def _public(row: Mapping[str, Any], provider: _Provider) -> Connection:
    if row["provider"] != provider.id:
        raise ConnectionBadResponse()
    status = {
        "active": "connected",
        "pending": "pending",
        "expired": "needs_reauth",
        "revoked": "needs_reauth",
        "error": "error",
    }.get(row["status"])
    if status is None:
        raise ConnectionBadResponse()
    auth_method = row["auth_type"]
    if auth_method not in provider.auth_methods:
        raise ConnectionBadResponse()
    return Connection(
        provider=provider.id,
        display_name=provider.display_name,
        auth_methods=provider.auth_methods,
        status=cast(ConnectionStatus, status),
        auth_method=cast(AuthMethod, auth_method),
        account_label=row.get("account") if auth_method == "oauth" else None,
    )


def _validate_provider(value: object) -> _Provider:
    if not isinstance(value, dict) or set(value) != {
        "object",
        "id",
        "display_name",
        "auth_methods",
    }:
        raise ConnectionBadResponse()
    methods = value.get("auth_methods")
    if (
        value.get("object") != "provider"
        or not isinstance(value.get("id"), str)
        or not value["id"].strip()
        or not isinstance(value.get("display_name"), str)
        or not value["display_name"].strip()
        or not isinstance(methods, list)
        or not methods
        or any(method not in {"api_key", "oauth"} for method in methods)
        or len(methods) != len(set(methods))
    ):
        raise ConnectionBadResponse()
    return _Provider(
        id=value["id"],
        display_name=value["display_name"],
        auth_methods=cast(tuple[AuthMethod, ...], tuple(methods)),
    )


def _decode_row(response: httpx.Response) -> dict[str, Any]:
    return _validate_row(_decode_object(response))


def _decode_oauth_authorization(
    response: httpx.Response,
    provider: str,
) -> OAuthAuthorization:
    body = _decode_object(response)
    if response.status_code != 201 or set(body) != {
        "connection_id",
        "authorize_url",
        "state",
        "expires_in",
    }:
        raise ConnectionBadResponse()
    authorize_url = body.get("authorize_url")
    expires_in = body.get("expires_in")
    connection_id = body.get("connection_id")
    state = body.get("state")
    if (
        not _is_uuid(connection_id)
        or not isinstance(state, str)
        or not state.strip()
        or not isinstance(authorize_url, str)
        or not _is_https_url(authorize_url)
        or isinstance(expires_in, bool)
        or not isinstance(expires_in, int)
        or expires_in < 1
    ):
        raise ConnectionBadResponse()
    return OAuthAuthorization(provider, authorize_url, expires_in)


def _is_https_url(value: str) -> bool:
    parts = urlsplit(value)
    return (
        parts.scheme == "https"
        and bool(parts.hostname)
        and parts.username is None
        and parts.password is None
    )


def _is_uuid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        UUID(value)
    except ValueError:
        return False
    return True


def _decode_object(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise ConnectionBadResponse() from exc
    if not isinstance(body, dict):
        raise ConnectionBadResponse()
    return body


def _validate_row(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConnectionBadResponse()
    required = {"id": str, "provider": str, "label": str, "status": str, "auth_type": str}
    if any(not isinstance(value.get(name), expected) for name, expected in required.items()):
        raise ConnectionBadResponse()
    return {
        "id": value["id"],
        "provider": value["provider"],
        "label": value["label"],
        "status": value["status"],
        "auth_type": value["auth_type"],
        "account": value.get("account") if isinstance(value.get("account"), str) else None,
    }


def _raise_for_status(response: httpx.Response) -> None:
    status = response.status_code
    if status < 300:
        return
    error = {
        # Provider capability is checked locally before a credential leaves the Engine.
        # AI Gateway also uses 400 for malformed credentials, so an upstream 400 is a
        # rejection—not evidence that the advertised method is unsupported.
        400: ConnectionRejected,
        401: ConnectionRejected,
        403: ConnectionRejected,
        404: ConnectionNotFound,
        409: ConnectionConflict,
        422: ConnectionRejected,
        429: ConnectionRateLimited,
        503: ConnectionUnavailable,
        504: ConnectionTimeout,
    }.get(status, ConnectionBadResponse)
    raise error()


__all__ = ["AigatewayConnections"]
