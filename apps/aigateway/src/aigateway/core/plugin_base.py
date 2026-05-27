from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .credential_blob.store import CredentialBlobStore
    from .oauth.identity import AccountIdentity
    from .profile_index import ProfileIndexStore


@dataclass(frozen=True)
class ModelEntry:
    """Single entry contributed to LiteLLM's model_list.

    Maps directly onto the dict shape that `litellm.Router(model_list=...)`
    expects. `model_name` is the user-facing alias; `litellm_params.model`
    is the fully-qualified provider/model string.
    """

    model_name: str
    litellm_params: dict[str, Any]


class OAuthStrategy(ABC):
    """Per-provider credential producer.

    Implementations own credential reads, refresh-on-401 with locking, and
    any provider-specific header construction. The OAuth bridge calls
    `get_authorization_header()` right before LiteLLM dispatches a request.
    """

    @abstractmethod
    async def get_authorization_header(self) -> dict[str, str]:
        """Return headers to merge into the upstream request.

        Example: ``{"Authorization": "Bearer ..."}``.
        """

    async def invalidate(self) -> None:
        """Drop any cached token. Called after a 401 from upstream."""

    @abstractmethod
    async def persist_credentials(self, credentials: dict[str, Any]) -> None:
        """Persist newly exchanged provider credentials for this profile."""

    @abstractmethod
    async def delete_credentials(self) -> None:
        """Delete persisted provider credentials for this profile."""

    @abstractmethod
    async def refresh_credentials(self) -> None:
        """Refresh persisted provider credentials for this profile."""


@dataclass(frozen=True)
class OAuthConfig:
    """Provider-level OAuth metadata used to drive the start + callback flow."""

    authorize_url: str
    token_url: str
    client_id: str
    scopes: list[str]
    redirect_path: str  # absolute path on the gateway callback surface
    extra_authorize_params: dict[str, str] | None = None
    loopback_redirect_ports: list[int] | None = None


@dataclass(frozen=True)
class OAuthCodeExchangeRequest:
    """Provider-owned authorization-code exchange input."""

    code: str
    code_verifier: str
    redirect_uri: str
    state: str
    http_client_factory: Any | None = None


class ProviderPluginBase(ABC):
    """Contract for an aigateway provider plugin.

    Each plugin owns: model contributions, the OAuth strategy, and the
    auth UI router. The gateway core loads plugins, builds a litellm
    Router from their combined model lists, and mounts each auth router
    under `/v1/auth/{custom_llm_provider}`.
    """

    custom_llm_provider: str

    @abstractmethod
    def register_models(self) -> list[ModelEntry]:
        """Return the model_list entries this plugin contributes."""

    def oauth_config(self) -> OAuthConfig | None:
        """Return provider OAuth metadata, or None for no-auth providers (e.g. local Ollama)."""
        return None

    def oauth_strategy_for(
        self,
        profile_name: str,
        *,
        credential_store: CredentialBlobStore | None = None,
        http_client_factory: Any | None = None,
    ) -> OAuthStrategy | None:
        """Return a per-profile OAuthStrategy. Default: no auth."""
        return None

    async def exchange_oauth_code(self, request: OAuthCodeExchangeRequest) -> dict[str, Any]:
        """Exchange an OAuth authorization code for provider credentials."""
        raise NotImplementedError(f"{self.custom_llm_provider} does not exchange OAuth codes")

    def account_label_from_credentials(self, _credentials: dict[str, Any]) -> str | None:
        """Return a display label for credentials persisted after OAuth, if available."""
        return None

    async def extract_identity(
        self,
        _credentials: dict[str, Any],
        *,
        http_client_factory: Any | None = None,
    ) -> AccountIdentity | None:
        """Return stable account identity from provider credentials when available."""
        return None

    def requires_oauth_connection_label(self) -> bool:
        """Whether first-class OAuth connection creation needs a user label up front."""
        return False

    def supports_chat_streaming(self) -> bool:
        """Whether `/v1/chat/completions` may create a streaming response."""
        return True

    def prepare_chat_body(self, body: dict[str, Any]) -> dict[str, Any]:
        """Apply provider-specific request normalization before dispatch."""
        return body

    def should_apply_profile_default(self, field: str) -> bool:
        """Return whether a profile default field should be merged into chat bodies."""
        return True

    def allows_chatless_profile(self) -> bool:
        """Whether chat may proceed when no gateway OAuth profile exists."""
        return False

    def invalidate_profile_session(self, _profile_name: str) -> None:
        """Drop provider-owned per-profile chat/session cache, if any."""
        return None

    def should_mark_profile_error_on_dispatch_status(self, _status_code: int) -> bool:
        """Whether a provider dispatch failure means stored profile auth is unusable."""
        return False

    async def chat_completion(self, body: dict[str, Any]) -> Any:
        """Dispatch a normalized OpenAI-compatible chat completion request."""
        import litellm

        return await litellm.acompletion(**body)

    async def chat_completion_stream(self, body: dict[str, Any]) -> AsyncIterator[Any]:
        """Dispatch a normalized streaming chat completion request."""
        import litellm

        stream: Any = await litellm.acompletion(**body)
        async for chunk in stream:
            yield chunk

    def auth_router(self):
        """Provider-specific auth routes.

        Handlers should require `CurrentAccount` unless they are OAuth callback
        targets protected by a pending-auth state nonce.
        """
        return None

    async def bootstrap_profiles(
        self,
        *,
        account_id: str,
        credential_store: CredentialBlobStore | None = None,
        index_store: ProfileIndexStore | None = None,
    ) -> None:
        """Populate provider-owned profile metadata at startup, if any."""
        return None
