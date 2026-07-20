"""Safe adapter from public ScreamingFace connections to AI Gateway connections."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, NoReturn, cast
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from screamingface_engine.catalog import PROVIDER_ROUTES, AuthMethod, ProviderRoute
from screamingface_engine.gateway import GatewayClient, GatewayResponseTooLargeError

MANAGED_LABEL = "default"
MAX_GATEWAY_RESPONSE_BYTES = 262_144


class ConnectionGatewayError(Exception):
    """A sanitized connection-control failure safe for the public engine boundary."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        *,
        provider: str | None = None,
        retryable: bool = False,
    ) -> None:
        self.status = status
        self.code = code
        self.provider = provider
        self.retryable = retryable
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class GatewayConnection:
    id: UUID
    provider: ProviderRoute
    status: str
    auth_method: AuthMethod
    account_label: str | None

    def public(self) -> dict[str, object]:
        if self.auth_method not in self.provider.auth_methods:
            # A provider may temporarily stop advertising an auth method while an older
            # managed connection still exists. Keep that record removable/replaceable without
            # presenting the deprecated method as a usable public connection.
            return {
                "provider": self.provider.id,
                "status": "needs_reauth",
                "auth_method": None,
                "account_label": None,
            }
        return {
            "provider": self.provider.id,
            "status": _public_status(self.status),
            "auth_method": self.auth_method,
            "account_label": self.account_label,
        }


class ConnectionGateway:
    """One-connection-per-provider view over AI Gateway's general connection API."""

    def __init__(
        self,
        gateway: GatewayClient,
        *,
        codex_oauth_redirect_uri: str = "http://localhost:1455/auth/callback",
    ) -> None:
        self._gateway = gateway
        self._codex_oauth_redirect_uri = codex_oauth_redirect_uri

    def provider(self, provider_id: str) -> ProviderRoute:
        provider = next((item for item in PROVIDER_ROUTES if item.id == provider_id), None)
        if provider is None:
            raise ConnectionGatewayError(
                404,
                "unknown_provider",
                f"The engine does not advertise provider {provider_id!r}.",
                provider=provider_id,
            )
        return provider

    async def list_public(self) -> dict[str, object]:
        connections = await self._list_gateway_connections()
        return {
            "schema": "screamingface.connections.v1",
            "connections": [
                self._public_for(provider, connections) for provider in PROVIDER_ROUTES
            ],
        }

    async def get_public(self, provider: ProviderRoute) -> dict[str, object]:
        connections = await self._list_gateway_connections()
        return self._public_for(provider, connections)

    async def start_oauth(self, provider: ProviderRoute) -> dict[str, object]:
        self._require_method(provider, "oauth")
        existing = self._managed(provider, await self._list_gateway_connections())
        if existing is not None:
            await self._delete_gateway_connection(existing, provider)
        body = {"provider": provider.gateway_provider, "label": MANAGED_LABEL}
        if provider.id == "codex":
            # The official Codex OAuth client registers fixed loopback ports. The public
            # callback remains engine-owned; Compose maps this URI to the engine listener.
            body["redirect_uri"] = self._codex_oauth_redirect_uri
        payload = await self._json_request(
            "POST",
            "/v1/oauth/connections",
            provider=provider,
            json_body=body,
            expected_status={201},
        )
        try:
            _exact_fields(
                payload,
                {"connection_id", "authorize_url", "state", "expires_in"},
                "Gateway OAuth response",
            )
            UUID(_nonblank(payload["connection_id"], "Gateway OAuth connection_id"))
            authorize_url = _absolute_authorize_url(payload["authorize_url"])
            _nonblank(payload["state"], "Gateway OAuth state")
            expires_in = payload["expires_in"]
            if isinstance(expires_in, bool) or not isinstance(expires_in, int) or expires_in < 1:
                raise ValueError("Gateway OAuth expires_in must be a positive integer")
        except (TypeError, ValueError) as exc:
            self._invalid_gateway_response(provider, exc)
        return {
            "provider": provider.id,
            "status": "pending",
            "authorize_url": authorize_url,
            "expires_in": expires_in,
        }

    async def set_api_key(self, provider: ProviderRoute, api_key: str) -> dict[str, object]:
        self._require_method(provider, "api_key")
        existing = self._managed(provider, await self._list_gateway_connections())
        if existing is not None and existing.auth_method == "api_key":
            path = f"/v1/oauth/connections/{existing.id}/api-key"
            method = "PUT"
            body: dict[str, object] = {"api_key": api_key}
            statuses = {200}
        else:
            if existing is not None:
                await self._delete_gateway_connection(existing, provider)
            path = "/v1/oauth/connections/api-key"
            method = "POST"
            body = {
                "provider": provider.gateway_provider,
                "label": MANAGED_LABEL,
                "api_key": api_key,
            }
            statuses = {201}
        payload = await self._json_request(
            method,
            path,
            provider=provider,
            json_body=body,
            expected_status=statuses,
        )
        connection = self._parse_gateway_connection(payload, provider)
        if connection.auth_method != "api_key":
            self._invalid_gateway_response(provider, ValueError("unexpected auth_type"))
        return connection.public()

    async def disconnect(self, provider: ProviderRoute) -> None:
        existing = self._managed(provider, await self._list_gateway_connections())
        if existing is not None:
            await self._delete_gateway_connection(existing, provider)

    async def complete_callback(self, path: str, code: str, state: str) -> None:
        provider = next((item for item in PROVIDER_ROUTES if item.callback_path == path), None)
        if provider is None:
            raise ConnectionGatewayError(404, "unknown_callback", "Unknown OAuth callback path.")
        # Keep callback credentials out of the internal request target and access logs.
        await self._request(
            "POST",
            f"/v1/auth/{provider.gateway_provider}/exchange-code",
            provider=provider,
            json_body={"code": code, "state": state},
            expected_status={200},
        )

    async def _list_gateway_connections(self) -> tuple[GatewayConnection, ...]:
        payload = await self._json_request(
            "GET",
            "/v1/oauth/connections",
            provider=None,
            expected_status={200},
        )
        try:
            _exact_fields(payload, {"connections"}, "Gateway connection list")
            records = payload["connections"]
            if not isinstance(records, list):
                raise TypeError("Gateway connections must be a list")
            gateway_providers = {item.gateway_provider: item for item in PROVIDER_ROUTES}
            parsed: list[GatewayConnection] = []
            for value in records:
                if not isinstance(value, dict):
                    raise TypeError("Gateway connection records must be objects")
                gateway_provider = value.get("provider")
                provider = (
                    gateway_providers.get(gateway_provider)
                    if isinstance(gateway_provider, str)
                    else None
                )
                # INVARIANT: ScreamingFace owns only the private ``default`` label; unrelated
                # AI Gateway connections remain invisible and cannot break this projection.
                if provider is not None and value.get("label") == MANAGED_LABEL:
                    parsed.append(self._parse_gateway_connection(value, provider))
            return tuple(parsed)
        except (TypeError, ValueError) as exc:
            self._invalid_gateway_response(None, exc)

    def _parse_gateway_connection(
        self, payload: Mapping[str, object], provider: ProviderRoute
    ) -> GatewayConnection:
        try:
            connection_id = UUID(_nonblank(payload.get("id"), "Gateway connection id"))
            if payload.get("provider") != provider.gateway_provider:
                raise ValueError("Gateway connection provider mismatch")
            if payload.get("label") != MANAGED_LABEL:
                raise ValueError("Gateway connection label mismatch")
            status = _nonblank(payload.get("status"), "Gateway connection status")
            if status not in {"pending", "active", "expired", "error"}:
                raise ValueError(f"unsupported Gateway connection status {status!r}")
            auth_method = _nonblank(payload.get("auth_type"), "Gateway connection auth_type")
            if auth_method not in {"oauth", "api_key"}:
                raise ValueError("Gateway connection auth_type is unknown")
            account_label = _account_label(payload.get("account"))
        except (TypeError, ValueError) as exc:
            self._invalid_gateway_response(provider, exc)
        return GatewayConnection(
            connection_id,
            provider,
            status,
            cast(AuthMethod, auth_method),
            account_label,
        )

    def _public_for(
        self, provider: ProviderRoute, connections: tuple[GatewayConnection, ...]
    ) -> dict[str, object]:
        connection = self._managed(provider, connections)
        if connection is not None:
            return connection.public()
        return {
            "provider": provider.id,
            "status": "not_connected",
            "auth_method": None,
            "account_label": None,
        }

    def _managed(
        self, provider: ProviderRoute, connections: tuple[GatewayConnection, ...]
    ) -> GatewayConnection | None:
        selected = [item for item in connections if item.provider == provider]
        if len(selected) > 1:
            self._invalid_gateway_response(provider, ValueError("duplicate managed connection"))
        return selected[0] if selected else None

    def _require_method(self, provider: ProviderRoute, method: AuthMethod) -> None:
        if method not in provider.auth_methods:
            raise ConnectionGatewayError(
                400,
                "auth_method_not_supported",
                f"{provider.display_name} does not support {method!r} authentication.",
                provider=provider.id,
            )

    async def _delete_gateway_connection(
        self, connection: GatewayConnection, provider: ProviderRoute
    ) -> None:
        await self._request(
            "DELETE",
            f"/v1/oauth/connections/{connection.id}",
            provider=provider,
            expected_status={204, 404},
        )

    async def _json_request(
        self,
        method: str,
        path: str,
        *,
        provider: ProviderRoute | None,
        expected_status: set[int],
        json_body: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        response = await self._request(
            method,
            path,
            provider=provider,
            expected_status=expected_status,
            json_body=json_body,
        )
        try:
            return _unique_json_object(response.text)
        except (TypeError, ValueError) as exc:
            self._invalid_gateway_response(provider, exc)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        provider: ProviderRoute | None,
        expected_status: set[int],
        params: Mapping[str, str] | None = None,
        json_body: Mapping[str, object] | None = None,
    ) -> httpx.Response:
        try:
            response = await self._gateway.request(
                method,
                path,
                params=params,
                json=json_body,
                max_response_bytes=MAX_GATEWAY_RESPONSE_BYTES,
            )
        except httpx.TimeoutException as exc:
            raise ConnectionGatewayError(
                504,
                "gateway_timeout",
                "AI Gateway timed out.",
                provider=provider.id if provider else None,
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise ConnectionGatewayError(
                503,
                "gateway_unavailable",
                "AI Gateway is temporarily unavailable.",
                provider=provider.id if provider else None,
                retryable=True,
            ) from exc
        except GatewayResponseTooLargeError as exc:
            self._invalid_gateway_response(provider, exc)
        if response.status_code not in expected_status:
            self._raise_gateway_status(response, provider)
        return response

    def _raise_gateway_status(
        self, response: httpx.Response, provider: ProviderRoute | None
    ) -> NoReturn:
        gateway_code = _gateway_error_code(response)
        code, status, message, retryable = _normalized_error(gateway_code, response.status_code)
        raise ConnectionGatewayError(
            status,
            code,
            message,
            provider=provider.id if provider else None,
            retryable=retryable,
        )

    def _invalid_gateway_response(self, provider: ProviderRoute | None, exc: Exception) -> NoReturn:
        raise ConnectionGatewayError(
            502,
            "gateway_unavailable",
            "AI Gateway returned an invalid connection response.",
            provider=provider.id if provider else None,
            retryable=True,
        ) from exc


def _public_status(status: str) -> str:
    return {
        "active": "connected",
        "pending": "pending",
        "expired": "needs_reauth",
        "error": "needs_reauth",
    }[status]


def _account_label(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError("Gateway connection account must be an object or null")
    for field in ("email", "name", "sub"):
        candidate = value.get(field)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _absolute_authorize_url(value: object) -> str:
    url = _nonblank(value, "Gateway OAuth authorize_url")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Gateway OAuth authorize_url must be an absolute HTTPS URL")
    return url


def _gateway_error_code(response: httpx.Response) -> str | None:
    try:
        payload = _unique_json_object(response.text)
        detail = payload.get("detail")
        if isinstance(detail, Mapping):
            code = detail.get("code")
            return code if isinstance(code, str) else None
    except (TypeError, ValueError):
        return None
    return None


def _normalized_error(gateway_code: str | None, status: int) -> tuple[str, int, str, bool]:
    if gateway_code == "invalid_api_key":
        return "invalid_api_key", 400, "The API key is invalid.", False
    if gateway_code in {"api_key_not_supported", "provider_does_not_use_oauth"}:
        return "auth_method_not_supported", 400, "Authentication method is unsupported.", False
    if gateway_code in {"auth_required", "connection_not_active"}:
        return "connection_needs_reauth", 401, "The provider must be reconnected.", False
    if status in {401, 403}:
        return "provider_access_denied", status, "Provider access was denied.", False
    if status == 504:
        return "gateway_timeout", 504, "AI Gateway timed out.", True
    return "gateway_unavailable", 503, "AI Gateway is temporarily unavailable.", True


def _unique_json_object(body: str) -> dict[str, object]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON field {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(body, object_pairs_hook=unique)
    except json.JSONDecodeError as exc:
        raise ValueError("response is not JSON") from exc
    if not isinstance(value, dict):
        raise TypeError("expected a JSON object")
    return value


def _exact_fields(payload: Mapping[str, object], expected: set[str], label: str) -> None:
    missing = expected - set(payload)
    unknown = set(payload) - expected
    if missing:
        raise ValueError(f"{label} is missing fields: {sorted(missing)}")
    if unknown:
        raise ValueError(f"{label} has unknown fields: {sorted(unknown)}")


def _nonblank(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


__all__ = [
    "ConnectionGateway",
    "ConnectionGatewayError",
    "GatewayConnection",
    "MAX_GATEWAY_RESPONSE_BYTES",
]
