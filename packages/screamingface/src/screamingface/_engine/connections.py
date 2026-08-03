"""SF Engine provider-connection adapters and strict wire decoding."""

from __future__ import annotations

import builtins
from collections.abc import Awaitable, Callable
from typing import NoReturn, cast

import httpx

from screamingface._core.wire import mapping as _wire_mapping
from screamingface._core.wire import text as _wire_text
from screamingface.connections import AuthMethod, Connection, ConnectionStatus
from screamingface.errors import EngineUnavailableError, ProviderConnectionError

_PATH = "/v1/connections"
_ENGINE_FAILURES: dict[int, tuple[str, str, bool]] = {
    401: ("Provider connection was rejected", "connection_rejected", True),
    403: ("Provider connection was rejected", "connection_rejected", True),
    404: ("The provider is not available on this SF Engine", "unknown_provider", True),
    409: (
        "The provider connection is ambiguous in AI Gateway",
        "connection_conflict",
        True,
    ),
    429: (
        "Provider connection requests are temporarily rate limited",
        "connection_rate_limited",
        False,
    ),
    502: (
        "AI Gateway returned an unusable response",
        "connection_gateway_bad_response",
        False,
    ),
    503: ("AI Gateway is unavailable", "connection_gateway_unavailable", False),
    504: ("AI Gateway did not respond in time", "connection_gateway_timeout", False),
}
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
        _raise_engine_failure(response.status_code)
    try:
        return response.json()
    except ValueError as exc:
        _invalid("provider connection response must be JSON", cause=exc)


def _raise_engine_failure(status: int) -> NoReturn:
    known = _ENGINE_FAILURES.get(status)
    if known is None:
        message = f"SF Engine provider connection failed with HTTP {status}"
        code = "connection_engine_error"
        permanent = status < 500
    else:
        message, code, permanent = known
    raise ProviderConnectionError(
        message,
        code=code,
        status=status,
        permanent=permanent,
    )


def _decode_list(payload: object) -> tuple[Connection, ...]:
    root = _wire_mapping(payload, "provider connection catalogue", _invalid)
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
    row = _wire_mapping(payload, "provider connection", _invalid)
    if set(row) != _FIELDS or row.get("object") != "connection":
        _invalid("provider connection has unsupported fields")
    auth_methods = row.get("auth_methods")
    if not isinstance(auth_methods, builtins.list) or not auth_methods:
        _invalid("provider connection auth_methods must be a non-empty array")
    try:
        return Connection(
            provider=_wire_text(row.get("provider"), "provider connection provider", _invalid),
            display_name=_wire_text(
                row.get("display_name"), "provider connection display_name", _invalid
            ),
            auth_methods=cast(tuple[AuthMethod, ...], tuple(auth_methods)),
            status=cast(
                ConnectionStatus,
                _wire_text(row.get("status"), "provider connection status", _invalid),
            ),
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


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return _wire_text(value, "provider connection optional value", _invalid)


def _invalid(message: str, *, cause: Exception | None = None) -> NoReturn:
    error = ProviderConnectionError(
        message,
        code="invalid_connection_response",
        permanent=True,
    )
    if cause is None:
        raise error
    raise error from cause


__all__: list[str] = []
