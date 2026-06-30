"""HTTP client to the AI Gateway.

Translates a list of CoreMessage (the SF-internal canonical shape) into
an OpenAI ChatCompletions request, POSTs to the gateway with X-Profile,
and parses the response back into a CoreMessage.

Gateway-side errors map onto the existing SF error types so callers can
catch them uniformly (BackendError for transport / unexpected status,
AuthError for auth-required / refresh-failed, CredentialNotFoundError
for missing-profile-tokens).
"""

from __future__ import annotations

import logging

import httpx

from screamingface.plugins.llm_base.backend_base import Backend, HealthStatus
from screamingface.plugins.llm_base.errors import (
    AuthError,
    BackendError,
    CredentialNotFoundError,
)
from screamingface.plugins.llm_base.messages import CoreMessage, TextPart, ToolDefinition

from .client import AigwGatewayAuthRequired, AigwGatewayClient, AigwGatewayClientError
from .config import resolve_aigw_runtime_config

logger = logging.getLogger(__name__)

AIGW_ACCOUNT_ACTIVATION_REQUIRED_CODE = "account_activation_required"


class AigwGatewayError(BackendError):
    """Raised for unexpected gateway responses (gateway 500, malformed JSON)."""


class AigwBackend(Backend):
    """Speaks OpenAI ChatCompletions to the local AI Gateway.

    One method: `run(messages, *, model, system, ...) -> CoreMessage`.
    The gateway handles auth, refresh, and provider-specific shape
    translation; this class just speaks the gateway's protocol.

    Args:
        gateway_url: Base URL (default http://127.0.0.1:9105).
        profile_name: X-Profile header value (default "default").
        http_client_factory: Callable returning an httpx.AsyncClient. Tests
            inject one that returns a MockTransport-backed client.
    """

    def __init__(
        self,
        *,
        gateway_url: str = "http://127.0.0.1:9105",
        profile_name: str = "default",
        gateway_provider: str,
        http_client_factory=None,
        app=None,
    ) -> None:
        if not gateway_provider:
            msg = "gateway_provider is required for gateway-backed backends"
            raise ValueError(msg)
        self._gateway_url = gateway_url.rstrip("/")
        self._profile_name = profile_name
        self._gateway_provider = gateway_provider
        self._http_factory = http_client_factory or (
            lambda timeout: httpx.AsyncClient(timeout=httpx.Timeout(timeout))
        )
        self._app = app

    async def health(self, model: str | None = None) -> HealthStatus:  # noqa: ARG002
        try:
            resp = await self._request(
                "GET",
                f"/v1/auth/{self._gateway_provider}/profiles/{self._profile_name}/status",
                timeout_seconds=10.0,
            )
        except AigwGatewayAuthRequired:
            return HealthStatus(authenticated=False, error="AIGateway login required")
        except AigwGatewayClientError as exc:
            return HealthStatus(authenticated=False, error=str(exc.detail))
        except httpx.RequestError as exc:
            base = _runtime_gateway_url(self._app, self._gateway_url)
            return HealthStatus(
                authenticated=False, error=f"AI Gateway unreachable at {base}: {exc}"
            )

        if resp.status_code == 404:
            connection_status = await self._health_from_oauth_connections()
            if connection_status is not None:
                return connection_status
            return HealthStatus(authenticated=False, error="Profile not yet created at gateway")
        if resp.status_code >= 500:
            return HealthStatus(
                authenticated=False,
                error=f"Gateway error (HTTP {resp.status_code})",
            )
        if resp.status_code >= 400:
            return HealthStatus(authenticated=False, error=f"Gateway HTTP {resp.status_code}")
        body = resp.json() if resp.content else {}
        state = (body.get("state") or "").lower()
        if state == "authenticated":
            return HealthStatus(authenticated=True)
        if state == "pending":
            return HealthStatus(authenticated=False, error="OAuth in progress")
        if state == "error":
            return HealthStatus(authenticated=False, error="Profile in error state")
        return HealthStatus(authenticated=False, error=f"Unknown profile state: {state!r}")

    async def _health_from_oauth_connections(self) -> HealthStatus | None:
        try:
            resp = await self._request(
                "GET",
                f"/v1/oauth/connections?provider={self._gateway_provider}&status=active",
                timeout_seconds=10.0,
            )
        except AigwGatewayAuthRequired:
            return HealthStatus(authenticated=False, error="AIGateway login required")
        except AigwGatewayClientError as exc:
            return HealthStatus(authenticated=False, error=str(exc.detail))
        except httpx.RequestError as exc:
            base = _runtime_gateway_url(self._app, self._gateway_url)
            return HealthStatus(
                authenticated=False, error=f"AI Gateway unreachable at {base}: {exc}"
            )

        if resp.status_code == 404:
            return None
        if resp.status_code >= 500:
            return HealthStatus(
                authenticated=False,
                error=f"Gateway error (HTTP {resp.status_code})",
            )
        if resp.status_code >= 400:
            return HealthStatus(authenticated=False, error=f"Gateway HTTP {resp.status_code}")

        connections = _active_connections(resp)
        if not connections:
            return None
        if _matching_connection(connections, self._profile_name) is not None:
            return HealthStatus(authenticated=True)
        if self._profile_name == "default" and len(connections) == 1:
            return HealthStatus(authenticated=True)
        if self._profile_name == "default":
            return HealthStatus(
                authenticated=False,
                error=(
                    "Multiple active OAuth connections exist; select one with the "
                    "backend auth_profile setting"
                ),
            )
        return HealthStatus(
            authenticated=False,
            error=f"No active OAuth connection named {self._profile_name!r}",
        )

    async def run(
        self,
        messages: list[CoreMessage],
        *,
        model: str,
        system: str | None = None,
        tools: list[ToolDefinition] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        timeout_seconds: float = 300.0,
        extra_body: dict | None = None,
    ) -> CoreMessage:
        body = self._build_body(
            messages,
            model=model,
            system=system,
            tools=tools,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if extra_body:
            body.update(extra_body)

        headers = {"X-Profile": self._profile_name, "content-type": "application/json"}

        try:
            resp = await self._request(
                "POST",
                "/v1/chat/completions",
                json=body,
                headers=headers,
                timeout_seconds=timeout_seconds,
            )
        except AigwGatewayAuthRequired as exc:
            raise AuthError("Gateway: AIGateway login required") from exc
        except AigwGatewayClientError as exc:
            raise BackendError(str(exc.detail), status=exc.status_code) from exc
        except httpx.RequestError as exc:
            base = _runtime_gateway_url(self._app, self._gateway_url)
            raise BackendError(
                f"AI Gateway unreachable at {base}: {exc}",
                status=None,
            ) from exc

        if resp.status_code == 200:
            return _response_to_core_message(resp.json())

        # Map gateway error codes onto SF's error hierarchy.
        detail = _detail_or_text(resp)
        code = (detail or {}).get("code") if isinstance(detail, dict) else None
        retry_after = _parse_retry_after(resp.headers.get("retry-after"))

        if resp.status_code == 404 and code == "profile_not_found":
            raise CredentialNotFoundError(
                f"Gateway profile {self._profile_name!r} not found. "
                f"Create it via POST /v1/auth/<provider>/profiles."
            )
        if resp.status_code == 409 and code == "profile_pending_auth":
            raise AuthError(
                f"Gateway profile {self._profile_name!r} is awaiting OAuth callback. "
                f"Complete the flow in Electron."
            )
        if resp.status_code in (401, 403) and code in {
            "auth_required",
            AIGW_ACCOUNT_ACTIVATION_REQUIRED_CODE,
        }:
            msg = _detail_message(detail, "auth required")
            raise AuthError(f"Gateway: {msg}")
        if resp.status_code in (400, 422):
            raise BackendError(
                f"Gateway rejected request ({resp.status_code}): {detail}",
                status=resp.status_code,
            )
        if code == "provider_unavailable":
            raise BackendError(
                f"Gateway provider unavailable: {_detail_message(detail, 'provider unavailable')}",
                status=resp.status_code,
                retry_after=retry_after,
            )
        if code == "provider_error":
            # A bare gateway provider_error with HTTP 403 remains provider-level
            # until gateway emitters explicitly classify generic 403s as auth.
            raise BackendError(
                f"Gateway provider error: {_detail_message(detail, 'provider error')}",
                status=resp.status_code,
                retry_after=retry_after,
            )
        if resp.status_code == 429 and code == "rate_limited":
            raise BackendError(
                f"Gateway rate limited: {_detail_message(detail, 'rate limited')}",
                status=resp.status_code,
                retry_after=retry_after,
            )
        # Anything else → unexpected gateway error
        raise AigwGatewayError(
            f"Gateway returned status {resp.status_code}: {resp.text[:500]}",
            status=resp.status_code,
            retry_after=retry_after,
        )

    def _build_body(
        self,
        messages: list[CoreMessage],
        *,
        model: str,
        system: str | None,
        tools: list[ToolDefinition] | None,
        max_tokens: int | None,
        temperature: float | None,
    ) -> dict:
        openai_messages: list[dict] = []
        if system:
            openai_messages.append({"role": "system", "content": system})
        for m in messages:
            openai_messages.append(_core_message_to_openai(m))

        body: dict = {"model": model, "messages": openai_messages}
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if temperature is not None:
            body["temperature"] = temperature
        if tools:
            body["tools"] = [_tool_to_openai(t) for t in tools]
        return body

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        headers: dict[str, str] | None = None,
        timeout_seconds: float,
    ) -> httpx.Response:
        from screamingface.plugins.llm_base._tracing import (
            record_llm_call,
            set_provider_attrs,
            traced_provider_post,
        )

        url = f"{self._gateway_url}{path}"
        # Open the span first, then inject W3C trace context into the outbound
        # headers so a locally-instrumented gateway can link into this trace.
        # (Remote gateways simply ignore the header — see plan follow-up.)
        with traced_provider_post("aigw", url, method=method):
            headers = dict(headers or {})
            try:
                from opentelemetry.propagate import inject

                inject(headers)
            except ImportError:
                pass

            if self._app is not None:
                resp = await AigwGatewayClient(
                    self._app,
                    http_client_factory=self._http_factory,
                ).request(
                    method,
                    path,
                    json=json,
                    headers=headers,
                    timeout_seconds=timeout_seconds,
                )
            else:
                async with self._http_factory(timeout_seconds) as client:
                    resp = await client.request(method, url, json=json, headers=headers)

            set_provider_attrs(
                {
                    "http.status_code": resp.status_code,
                    "aigw.profile": self._profile_name,
                    "aigw.provider": self._gateway_provider,
                }
            )
            # Only the chat-completions call is an LLM call; auth/status GETs are not.
            if path == "/v1/chat/completions":
                record_llm_call(self._gateway_provider, json, resp)
            return resp


def _core_message_to_openai(msg: CoreMessage) -> dict:
    if isinstance(msg.content, str):
        return {"role": msg.role, "content": msg.content}
    # Concatenate every TextPart; ignore non-text parts for now (Phase 1).
    text = "".join(p.text for p in msg.content if isinstance(p, TextPart))
    return {"role": msg.role, "content": text}


def _tool_to_openai(t: ToolDefinition) -> dict:
    return {
        "type": "function",
        "function": {
            "name": t.name,
            "description": t.description,
            "parameters": t.input_schema,
        },
    }


def _response_to_core_message(data: dict) -> CoreMessage:
    """Pull the assistant text out of an OpenAI ChatCompletions response."""
    try:
        choice = data["choices"][0]
        msg = choice["message"]
        content = msg.get("content") or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise AigwGatewayError(
            f"Malformed gateway response: {exc}; body={data!r}",
            status=200,
        ) from exc
    return CoreMessage(role="assistant", content=[TextPart(text=content)])


def _detail_or_text(resp: httpx.Response):
    try:
        body = resp.json()
    except (ValueError, httpx.DecodingError):
        return resp.text
    return body.get("detail", body) if isinstance(body, dict) else body


def _detail_message(detail, fallback: str) -> str:
    if isinstance(detail, dict):
        message = detail.get("message")
        return message if isinstance(message, str) and message else fallback
    return str(detail or fallback)


def _parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _active_connections(resp: httpx.Response) -> list[dict]:
    try:
        body = resp.json() if resp.content else {}
    except (ValueError, httpx.DecodingError):
        return []
    raw = body.get("connections") if isinstance(body, dict) else None
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict) and item.get("status") == "active"]


def _matching_connection(connections: list[dict], profile_name: str) -> dict | None:
    for connection in connections:
        if connection.get("label") == profile_name:
            return connection
    return None


def _runtime_gateway_url(app, fallback: str) -> str:
    if app is None:
        return fallback
    return resolve_aigw_runtime_config(app).gateway_url
