"""Backend ABC — the runtime for a specific provider.

A concrete :class:`Backend` is the top-level entry point for one
provider (Anthropic, OpenAI, Gemini, etc.). It combines:

- an :class:`AuthStrategy` that knows how to get auth headers
- an :class:`Adapter` that knows the wire format
- an httpx client (or equivalent transport)

The :meth:`run` method is the public API. It takes a CoreMessage list
plus the usual knobs (model, system, tools, …), handles everything
needed to fulfill the request (auth → translate → POST → parse), and
returns a single :class:`CoreMessage` (the assistant's reply).

Backends are **per-request stateless**. A single instance is safe to
share across many concurrent ``run()`` calls — the auth strategy holds
its own lock for refresh concurrency.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from screamingface.plugins.llm_base.errors import AuthError, BackendError
from screamingface.plugins.llm_base.messages import CoreMessage, ToolDefinition

if TYPE_CHECKING:
    import httpx

    from screamingface.plugins.llm_base.auth_base import AuthStrategy

logger = logging.getLogger(__name__)


@dataclass
class HealthStatus:
    """Result of a backend health check."""

    authenticated: bool
    error: str | None = None
    tokens_remaining: int | None = None
    requests_remaining: int | None = None
    rate_limit: dict[str, str | int | float] = field(default_factory=dict)


class Backend(ABC):
    """Abstract contract for a provider backend."""

    async def health(self) -> HealthStatus:
        return HealthStatus(authenticated=False, error="health() not implemented")

    @abstractmethod
    async def run(
        self,
        messages: list[CoreMessage],
        *,
        model: str,
        system: str | None = None,
        tools: list[ToolDefinition] | None = None,
        max_tokens: int = 16000,
        temperature: float | None = None,
        timeout_seconds: float = 300.0,
    ) -> CoreMessage:
        """Execute one round-trip against the provider.

        Raises:
            AuthError: Auth path broke and the user must re-auth.
            BackendError: Provider returned a non-success status or
                the network failed.
            AdapterError: Request or response couldn't be adapted
                to/from our canonical shape.
        """


async def post_with_default_retry(
    *,
    auth: AuthStrategy,
    http_factory,
    url: str,
    body: dict,
    provider_name: str,
    auth_login_cmd: str,
) -> dict:
    """Shared POST helper with the canonical ``401 → invalidate → retry`` recipe.

    This is the three-step dance every *_backend_api plugin had copied:

    1. Build auth headers, POST the body.
    2. On 401, invalidate the auth cache and retry exactly once. A
       second 401 means the credential itself is bad — raise
       :class:`AuthError` pointing at ``auth_login_cmd``.
    3. On 200 return the parsed JSON body; otherwise translate status
       codes to :class:`BackendError` / :class:`AuthError`.

    Providers with non-standard retry behavior (e.g. Gemini's 429
    self-recovery loop) should not use this — they override with their
    own method.

    Args:
        auth: Strategy for building the Authorization header.
        http_factory: No-arg callable returning an ``httpx.AsyncClient``
            (typically :func:`llm_base.http.default_http_factory`).
        url: The endpoint to POST to.
        body: The request body (serialized as JSON).
        provider_name: Human name of the provider for error messages
            ("Anthropic", "OpenAI", …).
        auth_login_cmd: The CLI command the user should run to
            re-authenticate when the credential is bad
            (e.g. ``"claude auth login"``).
    """
    import httpx

    async def _do_post(headers: dict[str, str]) -> httpx.Response:
        try:
            async with http_factory() as client:
                return await client.post(url, json=body, headers=headers)
        except httpx.TimeoutException as exc:
            raise BackendError(
                f"{provider_name} request timed out: {exc}",
                status=None,
            ) from exc
        except httpx.RequestError as exc:
            raise BackendError(
                f"{provider_name} request failed: {exc}",
                status=None,
            ) from exc

    headers = await auth.get_authorization_header()
    headers.setdefault("content-type", "application/json")
    resp = await _do_post(headers)

    if resp.status_code == 401:
        logger.warning(
            "%s: %s returned 401, invalidating auth cache and retrying once",
            provider_name,
            url,
        )
        auth.invalidate_cache()
        headers = await auth.get_authorization_header()
        headers.setdefault("content-type", "application/json")
        resp = await _do_post(headers)
        if resp.status_code == 401:
            raise AuthError(
                f"Authentication failed twice against {provider_name}; "
                f"token state may be corrupt. Run '{auth_login_cmd}' to re-authenticate."
            )

    if resp.status_code == 200:
        try:
            return resp.json()
        except ValueError as exc:
            raise BackendError(
                f"{provider_name} returned 200 but the body is not JSON: {exc}",
                status=200,
            ) from exc

    if resp.status_code == 429:
        retry_after_raw = resp.headers.get("retry-after")
        retry_after: float | None = None
        if retry_after_raw is not None:
            try:
                retry_after = float(retry_after_raw)
            except ValueError:
                retry_after = None
        raise BackendError(
            f"{provider_name} rate limit exceeded (429). "
            f"Retry after {retry_after_raw or 'unknown'} seconds.",
            status=429,
            retry_after=retry_after,
        )

    if resp.status_code == 403:
        raise AuthError(
            f"{provider_name} returned 403 Forbidden. Token is valid but "
            f"lacks permission. Response: {resp.text[:500]}. "
            f"Run '{auth_login_cmd}' to re-authenticate with the correct scopes."
        )

    raise BackendError(
        f"{provider_name} API error {resp.status_code}: {resp.text[:500]}",
        status=resp.status_code,
    )
