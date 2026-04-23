"""llm-base plugin — shared ABCs and types for multi-backend LLM providers.

This plugin registers no routes, no hooks, and no settings. Its only
purpose is to exist in the SF plugin registry (so other plugins can
declare ``depends = ["llm-base"]``) and to expose a stable Python import
surface that every concrete provider plugin builds on.

Public API
----------

Types:
  - :class:`CoreMessage` — provider-agnostic message shape (Vercel AI SDK
    inspired). Each message has a role and a content list of typed parts.
  - :class:`TextPart`, :class:`ImagePart`, :class:`ToolCallPart`,
    :class:`ToolResultPart`, :class:`ReasoningPart` — content block types.
  - :class:`ToolDefinition` — minimal tool-use schema.

ABCs:
  - :class:`CredentialStore` — cross-platform secret storage
    (macOS Keychain / Linux libsecret / Windows Credential Manager).
  - :class:`AuthStrategy` — how to build the ``Authorization`` header
    for an outbound provider call. Concrete subclasses live in each
    provider plugin (e.g. ``ClaudeCodeOAuth`` in claude_backend_api).
  - :class:`Adapter` — converts CoreMessage lists to/from a specific
    provider's wire format (Gang-of-Four Adapter pattern).
  - :class:`Backend` — the runtime for a provider. Combines auth +
    adapter + httpx client.

Errors:
  All errors inherit from :class:`LlmBaseError`.

Concrete helpers:
  :func:`get_credential_store` returns the platform-appropriate concrete
  :class:`CredentialStore` implementation.
"""

from __future__ import annotations

from screamingface.plugins.llm_base.adapter_base import (
    Adapter,
    collect_provider_metadata,
    extract_system_text,
)
from screamingface.plugins.llm_base.auth_base import AuthStrategy
from screamingface.plugins.llm_base.backend_base import (
    Backend,
    HealthStatus,
    post_with_default_retry,
)
from screamingface.plugins.llm_base.constants import (
    CLI_ONLY_FIELDS,
    DEFAULT_MAX_TOKENS,
    PROMPT_PREVIEW_LIMIT,
    STDOUT_PREVIEW_LIMIT,
)
from screamingface.plugins.llm_base.credential_store import (
    CredentialStore,
    LinuxLibsecretStore,
    MacOSKeychainStore,
    WindowsCredentialManagerStore,
    get_credential_store,
)
from screamingface.plugins.llm_base.errors import (
    AdapterError,
    AuthError,
    BackendError,
    CredentialNotFoundError,
    LlmBaseError,
)
from screamingface.plugins.llm_base.http import default_http_factory, make_http_factory
from screamingface.plugins.llm_base.messages import (
    CoreMessage,
    ImagePart,
    ReasoningPart,
    TextPart,
    ToolCallPart,
    ToolDefinition,
    ToolResultPart,
    extract_text,
)
from screamingface.plugins.llm_base.oauth_base import OAuthStrategy

__all__ = [
    # ABCs
    "AuthStrategy",
    "OAuthStrategy",
    "Backend",
    "CredentialStore",
    "Adapter",
    "HealthStatus",
    "post_with_default_retry",
    # Adapter helpers
    "collect_provider_metadata",
    "extract_system_text",
    # Concrete credential stores
    "LinuxLibsecretStore",
    "MacOSKeychainStore",
    "WindowsCredentialManagerStore",
    "get_credential_store",
    # Messages
    "CoreMessage",
    "TextPart",
    "ImagePart",
    "ToolCallPart",
    "ToolResultPart",
    "ReasoningPart",
    "ToolDefinition",
    "extract_text",
    # Constants
    "CLI_ONLY_FIELDS",
    "DEFAULT_MAX_TOKENS",
    "PROMPT_PREVIEW_LIMIT",
    "STDOUT_PREVIEW_LIMIT",
    # HTTP
    "default_http_factory",
    "make_http_factory",
    # Errors
    "LlmBaseError",
    "AuthError",
    "BackendError",
    "CredentialNotFoundError",
    "AdapterError",
]
