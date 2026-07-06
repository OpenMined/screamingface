"""Hugging Face provider plugin for the AI Gateway (SF-345).

An API-key-only provider (no OAuth). Chat routes through LiteLLM's built-in
``huggingface`` provider against the unified OpenAI-compatible router
(``https://router.huggingface.co/v1``); the request-local HF token is injected by
the gateway as ``body["api_key"]`` and never read from the process environment.

Key design points (validated against litellm 1.87.0):
- ``register_models`` emits ``huggingface/<org>/<model>:<provider>`` entries with the
  router pinned as ``api_base``. Pinning ``api_base`` short-circuits litellm's
  per-request provider-mapping fetch to ``huggingface.co`` (which would be
  ``HUGGINGFACE_API_KEY``-env-keyed and ignore the request token).
- ``prepare_chat_body`` injects that same ``api_base`` on dispatch (the default
  ``chat_completion`` calls ``litellm.acompletion(**body)``, which does not read
  ``register_models`` params) and strips any caller-supplied auth so only the
  gateway-owned credential reaches upstream.
- Only 401 marks the stored credential unusable; 403 is ambiguous (model-access vs
  token permission) and must not nuke a valid key.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aigateway.core.api_key_strategy import ApiKeyStrategy
from aigateway.core.plugin_base import (
    CredentialStrategy,
    ModelEntry,
    ProviderPluginBase,
)

from .settings import HuggingFacePluginSettings

if TYPE_CHECKING:
    from aigateway.core.credential_blob.store import CredentialBlobStore

# Caller-supplied copies of these are stripped before the gateway injects its own
# provider-owned values, so a client can never smuggle auth/billing material upstream.
_CLIENT_OWNED_HEADER_NAMES = {
    "authorization",
    "proxy-authorization",
    "x-api-key",
    "x-hf-bill-to",
}


def _credential_service_for(profile_name: str) -> str:
    """Namespace the stored credential slot by provider + profile/connection."""
    return f"aigateway:huggingface:{profile_name}"


class HuggingFaceProviderPlugin(ProviderPluginBase[HuggingFacePluginSettings]):
    custom_llm_provider = "huggingface"
    settings_cls = HuggingFacePluginSettings

    def register_models(self) -> list[ModelEntry]:
        api_base = self.settings.router_api_base
        return [
            ModelEntry(model_name=slug, litellm_params={"model": slug, "api_base": api_base})
            for slug in self.settings.default_models
        ]

    def supports_api_key(self) -> bool:
        return True

    def api_key_strategy_for(
        self,
        profile_name: str,
        *,
        credential_store: CredentialBlobStore | None = None,
    ) -> CredentialStrategy:
        return ApiKeyStrategy(
            profile_name,
            service=_credential_service_for(profile_name),
            account="default",
            header_builder=lambda api_key: {"Authorization": f"Bearer {api_key}"},
            credential_store=credential_store,
        )

    def should_mark_profile_error_on_dispatch_status(self, status_code: int) -> bool:
        # 401 => bad/missing token (invalidate). 403 is ambiguous (model-access vs
        # token permission) and must not invalidate a valid stored credential.
        return status_code == 401

    def prepare_chat_body(self, body: dict[str, Any]) -> dict[str, Any]:
        out = dict(body)
        # The gateway owns the key; a caller copy would be overwritten by injection
        # anyway, but drop it explicitly for defense in depth.
        out.pop("api_key", None)
        extra_headers = out.get("extra_headers")
        if isinstance(extra_headers, dict):
            sanitized = {
                key: value
                for key, value in extra_headers.items()
                if str(key).lower() not in _CLIENT_OWNED_HEADER_NAMES
            }
            if sanitized:
                out["extra_headers"] = sanitized
            else:
                out.pop("extra_headers", None)
        elif "extra_headers" in out:
            # A non-dict extra_headers would crash the downstream handler; drop it.
            out.pop("extra_headers", None)
        # Gateway-owned router base. routes/chat.py strips the caller's api_base
        # first, then we set our own; this keeps litellm on the request-local path.
        out["api_base"] = self.settings.router_api_base
        # HF provider caps differ by backend; omitting max_tokens lets the router choose
        # a provider-safe default instead of rejecting SF's generic 16k default.
        out.pop("max_tokens", None)
        bill_to = (self.settings.bill_to or "").strip()
        if bill_to:
            headers = dict(out.get("extra_headers") or {})
            headers["X-HF-Bill-To"] = bill_to
            out["extra_headers"] = headers
        return out


PLUGIN = HuggingFaceProviderPlugin()
