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

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from screamingface.plugins.llm_base.messages import CoreMessage, ToolDefinition


@dataclass
class HealthStatus:
    """Result of a backend health check.

    Attributes:
        authenticated: Whether the backend has a valid auth credential.
        error: Human-readable error message when authenticated is False.
        tokens_remaining: Remaining token capacity from rate limit headers.
            None if the backend doesn't report this or the check didn't
            reach the API.
        requests_remaining: Remaining request capacity from rate limit headers.
        rate_limit: Full rate limit info as key-value pairs (provider-specific).
    """

    authenticated: bool
    error: str | None = None
    tokens_remaining: int | None = None
    requests_remaining: int | None = None
    rate_limit: dict[str, str | int | float] = field(default_factory=dict)


class Backend(ABC):
    """Abstract contract for a provider backend."""

    async def health(self) -> HealthStatus:
        """Check backend health: auth validity and rate limit capacity.

        The default implementation just checks whether
        ``get_authorization_header()`` succeeds. Concrete backends should
        override to add rate-limit capacity info from the provider.
        """
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

        Flow:
          1. Call ``auth.get_authorization_header()`` for headers.
          2. Call ``adapter.to_provider_format(messages, ...)`` for
             the request body.
          3. POST to the provider's endpoint.
          4. On 200: ``adapter.from_provider_response(data)``.
          5. On 401: invalidate auth cache, retry once.
          6. On other errors: raise :class:`BackendError` with status.

        Raises:
            AuthError: Auth path broke and the user must re-auth.
            BackendError: Provider returned a non-success status or
                the network failed.
            AdapterError: Request or response couldn't be adapted
                to/from our canonical shape.
        """
