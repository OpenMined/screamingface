"""AI Gateway adapter for the SF Engine provider-connection port."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, cast

import httpx

from url4_cloud.connections.port import (
    Caller,
    Connection,
    ConnectionBadResponse,
    ConnectionConflict,
    ConnectionNotFound,
    ConnectionRateLimited,
    ConnectionRejected,
    ConnectionStatus,
    ConnectionTimeout,
    ConnectionUnavailable,
)

logger = logging.getLogger(__name__)

_CONNECTIONS_PATH = "/v1/oauth/connections"
_API_KEY_PATH = f"{_CONNECTIONS_PATH}/api-key"
_MANAGED_LABEL = "screamingface"
_PROVIDER = "openrouter"


class AigatewayConnections:
    """Manage OpenRouter credentials through AI Gateway without exposing its private records."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    @staticmethod
    def disconnected() -> Connection:
        return Connection.openrouter()

    async def list(self, caller: Caller) -> tuple[Connection, ...]:
        rows = await self._rows(caller)
        selected = _select(rows)
        return (self.disconnected() if selected is None else _public(selected),)

    async def connect(self, caller: Caller, provider: str, api_key: str) -> Connection:
        _require_provider(provider)
        rows = await self._rows(caller)
        selected = _select(rows)
        if selected is None:
            response = await self._request(
                "POST",
                _API_KEY_PATH,
                caller,
                json={"provider": _PROVIDER, "label": _MANAGED_LABEL, "api_key": api_key},
            )
        else:
            connection_id = selected["id"]
            response = await self._request(
                "PUT",
                f"{_CONNECTIONS_PATH}/{connection_id}/api-key",
                caller,
                json={"api_key": api_key},
            )
        return _public(_decode_row(response))

    async def disconnect(self, caller: Caller, provider: str) -> Connection:
        _require_provider(provider)
        rows = await self._rows(caller)
        selected = _select(rows)
        if selected is None:
            return self.disconnected()
        await self._request(
            "DELETE",
            f"{_CONNECTIONS_PATH}/{selected['id']}",
            caller,
        )
        return self.disconnected()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _rows(self, caller: Caller) -> list[dict[str, Any]]:
        response = await self._request(
            "GET",
            _CONNECTIONS_PATH,
            caller,
            params={"provider": _PROVIDER},
        )
        body = _decode_object(response)
        rows = body.get("connections")
        if not isinstance(rows, list):
            raise ConnectionBadResponse()
        decoded: list[dict[str, Any]] = []
        for row in rows:
            decoded.append(_validate_row(row))
        return decoded

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
                "AI Gateway provider-connection transport failure (%s)",
                type(exc).__name__,
            )
            raise ConnectionUnavailable() from exc
        _raise_for_status(response)
        return response


def _require_provider(provider: str) -> None:
    if provider != _PROVIDER:
        raise ConnectionNotFound()


def _select(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    managed = [row for row in rows if row["label"] == _MANAGED_LABEL]
    if len(managed) == 1:
        return managed[0]
    if len(managed) > 1:
        raise ConnectionConflict()
    # Preserve a lone pre-existing local connection for compatibility. When several unrelated
    # OpenRouter rows exist, do not guess or delete one: this surface manages its own named row.
    if len(rows) == 1:
        return rows[0]
    return None


def _public(row: Mapping[str, Any]) -> Connection:
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
    if auth_method not in {"api_key", "oauth"}:
        raise ConnectionBadResponse()
    return Connection.openrouter(
        status=cast(ConnectionStatus, status),
        auth_method=auth_method,
        # API-key labels are internal handles, not user-facing accounts.
        account_label=row.get("account") if auth_method == "oauth" else None,
    )


def _decode_row(response: httpx.Response) -> dict[str, Any]:
    return _validate_row(_decode_object(response))


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
    required = {
        "id": str,
        "provider": str,
        "label": str,
        "status": str,
        "auth_type": str,
    }
    if any(not isinstance(value.get(name), expected) for name, expected in required.items()):
        raise ConnectionBadResponse()
    if value["provider"] != _PROVIDER:
        raise ConnectionBadResponse()
    # Copy only fields needed below. Private identifiers/credential locators never enter
    # the public domain value and cannot leak through repr or response serialization.
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
    if status in {400, 401, 403, 422}:
        raise ConnectionRejected()
    if status == 404:
        raise ConnectionNotFound()
    if status == 409:
        raise ConnectionConflict()
    if status == 429:
        raise ConnectionRateLimited()
    if status == 503:
        raise ConnectionUnavailable()
    if status == 504:
        raise ConnectionTimeout()
    raise ConnectionBadResponse()


__all__ = ["AigatewayConnections"]
