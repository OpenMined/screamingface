"""The LiteLLM control-plane surface this provider must neutralize.

WHY this is its own module: OpenRouter dispatches through a SHARED LiteLLM
surface, so two hazards apply to it that do not apply to a provider with its own
transport — orchestration selectors a caller can plant in the request body, and
process-global callbacks or routing that can observe or redirect an
account-scoped BYOK credential. Both are LiteLLM vocabulary rather than
OpenRouter's, and both are pure functions over data.

INVARIANT: nothing here rejects a request. The strip removes fields — idempotently,
so ``prepare_chat_body`` may repeat it as defense in depth — and the detector only
reports. Refusing is the plugin's decision, never this module's.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_LITELLM_GLOBAL_CALLBACK_FIELDS = (
    "callbacks",
    "input_callback",
    "success_callback",
    "failure_callback",
    "_async_input_callback",
    "_async_success_callback",
    "_async_failure_callback",
)

_LITELLM_GLOBAL_RULE_FIELDS = ("pre_call_rules", "post_call_rules")

_OPENROUTER_LITELLM_CONTROL_FIELDS = frozenset(
    {
        "litellm_credential_name",
        "guardrails",
        "guardrail_config",
        "disable_global_guardrails",
        "prompt_id",
        "prompt_variables",
        "prompt_label",
        "prompt_version",
        "caching",
        "cache_key",
        "preset_cache_key",
    }
)

_OPENROUTER_METADATA_CONTROL_FIELDS = frozenset(
    {"disable_global_guardrails", "guardrails", "previous_models"}
)

_OPENROUTER_NESTED_METADATA_CONTROL_FIELDS = frozenset({"disable_global_guardrails", "guardrails"})


def _has_unsafe_litellm_global_state(litellm: Any, model: object) -> bool:
    """Detect process-global controls that can observe or reroute BYOK calls."""
    aliases = getattr(litellm, "model_alias_map", None)
    if isinstance(model, str) and isinstance(aliases, Mapping) and model in aliases:
        return True
    if getattr(litellm, "model_fallbacks", None):
        return True
    if any(bool(getattr(litellm, field, None)) for field in _LITELLM_GLOBAL_RULE_FIELDS):
        return True
    for field in _LITELLM_GLOBAL_CALLBACK_FIELDS:
        callbacks = getattr(litellm, field, None)
        if callbacks and any(callback != "cache" for callback in callbacks):
            return True
    return False


def _strip_openrouter_litellm_controls(body: dict[str, Any]) -> dict[str, Any]:
    """Remove LiteLLM orchestration selectors without changing other providers."""
    out = {
        key: value for key, value in body.items() if key not in _OPENROUTER_LITELLM_CONTROL_FIELDS
    }
    metadata = out.get("metadata")
    if not isinstance(metadata, Mapping):
        return out
    sanitized_metadata = {
        key: value
        for key, value in metadata.items()
        if key not in _OPENROUTER_METADATA_CONTROL_FIELDS
    }
    for nested_key in ("requester_metadata", "user_api_key_metadata"):
        nested_metadata = sanitized_metadata.get(nested_key)
        if isinstance(nested_metadata, Mapping):
            sanitized_metadata[nested_key] = {
                key: value
                for key, value in nested_metadata.items()
                if key not in _OPENROUTER_NESTED_METADATA_CONTROL_FIELDS
            }
    out["metadata"] = sanitized_metadata
    return out
