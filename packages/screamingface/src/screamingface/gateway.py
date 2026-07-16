"""Narrow HTTP client for the published AI Gateway contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

import httpx

from screamingface.errors import GatewayError, ProviderCallError

# Temporary compatibility map for the provider plugins currently shipped by AI
# Gateway. Remove this once the gateway publishes provider capabilities through
# its HTTP API; model IDs and counts still come from GET /v1/models.
_TEMPORARY_PROVIDER_AUTH_METHODS: dict[str, tuple[str, ...]] = {
    "anthropic": ("api_key", "oauth"),
    "antigravity": ("oauth",),
    "codex": ("oauth",),
    "gemini-cli": ("api_key", "oauth"),
    "huggingface": ("api_key",),
    "ollama": ("none",),
}


@dataclass(frozen=True)
class GatewayLogin:
    token: str
    expires_at: datetime
    username: str

    def __repr__(self) -> str:
        return (
            f"GatewayLogin(username={self.username!r}, expires_at={self.expires_at!r}, "
            "token=<redacted>)"
        )


@dataclass(frozen=True)
class Completion:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True)
class Connection:
    id: str
    provider: str
    label: str
    status: str
    auth_type: str = "oauth"


@dataclass(frozen=True)
class ProviderCapability:
    id: str
    auth_methods: tuple[str, ...]
    model_count: int


@dataclass(frozen=True)
class OAuthStart:
    connection_id: str
    authorize_url: str
    expires_in: int


class GatewayPort(Protocol):
    async def list_models(self) -> list[str]: ...

    async def list_providers(self) -> list[ProviderCapability]: ...

    async def list_connections(self) -> list[Connection]: ...

    async def get_connection(self, connection_id: str) -> Connection: ...

    async def create_api_key_connection(
        self, provider: str, label: str | None, api_key: str
    ) -> Connection: ...

    async def replace_api_key_connection(self, connection_id: str, api_key: str) -> Connection: ...

    async def delete_connection(self, connection_id: str) -> None: ...

    async def aclose(self) -> None: ...

    async def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        profile: str = "default",
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> Completion: ...


class OAuthGatewayPort(Protocol):
    async def start_oauth_connection(
        self, provider: str, label: str | None = None, redirect_uri: str | None = None
    ) -> OAuthStart: ...


class AIGatewayClient:
    """Async, secret-safe client for the endpoints consumed by the SDK."""

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._token = token
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            transport=transport,
        )

    def __repr__(self) -> str:
        state = "set" if self._token else "unset"
        return f"AIGatewayClient(base_url={self.base_url!r}, token=<{state}>)"

    async def aclose(self) -> None:
        await self._client.aclose()

    async def health(self) -> bool:
        try:
            response = await self._client.get("/healthz", timeout=1.0)
        except httpx.HTTPError:
            return False
        return response.status_code == 200 and response.json().get("status") == "ok"

    async def login(self, username: str, password: str) -> GatewayLogin:
        response = await self._client.post(
            "/v1/auth/login",
            json={"username": username, "password": password},
        )
        payload = _json_or_error(response, "gateway login")
        self._token = _required_str(payload, "token")
        account = payload.get("account")
        if not isinstance(account, dict):
            raise GatewayError("gateway login response is missing account")
        return GatewayLogin(
            token=self._token,
            expires_at=_parse_datetime(_required_str(payload, "expires_at")),
            username=_required_str(account, "username"),
        )

    async def me(self) -> dict[str, Any]:
        response = await self._client.get("/v1/auth/me", headers=self._auth_headers())
        return _json_or_error(response, "gateway session")

    async def list_models(self) -> list[str]:
        rows = await self._model_rows()
        return [model_id for row in rows if (model_id := _model_id(row)) is not None]

    async def list_providers(self) -> list[ProviderCapability]:
        rows = await self._model_rows()
        providers: dict[str, tuple[set[str], int]] = {}
        for row in rows:
            provider = row.get("owned_by")
            if not isinstance(provider, str):
                continue
            methods, count = providers.setdefault(provider, (set(), 0))
            raw_methods = row.get("auth_methods")
            if isinstance(raw_methods, list):
                methods.update(method for method in raw_methods if isinstance(method, str))
            providers[provider] = (methods, count + 1)
        return [
            ProviderCapability(
                provider,
                tuple(sorted(methods)) or _TEMPORARY_PROVIDER_AUTH_METHODS.get(provider, ()),
                count,
            )
            for provider, (methods, count) in providers.items()
        ]

    async def _model_rows(self) -> list[dict[str, Any]]:
        response = await self._client.get("/v1/models", headers=self._auth_headers())
        payload = _json_or_error(response, "model listing")
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise GatewayError("model listing response is missing data")
        return [row for row in rows if isinstance(row, dict)]

    async def list_connections(self) -> list[Connection]:
        response = await self._client.get(
            "/v1/oauth/connections",
            headers=self._auth_headers(),
        )
        payload = _json_or_error(response, "provider connection listing")
        rows = payload.get("connections")
        if not isinstance(rows, list):
            raise GatewayError("provider connection response is missing connections")
        return [_connection(row) for row in rows if isinstance(row, dict)]

    async def get_connection(self, connection_id: str) -> Connection:
        response = await self._client.get(
            f"/v1/oauth/connections/{connection_id}", headers=self._auth_headers()
        )
        return _connection(_json_or_error(response, "provider connection status"))

    async def start_oauth_connection(
        self,
        provider: str,
        label: str | None = None,
        redirect_uri: str | None = None,
    ) -> OAuthStart:
        body = {"provider": provider}
        if label is not None:
            body["label"] = label
        if redirect_uri is not None:
            body["redirect_uri"] = redirect_uri
        response = await self._client.post(
            "/v1/oauth/connections", headers=self._auth_headers(), json=body
        )
        payload = _json_or_error(response, "starting provider OAuth")
        return OAuthStart(
            connection_id=_required_str(payload, "connection_id"),
            authorize_url=_required_str(payload, "authorize_url"),
            expires_in=_int_or_zero(payload.get("expires_in")),
        )

    async def create_api_key_connection(
        self, provider: str, label: str | None, api_key: str
    ) -> Connection:
        body = {"provider": provider, "api_key": api_key}
        if label is not None:
            body["label"] = label
        response = await self._client.post(
            "/v1/oauth/connections/api-key", headers=self._auth_headers(), json=body
        )
        return _connection(_json_or_error(response, "creating provider API-key connection"))

    async def replace_api_key_connection(self, connection_id: str, api_key: str) -> Connection:
        response = await self._client.put(
            f"/v1/oauth/connections/{connection_id}/api-key",
            headers=self._auth_headers(),
            json={"api_key": api_key},
        )
        return _connection(_json_or_error(response, "replacing provider API key"))

    async def delete_connection(self, connection_id: str) -> None:
        response = await self._client.delete(
            f"/v1/oauth/connections/{connection_id}", headers=self._auth_headers()
        )
        if response.is_error:
            raise GatewayError(
                f"deleting provider connection failed with HTTP {response.status_code}"
            )

    async def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        profile: str = "default",
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> Completion:
        headers = {**self._auth_headers(), "X-Profile": profile}
        try:
            response = await self._client.post(
                "/v1/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
            )
        except httpx.TimeoutException as exc:
            raise ProviderCallError(model, "timeout", "Provider call timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderCallError(model, "network_error", "Provider call failed") from exc
        if response.is_error:
            raise _provider_error(response, model)
        payload = _json_or_error(response, "chat completion")
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderCallError(model, "invalid_response", "Provider response has no choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise ProviderCallError(
                model, "invalid_response", "Provider response has no message content"
            )
        raw_usage = payload.get("usage")
        usage: dict[str, Any] = raw_usage if isinstance(raw_usage, dict) else {}
        return Completion(
            text=message["content"],
            prompt_tokens=_int_or_zero(usage.get("prompt_tokens")),
            completion_tokens=_int_or_zero(usage.get("completion_tokens")),
            total_tokens=_int_or_zero(usage.get("total_tokens")),
        )

    def _auth_headers(self) -> dict[str, str]:
        if not self._token:
            raise GatewayError("AI Gateway authentication is required")
        return {"Authorization": f"Bearer {self._token}"}


def _json_or_error(response: httpx.Response, operation: str) -> dict[str, Any]:
    if response.is_error:
        # INVARIANT: never include raw response bodies; validation errors may originate
        # from secret-bearing requests even though AI Gateway also redacts them.
        raise GatewayError(f"{operation} failed with HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise GatewayError(f"{operation} returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise GatewayError(f"{operation} returned an invalid response")
    return payload


def _required_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise GatewayError(f"gateway response is missing {key}")
    return value


def _parse_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GatewayError("gateway response contains an invalid timestamp") from exc


def _int_or_zero(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _model_id(row: object) -> str | None:
    result = None
    if isinstance(row, dict):
        model_id = row.get("id")
        owner = row.get("owned_by")
        if isinstance(model_id, str) and model_id:
            result = model_id
            if "/" not in model_id and isinstance(owner, str) and owner:
                result = f"{owner}/{model_id}"
    return result


def _connection(payload: dict[str, Any]) -> Connection:
    return Connection(
        id=_required_str(payload, "id"),
        provider=_required_str(payload, "provider"),
        label=_required_str(payload, "label"),
        status=_required_str(payload, "status"),
        auth_type=str(payload.get("auth_type") or "oauth"),
    )


def _provider_error(response: httpx.Response, model: str) -> ProviderCallError:
    code = "provider_error"
    message = f"Provider call failed with HTTP {response.status_code}"
    try:
        payload = response.json()
    except ValueError:
        return ProviderCallError(model, code, message)
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, dict):
        raw_code = detail.get("code")
        raw_message = detail.get("message")
        if isinstance(raw_code, str) and raw_code:
            code = raw_code
        if isinstance(raw_message, str) and raw_message:
            message = raw_message
    return ProviderCallError(model, code, message)
