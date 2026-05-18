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

logger = logging.getLogger(__name__)


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

    async def health(self, model: str | None = None) -> HealthStatus:  # noqa: ARG002
        url = (
            f"{self._gateway_url}/v1/auth/{self._gateway_provider}"
            f"/profiles/{self._profile_name}/status"
        )
        try:
            async with self._http_factory(10.0) as client:
                resp = await client.get(url)
        except httpx.RequestError as exc:
            return HealthStatus(authenticated=False, error=f"AI Gateway unreachable: {exc}")

        if resp.status_code == 404:
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

        url = f"{self._gateway_url}/v1/chat/completions"
        headers = {"X-Profile": self._profile_name, "content-type": "application/json"}

        try:
            async with self._http_factory(timeout_seconds) as client:
                resp = await client.post(url, json=body, headers=headers)
        except httpx.RequestError as exc:
            raise BackendError(
                f"AI Gateway unreachable at {self._gateway_url}: {exc}",
                status=None,
            ) from exc

        if resp.status_code == 200:
            return _response_to_core_message(resp.json())

        # Map gateway error codes onto SF's error hierarchy.
        detail = _detail_or_text(resp)
        code = (detail or {}).get("code") if isinstance(detail, dict) else None

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
        if resp.status_code == 401 and code == "auth_required":
            msg = (
                detail.get("message", "auth required")
                if isinstance(detail, dict)
                else "auth required"
            )
            raise AuthError(f"Gateway: {msg}")
        if resp.status_code in (400, 422):
            raise BackendError(
                f"Gateway rejected request ({resp.status_code}): {detail}",
                status=resp.status_code,
            )
        # Anything else → unexpected gateway error
        retry_after = _parse_retry_after(resp.headers.get("retry-after"))
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


def _parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None
