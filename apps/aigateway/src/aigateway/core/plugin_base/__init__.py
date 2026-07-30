"""The aigateway provider-plugin contract.

FEATURE: the port every provider implements. A plugin contributes models,
produces credentials, exposes auth routes, dispatches completions, and declares
its chat-parameter contract; the gateway core knows nothing provider-specific
beyond what these hooks return.

INVARIANT (SOLID/hexagonal): core defines this port and never imports a plugin.
Wiring happens through the plugin registry, not through direct imports.

AIDEV-NOTE (OME-653): the implementation is split across ``_ports`` (value types
and the credential port), ``_provider`` (auth, model registration, dispatch),
``_contract`` (the OME-479 chat-parameter hooks) and ``_resolvers`` (duck-typed
credential resolution) purely to keep each file within the repository's 450-line
limit. That layout is an implementation detail — THIS module is the public
surface, and every name below is importable exactly as it was from the former
single ``plugin_base`` module. Import from here, never from a half.
"""

from ._contract import ProviderPluginBase
from ._ports import (
    CredentialStrategy,
    ModelEntry,
    OAuthCodeExchangeRequest,
    OAuthConfig,
    OAuthStrategy,
    PluginSettings,
)
from ._resolvers import credential_service_provider_for, credential_strategy_from

__all__ = [
    "CredentialStrategy",
    "ModelEntry",
    "OAuthCodeExchangeRequest",
    "OAuthConfig",
    "OAuthStrategy",
    "PluginSettings",
    "ProviderPluginBase",
    "credential_service_provider_for",
    "credential_strategy_from",
]
