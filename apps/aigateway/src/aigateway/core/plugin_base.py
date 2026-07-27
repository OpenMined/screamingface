from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, cast

from pydantic_settings import BaseSettings, SettingsConfigDict

from .api_key_validation import ApiKeyValidator

# Runtime (not TYPE_CHECKING) import: the default transport capability is
# CONSTRUCTED here, not merely annotated. Safe — ``chat_parameters`` is pure core
# vocabulary and imports nothing that reaches this module.
from .chat_parameters import stream_transport_capability

if TYPE_CHECKING:
    from .chat_parameters import (
        ParameterProjectionRule,
        ProviderDiscoverySnapshot,
        ProviderParameterObservation,
        ToolCapability,
        TransportCapability,
    )
    from .credential_blob.store import CredentialBlobStore
    from .oauth.identity import AccountIdentity
    from .parameter_discovery import DiscoveryHttpClient, DiscoveryLimits, DiscoverySourceRef
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

    def api_key_validator(self) -> ApiKeyValidator | None:
        """Return an operational API-key validator, or None when unavailable."""
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

    def supports_api_key(self) -> bool:
        """Whether this provider accepts a raw API key (vs OAuth-only).

        Capability flag surfaced to clients so the UI only offers API-key auth
        where it works. The default is False; providers that implement
        ``api_key_strategy_for`` override this to True. Codex stays False (its
        subscription endpoint is OAuth-only and rejects raw keys)."""
        return False

    # --- OME-479 effective parameter contract (Strategy hooks) ---------------
    #
    # INVARIANT: core owns the contract algebra; each plugin owns the rules it
    # selects. These hooks are the ONLY provider-specific input to the summary,
    # the detailed contract, and dispatch — one source, three projections.

    def chat_parameter_rules(
        self, *, model: str, auth_type: AuthType | None = None
    ) -> tuple[ParameterProjectionRule, ...]:
        """Reviewed, provider-owned dispatch rules for ``model``.

        INVARIANT: a rule is the ONLY thing that enables a parameter, so the
        default is none — a provider advertises (and later forwards) an
        optional parameter only by returning a rule here. Dynamic discovery
        never creates or enables one.

        ``auth_type=None`` requests every rule the provider owns for the model
        and is used SOLELY to derive the conservative profile-independent
        summary; it must never be read as permission for every auth mode. A
        concrete auth mode filters rules for the profile-bound detailed
        contract and for dispatch.
        """
        return ()

    def chat_parameter_tools(
        self, *, model: str, auth_type: AuthType | None = None
    ) -> tuple[ToolCapability, ...]:
        """Accepted OpenAI-compatible ``tools[].type`` capabilities for ``model``.

        Default: none. A provider advertises ``function`` only once it validates
        OpenAI-compatible tool definitions through the final provider boundary.
        """
        return ()

    def chat_parameter_observations(
        self, *, model: str, auth_type: AuthType | None = None
    ) -> tuple[ProviderParameterObservation, ...]:
        """Raw provider evidence for ``model`` (labelled-local in v1; no network).

        INVARIANT: an observation NEVER authorizes a parameter — only a rule
        does. Observations exist so the detailed contract can show a
        provider-supported-but-not-yet-projected field as visible-but-disabled.
        Default: none.
        """
        return ()

    def chat_discovery_source(self, *, model: str) -> DiscoverySourceRef | None:
        """The cache identity of this provider's dynamic source for ``model``.

        INVARIANT (§5.3): declared BEFORE any fetch, because the observation cache
        must decide whether a stored value is still trustworthy without paying for
        a round trip. A revision read off the fetched payload would let the source
        itself declare its own old evidence valid.

        INVARIANT: this is the ONE place that answers "is there a dynamic source
        for this model". Returning a ref commits the provider to answering
        ``discover_chat_parameter_snapshot`` with a snapshot or a
        ``DiscoveryError`` — a ``None`` there is then an inconsistency the runtime
        degrades on rather than caching as evidence.

        Default: None — no dynamic source; the detailed contract is served from
        labelled-local observations alone.
        """
        return None

    async def discover_chat_parameter_snapshot(
        self,
        *,
        model: str,
        client: DiscoveryHttpClient,
        limits: DiscoveryLimits | None = None,
    ) -> ProviderDiscoverySnapshot | None:
        """Best-effort DYNAMIC evidence for ``model`` from FIXED public catalogs.

        INVARIANT (§4.2/§5.2): the async sibling of
        ``chat_parameter_observations``. It fetches this provider's FIXED public
        documents through the INJECTED bounded transport (never a raw client,
        never a caller-supplied URL, never a credential). It NEVER runs on the
        chat dispatch path, and — like an observation — it NEVER enables a
        parameter; only a rule does.

        INVARIANT (§5.3): three outcomes, three signals, because a consumer must
        be able to tell an OUTAGE from an absence of evidence:

        - ``ProviderDiscoverySnapshot`` — the source was reached. An EMPTY
          snapshot is the honest "reached it; this model is not listed".
        - raises sanitized ``DiscoveryError`` — the fetch was attempted and
          FAILED. ``ObservationCache`` maps this to its stale/degraded paths.
        - ``None`` — NO ATTEMPT was made, and no connection was opened.

        AIDEV-NOTE: ``None`` must not be widened back to cover failure. The cache
        treats every normal return as a successful refresh, so a ``None`` returned
        for a failure is stored labelled ``fresh`` and evicts the last good
        snapshot — the contract then claims currency it never had.

        Default: None — no dynamic source; the caller relies on labelled-local
        observations alone.
        """
        return None

    def chat_transport_capabilities(
        self, *, model: str, auth_type: AuthType | None = None
    ) -> tuple[TransportCapability, ...]:
        """Transport controls (e.g. ``stream``) reported separately from params.

        Streaming is a transport capability, not an ordinary model parameter, so
        it is surfaced in its own contract section.

        INVARIANT: the default is DERIVED from ``supports_chat_streaming`` — the
        same flag ``/v1/chat/completions`` enforces — so the published contract
        cannot disagree with what dispatch actually does. Deriving it here rather
        than per plugin means a new provider is described correctly with no extra
        code, and no plugin can publish a status that contradicts its own flag.

        Override to add further controls, or to replace the ``stream`` entry when
        the plugin has real upstream evidence to report as ``provider_support``.
        """
        return (stream_transport_capability(gateway_enabled=self.supports_chat_streaming()),)

    def available_auth_modes(self) -> tuple[AuthType, ...]:
        """Auth modes a client could use with this provider (profile-independent).

        Drives the conservative summary intersection on ``/v1/models``. Derived
        from declared capability: api-key iff ``supports_api_key()``, oauth iff
        the provider advertises ``oauth_config()``. Providers with bespoke auth
        override this.
        """
        modes: list[AuthType] = []
        if self.supports_api_key():
            modes.append("api_key")
        if self.oauth_config() is not None:
            modes.append("oauth")
        return tuple(modes)

    def strip_provider_dispatch_controls(self, body: dict[str, Any]) -> dict[str, Any]:
        """Remove caller-supplied LiteLLM control-plane fields THIS provider owns.

        # WHY: the global ``strip_dispatch_controls`` covers provider-neutral
        # control fields; a provider that dispatches through a shared LiteLLM
        # surface (e.g. OpenRouter) may also expose orchestration selectors
        # (caching/guardrails/prompt-management/named-credential) that are not
        # model parameters. Those must be neutralized BEFORE the OME-479
        # fail-closed classifier runs, so the classifier only ever adjudicates
        # genuine model-parameter candidates — plan §4.5 tier (a): transport /
        # gateway-owned fields are authorized structurally, not via a rule.
        # INVARIANT: the returned body carries no field this provider will refuse
        # to forward; the strip is idempotent (``prepare_chat_body`` may repeat it
        # as defense in depth). Default: identity — a provider opts in by override.
        """
        return body

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
    resolver: Callable[..., CredentialStrategy | None] | None = getattr(
        plugin, "credential_strategy_for", None
    )
    if callable(resolver):
        return resolver(
            profile_name,
            auth_type=auth_type,
            credential_store=credential_store,
            http_client_factory=http_client_factory,
        )
    if auth_type == "api_key":
        api_resolver: Callable[..., CredentialStrategy | None] | None = getattr(
            plugin, "api_key_strategy_for", None
        )
        if callable(api_resolver):
            return api_resolver(profile_name, credential_store=credential_store)
        return None
    legacy: Callable[..., CredentialStrategy | None] | None = getattr(
        plugin, "oauth_strategy_for", None
    )
    if callable(legacy):
        return legacy(
            profile_name,
            credential_store=credential_store,
            http_client_factory=http_client_factory,
        )
    return None
