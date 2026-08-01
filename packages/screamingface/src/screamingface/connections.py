"""Typed provider connections bound to an SF Engine Client."""

from __future__ import annotations

import builtins
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Literal, NoReturn, cast

import httpx

from screamingface.errors import EngineUnavailableError, ProviderConnectionError

type AuthMethod = Literal["api_key", "oauth"]
type ConnectionStatus = Literal[
    "not_connected",
    "pending",
    "connected",
    "needs_reauth",
    "error",
]

_PATH = "/v1/connections"
_METHODS = frozenset({"api_key", "oauth"})
_STATUSES = frozenset({"not_connected", "pending", "connected", "needs_reauth", "error"})
_FIELDS = frozenset(
    {
        "object",
        "provider",
        "display_name",
        "auth_methods",
        "status",
        "auth_method",
        "account_label",
    }
)


@dataclass(frozen=True, slots=True)
class Connection:
    """Sanitized provider state advertised by the configured SF Engine."""

    provider: str
    display_name: str
    auth_methods: tuple[AuthMethod, ...]
    status: ConnectionStatus
    auth_method: AuthMethod | None
    account_label: str | None

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.display_name.strip():
            raise ValueError("connection provider and display_name must be non-empty")
        if not self.auth_methods or any(method not in _METHODS for method in self.auth_methods):
            raise ValueError("connection auth_methods contain an unsupported method")
        if self.status not in _STATUSES:
            raise ValueError(f"unknown connection status {self.status!r}")
        if self.auth_method is not None and self.auth_method not in self.auth_methods:
            raise ValueError("connection auth_method is not advertised by its provider")
        if self.account_label is not None and not self.account_label.strip():
            raise ValueError("connection account_label must be non-empty or None")


class Connections:
    """Synchronous provider catalogue bound to one Client."""

    def __init__(
        self,
        request: Callable[..., httpx.Response],
        engine_url: str,
    ) -> None:
        self._request = request
        self._engine_url = engine_url

    def list(self) -> tuple[Connection, ...]:
        return _decode_list(_sync(self._request, self._engine_url, "GET", _PATH))

    def get(self, provider: str) -> Connection:
        selected = _provider(provider)
        return _find(self.list(), selected)

    def connect(self, provider: str, api_key: str) -> Connection:
        selected = _provider(provider)
        secret = _api_key(api_key)
        return _decode_one(
            _sync(
                self._request,
                self._engine_url,
                "PUT",
                f"{_PATH}/{selected}",
                json={"api_key": secret},
            ),
            selected,
        )

    def disconnect(self, provider: str) -> Connection:
        selected = _provider(provider)
        return _decode_one(
            _sync(self._request, self._engine_url, "DELETE", f"{_PATH}/{selected}"),
            selected,
        )


class AsyncConnections:
    """Asynchronous provider catalogue bound to one AsyncClient."""

    def __init__(
        self,
        request: Callable[..., Awaitable[httpx.Response]],
        engine_url: str,
    ) -> None:
        self._request = request
        self._engine_url = engine_url

    async def list(self) -> tuple[Connection, ...]:
        return _decode_list(await _async(self._request, self._engine_url, "GET", _PATH))

    async def get(self, provider: str) -> Connection:
        selected = _provider(provider)
        return _find(await self.list(), selected)

    async def connect(self, provider: str, api_key: str) -> Connection:
        selected = _provider(provider)
        secret = _api_key(api_key)
        return _decode_one(
            await _async(
                self._request,
                self._engine_url,
                "PUT",
                f"{_PATH}/{selected}",
                json={"api_key": secret},
            ),
            selected,
        )

    async def disconnect(self, provider: str) -> Connection:
        selected = _provider(provider)
        return _decode_one(
            await _async(
                self._request,
                self._engine_url,
                "DELETE",
                f"{_PATH}/{selected}",
            ),
            selected,
        )


def list() -> tuple[Connection, ...]:
    """List connections through the lazy default Client."""

    from screamingface._default_client import default_client

    return default_client().connections.list()


def get(provider: str) -> Connection:
    """Get one connection through the lazy default Client."""

    from screamingface._default_client import default_client

    return default_client().connections.get(provider)


def _sync(
    request: Callable[..., httpx.Response],
    engine_url: str,
    method: str,
    path: str,
    *,
    json: dict[str, str] | None = None,
) -> object:
    try:
        response = request(method, path, json=json)
    except httpx.HTTPError as exc:
        raise EngineUnavailableError(
            "Could not reach the SF Engine provider connections",
            engine_url=engine_url,
        ) from exc
    return _response(response)


async def _async(
    request: Callable[..., Awaitable[httpx.Response]],
    engine_url: str,
    method: str,
    path: str,
    *,
    json: dict[str, str] | None = None,
) -> object:
    try:
        response = await request(method, path, json=json)
    except httpx.HTTPError as exc:
        raise EngineUnavailableError(
            "Could not reach the SF Engine provider connections",
            engine_url=engine_url,
        ) from exc
    return _response(response)


def _response(response: httpx.Response) -> object:
    if not response.is_success:
        status = response.status_code
        if status in {401, 403}:
            raise ProviderConnectionError(
                "Provider connection was rejected",
                code="connection_rejected",
                status=status,
                permanent=True,
            )
        if status == 404:
            raise ProviderConnectionError(
                "The provider is not available on this SF Engine",
                code="unknown_provider",
                status=status,
                permanent=True,
            )
        if status == 409:
            raise ProviderConnectionError(
                "The provider connection is ambiguous in AI Gateway",
                code="connection_conflict",
                status=status,
                permanent=True,
            )
        if status == 429:
            raise ProviderConnectionError(
                "Provider connection requests are temporarily rate limited",
                code="connection_rate_limited",
                status=status,
                permanent=False,
            )
        raise ProviderConnectionError(
            f"SF Engine provider connection failed with HTTP {status}",
            code="connection_engine_error",
            status=status,
            permanent=status < 500,
        )
    try:
        return response.json()
    except ValueError as exc:
        _invalid("provider connection response must be JSON", cause=exc)


def _decode_list(payload: object) -> tuple[Connection, ...]:
    root = _mapping(payload, "provider connection catalogue")
    if set(root) != {"object", "data"} or root.get("object") != "list":
        _invalid("provider connection catalogue must be an object list")
    rows = root.get("data")
    if not isinstance(rows, builtins.list):
        _invalid("provider connection catalogue must contain a data array")
    values = tuple(_decode(row) for row in rows)
    providers = [value.provider for value in values]
    if len(providers) != len(set(providers)):
        _invalid("provider connection catalogue contains duplicate providers")
    return values


def _decode_one(payload: object, provider: str) -> Connection:
    value = _decode(payload)
    if value.provider != provider:
        _invalid("provider connection response does not match the request")
    return value


def _decode(payload: object) -> Connection:
    row = _mapping(payload, "provider connection")
    if set(row) != _FIELDS or row.get("object") != "connection":
        _invalid("provider connection has unsupported fields")
    auth_methods = row.get("auth_methods")
    if not isinstance(auth_methods, builtins.list) or not auth_methods:
        _invalid("provider connection auth_methods must be a non-empty array")
    try:
        return Connection(
            provider=_text(row.get("provider"), "provider"),
            display_name=_text(row.get("display_name"), "display_name"),
            auth_methods=cast(tuple[AuthMethod, ...], tuple(auth_methods)),
            status=cast(ConnectionStatus, _text(row.get("status"), "status")),
            auth_method=cast(AuthMethod | None, _optional_text(row.get("auth_method"))),
            account_label=_optional_text(row.get("account_label")),
        )
    except (TypeError, ValueError) as exc:
        _invalid(str(exc), cause=exc)


def _find(values: tuple[Connection, ...], provider: str) -> Connection:
    selected = next((value for value in values if value.provider == provider), None)
    if selected is None:
        raise ProviderConnectionError(
            f"The configured SF Engine does not advertise provider {provider!r}",
            provider=provider,
            code="unknown_provider",
            permanent=True,
        )
    return selected


def _provider(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("provider must be a non-empty string")
    return value.strip()


def _api_key(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("api_key must be a non-empty string")
    return value


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        _invalid(f"{label} must be an object")
    return cast(Mapping[str, object], value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _invalid(f"provider connection {label} must be non-empty text")
    return value.strip()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return _text(value, "optional value")


def _invalid(message: str, *, cause: Exception | None = None) -> NoReturn:
    error = ProviderConnectionError(
        message,
        code="invalid_connection_response",
        permanent=True,
    )
    if cause is None:
        raise error
    raise error from cause


__all__ = ["Connection", "ConnectionStatus", "get", "list"]
