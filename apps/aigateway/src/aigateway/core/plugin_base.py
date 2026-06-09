from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, cast

from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from .credential_blob.store import CredentialBlobStore
    from .oauth.identity import AccountIdentity
    from .profile_index import ProfileIndexStore
    from .profile_models import AuthType


class PluginSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)


@dataclass(frozen=True)
class ModelEntry:
    """Single entry contributed to LiteLLM's model_list.

    Maps directly onto the dict shape that `litellm.Router(model_list=...)`
    expects. `model_name` is the user-facing alias; `litellm_params.model`
    is the fully-qualified provider/model string.
    """

    model_name: str
    litellm_params: dict[str, Any]


class CredentialStrategy(ABC):
    """Per-provider credential producer (the auth "port").

    Implementations own credential reads, refresh-on-401 with locking, and
    any provider-specific header construction. The auth bridge calls
    `get_authorization_header()` right before LiteLLM dispatches a request.
    Implementations may be OAuth-backed (token refresh) or API-key-backed
    (no refresh; `refresh_credentials` is a no-op).
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


# Back-compat alias: existing plugins/tests import the port under its original
# OAuth-specific name. New code should use CredentialStrategy.
OAuthStrategy = CredentialStrategy


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


class ProviderPluginBase[TSettings: PluginSettings](ABC):
    """Contract for an aigateway provider plugin.

    Each plugin owns: model contributions, the OAuth strategy, and the
    auth UI router. The gateway core loads plugins, builds a litellm
    Router from their combined model lists, and mounts each auth router
    under `/v1/auth/{custom_llm_provider}`.
    """

    custom_llm_provider: str
    settings_cls: ClassVar[type[PluginSettings]] = PluginSettings

    def __init__(self, settings: TSettings | None = None) -> None:
        self.settings = settings if settings is not None else cast(TSettings, self.settings_cls())

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
    ) -> CredentialStrategy | None:
        """Return a per-profile OAuth strategy. Default: no auth."""
        return None

    def api_key_strategy_for(
        self,
        profile_name: str,
        *,
        credential_store: CredentialBlobStore | None = None,
    ) -> CredentialStrategy | None:
        """Return a per-profile API-key strategy, or None when the provider
        does not support API-key auth (e.g. codex subscription endpoints)."""
        return None

    def credential_strategy_for(
        self,
        profile_name: str,
        *,
        auth_type: AuthType = "oauth",
        credential_store: CredentialBlobStore | None = None,
        http_client_factory: Any | None = None,
    ) -> CredentialStrategy | None:
        """Resolve the credential strategy for ``profile_name`` by auth type."""
        if auth_type == "api_key":
            return self.api_key_strategy_for(profile_name, credential_store=credential_store)
        return self.oauth_strategy_for(
            profile_name,
            credential_store=credential_store,
            http_client_factory=http_client_factory,
        )

    async def exchange_oauth_code(self, request: OAuthCodeExchangeRequest) -> dict[str, Any]:
        """Exchange an OAuth authorization code for provider credentials."""
        raise NotImplementedError(f"{self.custom_llm_provider} does not exchange OAuth codes")

    def account_label_from_credentials(self, _credentials: dict[str, Any]) -> str | None:
        """Return a display label for credentials persisted after OAuth, if available."""
        return None

    def credential_service_provider(self) -> str:
        """Return the provider namespace used in persisted credential service keys."""
        return self.custom_llm_provider

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


def credential_service_provider_for(plugin: Any, provider: str) -> str:
    getter = getattr(plugin, "credential_service_provider", None)
    if callable(getter):
        value = getter()
        if isinstance(value, str) and value:
            return value
    return provider


def credential_strategy_from(
    plugin: Any,
    profile_name: str,
    *,
    auth_type: AuthType = "oauth",
    credential_store: CredentialBlobStore | None = None,
    http_client_factory: Any | None = None,
) -> CredentialStrategy | None:
    """Resolve a plugin's credential strategy, tolerating duck-typed plugins
    that only implement the legacy ``oauth_strategy_for`` hook (mirrors
    ``credential_service_provider_for``)."""
    resolver = getattr(plugin, "credential_strategy_for", None)
    if callable(resolver):
        return resolver(
            profile_name,
            auth_type=auth_type,
            credential_store=credential_store,
            http_client_factory=http_client_factory,
        )
    if auth_type == "api_key":
        api_resolver = getattr(plugin, "api_key_strategy_for", None)
        if callable(api_resolver):
            return api_resolver(profile_name, credential_store=credential_store)
        return None
    legacy = getattr(plugin, "oauth_strategy_for", None)
    if callable(legacy):
        return legacy(
            profile_name,
            credential_store=credential_store,
            http_client_factory=http_client_factory,
        )
    return None
