"""Provider connection values and private ScreamingFace engine client."""

from __future__ import annotations

import builtins
import time
from dataclasses import dataclass, field
from typing import Literal, cast, overload
from urllib.parse import urlsplit

import httpx

from screamingface._config import current_engine_url
from screamingface._engine_http import exact_fields, nonblank, object_value, unique_json_object
from screamingface._profile import AuthMethod, ProviderRecord, load_registry
from screamingface.errors import (
    AuthMethodRequiredError,
    EngineConnectionError,
    EngineProtocolError,
    ProviderConnectionError,
    SecureTransportRequiredError,
    UnknownProviderError,
    UnsupportedAuthMethodError,
)

type ConnectionStatus = Literal["not_connected", "pending", "connected", "needs_reauth", "error"]

CONNECTIONS_SCHEMA = "screamingface.connections.v1"
ERROR_SCHEMA = "screamingface.error.v1"
_STATUSES = {"not_connected", "pending", "connected", "needs_reauth", "error"}
_ERROR_TYPES = {
    "unknown_provider": UnknownProviderError,
    "auth_method_required": AuthMethodRequiredError,
    "auth_method_not_supported": UnsupportedAuthMethodError,
}
_transport: httpx.BaseTransport | None = None


@dataclass(frozen=True, slots=True)
class Connection:
    """Sanitized current-user connection state enriched with public capabilities."""

    provider: str
    display_name: str
    auth_methods: tuple[AuthMethod, ...]
    status: ConnectionStatus
    auth_method: AuthMethod | None
    account_label: str | None

    def __post_init__(self) -> None:
        if self.status not in _STATUSES:
            raise ValueError(f"unknown connection status {self.status!r}")
        if self.auth_method is not None and self.auth_method not in self.auth_methods:
            raise ValueError("connection auth_method is not advertised by its provider")


@dataclass(frozen=True, slots=True)
class OAuthFlow:
    """A bounded provider authorization attempt tied to its originating engine."""

    provider: str
    authorize_url: str
    status: Literal["pending"] = "pending"
    _engine_url: str = field(default="", repr=False)
    _provider_record: ProviderRecord | None = field(default=None, repr=False)
    _expires_at: float = field(default=0.0, repr=False)

    def wait(self, *, poll_interval: float = 0.5) -> Connection:
        """Poll until authorization completes or this flow expires."""

        if isinstance(poll_interval, bool) or not isinstance(poll_interval, (int, float)):
            raise TypeError("poll_interval must be a non-negative number")
        if poll_interval < 0:
            raise ValueError("poll_interval must be a non-negative number")
        provider = self._required_provider_record()
        while time.monotonic() <= self._expires_at:
            connection = _get_connection(provider, engine_url=self._engine_url)
            if connection.status != "pending":
                return connection
            time.sleep(poll_interval)
        raise ProviderConnectionError(
            f"Authorization for {provider.display_name} expired.",
            code="connection_pending",
            provider=provider.id,
        )

    def cancel(self) -> None:
        """Cancel this attempt; repeated cancellation remains harmless."""

        provider = self._required_provider_record()
        _request(
            "DELETE",
            f"/v1/connections/{provider.id}",
            engine_url=self._engine_url,
            expect_empty=True,
        )

    def _required_provider_record(self) -> ProviderRecord:
        if self._provider_record is None or not self._engine_url:
            raise ValueError("OAuthFlow values are created by sf.connect(...)")
        return self._provider_record


def list() -> tuple[Connection, ...]:
    """Return fresh, sanitized connection state for every advertised provider."""

    registry = load_registry()
    payload = _request("GET", "/v1/connections")
    return _decode_connection_list(payload, registry.providers)


def _decode_connection_list(
    payload: dict[str, object], advertised: tuple[ProviderRecord, ...]
) -> tuple[Connection, ...]:
    try:
        return _decode_connection_list_value(payload, advertised)
    except (TypeError, ValueError) as exc:
        raise EngineProtocolError(f"invalid connections response: {exc}") from exc


def _decode_connection_list_value(
    payload: dict[str, object], advertised: tuple[ProviderRecord, ...]
) -> tuple[Connection, ...]:
    exact_fields(payload, {"schema", "connections"}, "connections response")
    if payload["schema"] != CONNECTIONS_SCHEMA:
        raise EngineProtocolError(f"expected connection schema {CONNECTIONS_SCHEMA!r}")
    records = payload["connections"]
    if not isinstance(records, builtins.list):
        raise EngineProtocolError("connections must be a list")
    providers = {provider.id: provider for provider in advertised}
    result: builtins.list[Connection] = []
    seen: set[str] = set()
    for value in records:
        try:
            record = object_value(value, "connection record")
            provider_id = nonblank(record.get("provider"), "connection provider")
            if provider_id in seen:
                raise ValueError(f"duplicate connection provider {provider_id!r}")
            provider = providers.get(provider_id)
            if provider is None:
                raise ValueError(f"unknown connection provider {provider_id!r}")
            seen.add(provider_id)
            result.append(_decode_connection(record, provider))
        except (TypeError, ValueError) as exc:
            raise EngineProtocolError(f"invalid connections response: {exc}") from exc
    if seen != set(providers):
        missing = ", ".join(sorted(set(providers) - seen))
        raise EngineProtocolError(f"connections response is missing provider(s): {missing}")
    return tuple(result)


@overload
def connect(
    provider: None = None, *, method: None = None, api_key: None = None
) -> tuple[Connection, ...]: ...


@overload
def connect(provider: str, *, method: Literal["oauth"], api_key: None = None) -> OAuthFlow: ...


@overload
def connect(
    provider: str,
    *,
    method: Literal["api_key"] | None = None,
    api_key: str,
) -> Connection: ...


@overload
def connect(
    provider: str, *, method: None = None, api_key: None = None
) -> Connection | OAuthFlow: ...


def connect(
    provider: str | None = None,
    *,
    method: AuthMethod | None = None,
    api_key: str | None = None,
) -> tuple[Connection, ...] | Connection | OAuthFlow:
    """List connections or start/update one provider connection."""

    if provider is None:
        return _connect_without_provider(method=method, api_key=api_key)
    selected = _provider(provider)
    if api_key is not None:
        return _connect_api_key(selected, method=method, api_key=api_key)
    if method == "api_key":
        raise ValueError("api_key is required for API-key authentication")
    action = _oauth_action(selected, method)
    return action if isinstance(action, Connection) else _start_oauth(selected, action)


def _connect_without_provider(
    *, method: AuthMethod | None, api_key: str | None
) -> tuple[Connection, ...]:
    if method is not None or api_key is not None:
        raise TypeError("provider is required when method or api_key is supplied")
    return list()


def _connect_api_key(
    provider: ProviderRecord, *, method: AuthMethod | None, api_key: str
) -> Connection:
    if method not in {None, "api_key"}:
        raise ValueError("api_key cannot be combined with OAuth")
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("api_key must be a non-empty string")
    _require_method(provider, "api_key")
    payload = _request(
        "PUT",
        f"/v1/connections/{provider.id}/api-key",
        json_body={"api_key": api_key},
    )
    return _decode_connection_response(payload, provider)


def _oauth_action(provider: ProviderRecord, method: AuthMethod | None) -> AuthMethod | Connection:
    if method is not None:
        return method
    current = _get_connection(provider)
    if current.status == "connected":
        return current
    if len(provider.auth_methods) != 1:
        methods = ", ".join(provider.auth_methods)
        raise AuthMethodRequiredError(
            f"{provider.display_name} supports {methods}; choose method or pass api_key.",
            code="auth_method_required",
            provider=provider.id,
        )
    return provider.auth_methods[0]


def _start_oauth(selected: ProviderRecord, method: AuthMethod) -> OAuthFlow:
    _require_method(selected, method)
    payload = _request("POST", f"/v1/connections/{selected.id}/oauth")
    try:
        exact_fields(
            payload,
            {"provider", "status", "authorize_url", "expires_in"},
            "OAuth response",
        )
        if payload["provider"] != selected.id or payload["status"] != "pending":
            raise ValueError("OAuth response has mismatched provider or status")
        authorize_url = nonblank(payload["authorize_url"], "OAuth authorize_url")
        expires_in = payload["expires_in"]
        if isinstance(expires_in, bool) or not isinstance(expires_in, int) or expires_in < 1:
            raise ValueError("OAuth expires_in must be a positive integer")
    except (TypeError, ValueError) as exc:
        raise EngineProtocolError(f"invalid OAuth response: {exc}") from exc
    return OAuthFlow(
        provider=selected.id,
        authorize_url=authorize_url,
        _engine_url=current_engine_url(),
        _provider_record=selected,
        _expires_at=time.monotonic() + expires_in,
    )


def disconnect(provider: str) -> Connection:
    """Remove one provider connection; already-disconnected providers are harmless."""

    selected = _provider(provider)
    _request("DELETE", f"/v1/connections/{selected.id}", expect_empty=True)
    return Connection(
        provider=selected.id,
        display_name=selected.display_name,
        auth_methods=selected.auth_methods,
        status="not_connected",
        auth_method=None,
        account_label=None,
    )


def _provider(provider: str) -> ProviderRecord:
    if not isinstance(provider, str) or not provider.strip():
        raise ValueError("provider must be a non-empty string")
    selected = next(
        (item for item in load_registry().providers if item.id == provider.strip()), None
    )
    if selected is None:
        raise UnknownProviderError(
            f"The configured engine does not advertise provider {provider!r}.",
            code="unknown_provider",
            provider=provider,
        )
    return selected


def _require_method(provider: ProviderRecord, method: str) -> None:
    if method not in provider.auth_methods:
        raise UnsupportedAuthMethodError(
            f"{provider.display_name} does not support {method!r} authentication.",
            code="auth_method_not_supported",
            provider=provider.id,
        )


def _get_connection(provider: ProviderRecord, *, engine_url: str | None = None) -> Connection:
    payload = _request("GET", f"/v1/connections/{provider.id}", engine_url=engine_url)
    return _decode_connection_response(payload, provider)


def _decode_connection_response(payload: dict[str, object], provider: ProviderRecord) -> Connection:
    try:
        return _decode_connection(payload, provider)
    except (TypeError, ValueError) as exc:
        raise EngineProtocolError(f"invalid connection response: {exc}") from exc


def _decode_connection(payload: dict[str, object], provider: ProviderRecord) -> Connection:
    exact_fields(
        payload,
        {"provider", "status", "auth_method", "account_label"},
        "connection record",
    )
    if payload["provider"] != provider.id:
        raise ValueError("connection provider does not match the request")
    status = nonblank(payload["status"], "connection status")
    if status not in _STATUSES:
        raise ValueError(f"unknown connection status {status!r}")
    auth_method = payload["auth_method"]
    if auth_method is not None and auth_method not in provider.auth_methods:
        raise ValueError("connection auth_method is not advertised")
    account_label = payload["account_label"]
    if account_label is not None:
        account_label = nonblank(account_label, "connection account_label")
    return Connection(
        provider=provider.id,
        display_name=provider.display_name,
        auth_methods=provider.auth_methods,
        status=cast(ConnectionStatus, status),
        auth_method=cast(AuthMethod | None, auth_method),
        account_label=cast(str | None, account_label),
    )


def _request(
    method: str,
    path: str,
    *,
    engine_url: str | None = None,
    json_body: dict[str, object] | None = None,
    expect_empty: bool = False,
) -> dict[str, object]:
    base_url = engine_url or current_engine_url()
    _require_private_origin(base_url)
    try:
        with httpx.Client(
            base_url=base_url,
            timeout=30.0,
            follow_redirects=False,
            transport=_transport,
        ) as client:
            response = client.request(method, path, json=json_body)
    except httpx.HTTPError as exc:
        raise EngineConnectionError(f"could not reach URL4 engine at {base_url}") from exc
    if response.is_redirect:
        raise EngineProtocolError("provider connection routes must not redirect")
    if not response.is_success:
        _raise_engine_error(response)
    if expect_empty:
        if response.status_code != 204 or response.content:
            raise EngineProtocolError("connection deletion must return an empty HTTP 204 response")
        return {}
    try:
        return unique_json_object(response.text)
    except (TypeError, ValueError) as exc:
        raise EngineProtocolError(f"invalid provider connection response: {exc}") from exc


def _raise_engine_error(response: httpx.Response) -> None:
    try:
        payload = unique_json_object(response.text)
        exact_fields(
            payload,
            {"schema", "code", "message", "provider", "retryable"},
            "connection error",
        )
        if payload["schema"] != ERROR_SCHEMA:
            raise ValueError("unexpected connection error schema")
        code = nonblank(payload["code"], "connection error code")
        message = nonblank(payload["message"], "connection error message")
        provider = payload["provider"]
        if provider is not None:
            provider = nonblank(provider, "connection error provider")
        retryable = payload["retryable"]
        if not isinstance(retryable, bool):
            raise TypeError("connection error retryable must be a boolean")
    except (TypeError, ValueError) as exc:
        raise EngineProtocolError(
            f"URL4 engine returned HTTP {response.status_code} with an invalid safe error"
        ) from exc
    error_type = _ERROR_TYPES.get(code, ProviderConnectionError)
    raise error_type(
        message,
        code=code,
        provider=cast(str | None, provider),
        retryable=retryable,
    )


def _require_private_origin(engine_url: str) -> None:
    parts = urlsplit(engine_url)
    if parts.scheme == "https":
        return
    if parts.scheme == "http" and parts.hostname in {"localhost", "127.0.0.1", "::1"}:
        return
    raise SecureTransportRequiredError(
        "Provider connection operations require HTTPS outside a loopback engine."
    )


__all__ = ["Connection", "OAuthFlow", "connect", "disconnect", "list"]
