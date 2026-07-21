"""OpenRouter provider plugin (OME-428 Checkpoint A — local BYOK).

An API-key-only provider (no OAuth) routed through LiteLLM's built-in
``openrouter`` provider. Key design points (validated against litellm 1.87.0):

- Disabled by default (plan D2): a disabled plugin registers no models and
  returns no API-key strategy, so no key can be stored and every dispatch
  path fails closed through existing route handling — even for connection
  rows created while the provider was enabled.
- Exactly one gateway prefix (plan D8): the gateway ID
  ``openrouter/<author>/<model>[:variant]`` is passed to LiteLLM unchanged;
  LiteLLM's provider routing strips the single ``openrouter/`` prefix at the
  wire, so upstream receives ``<author>/<model>[:variant]`` exactly once.
  ``prepare_chat_body`` validates the upstream remainder before dispatch and
  copies the body — it never mutates the caller's dict.
- Non-streaming in every mode (plan D5): the route rejects ``stream:true``
  before credentials are read.
- Only 401 marks the stored credential unusable (plan D9); 402/403/408/429/5xx
  are provider/billing states and must not invalidate a valid key.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, cast

from fastapi import HTTPException

from aigateway.core.api_key_strategy import ApiKeyStrategy
from aigateway.core.http_status import valid_http_error_status
from aigateway.core.plugin_base import (
    CredentialStrategy,
    ModelEntry,
    ProviderPluginBase,
)
from aigateway.core.provider_errors import NonRetryableProviderError

from .provenance import converter_error_status, is_http200_body_error
from .settings import (
    GATEWAY_MODEL_PREFIX,
    OpenRouterPluginSettings,
    is_valid_upstream_model_id,
)

if TYPE_CHECKING:
    from aigateway.core.credential_blob.store import CredentialBlobStore


def _credential_service_for(profile_name: str) -> str:
    """Namespace the stored credential slot by provider + profile/connection."""
    return f"aigateway:openrouter:{profile_name}"


# D7: the gateway owns routing — every dispatch goes to the official API base.
OFFICIAL_API_BASE = "https://openrouter.ai/api/v1"

# D7: trusted attribution, injected AFTER caller-header sanitization so the
# gateway owns these keys end-to-end. LiteLLM 1.87.0 lets caller headers
# override its OR_SITE_URL/OR_APP_NAME defaults (openrouter_headers.update),
# which is exactly why the caller's copies must be dropped first.
_TRUSTED_ATTRIBUTION = {
    "HTTP-Referer": "https://screamingface.ai",
    "X-OpenRouter-Title": "ScreamingFace",
    "X-Title": "ScreamingFace",
}

# Caller copies of auth, host/framing, and attribution headers are dropped
# before the gateway injects its own (D7). Lower-cased for comparison.
_STRIPPED_CALLER_HEADERS = frozenset(
    {
        # auth
        "authorization",
        "x-api-key",
        "proxy-authorization",
        # host / framing
        "host",
        "content-length",
        "transfer-encoding",
        # attribution (gateway-owned)
        "http-referer",
        "referer",
        "x-openrouter-title",
        "x-title",
    }
)

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


def _invalid_model_error() -> HTTPException:
    # Gateway-authored message only — never echo the raw caller value.
    return HTTPException(
        status_code=400,
        detail={
            "code": "invalid_model",
            "provider": "openrouter",
            "message": (
                "model must be 'openrouter/<author>/<model>' with an optional single ':variant'"
            ),
        },
    )


class _UnsafeLiteLLMStateError(HTTPException):
    """A pre-dispatch global-state conflict that the retry loop must not repeat."""

    aigw_non_retryable = True


def _unsafe_litellm_state_error() -> _UnsafeLiteLLMStateError:
    return _UnsafeLiteLLMStateError(
        status_code=503,
        detail={
            "code": "provider_unavailable",
            "message": "OpenRouter dispatch is unavailable",
        },
    )


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


def _embedded_error_status(error: Any) -> int | None:
    """Extract a numeric HTTP status from an embedded error object, else None.

    # WHY (blocker E): uses the shared strict validator so a string/Unicode/
    # float/bool ``code`` on the returned-payload scanner path degrades to 502
    # exactly like it does on the converter-raise and transport paths.
    """
    if not isinstance(error, dict):
        return None
    for key in ("status", "status_code", "code"):
        status = valid_http_error_status(error.get(key))
        if status is not None:
            return status
    return None


def _top_level_error_is_meaningful(error: Any) -> bool:
    """Gate for the top-level ``error`` scan (OME-428 CODE-1).

    # WHY: litellm's converter deliberately passes benign top-level error
    # shapes through as valid 200 responses ("some OpenAI-compatible providers
    # return empty error objects even on success"); flagging those discards a
    # paid completion as a 502.
    # INVARIANT: supersets litellm convert_dict_to_response.py:496-509
    # (1.87.0) — fires on every shape litellm raises on, PLUS status-keyed
    # shapes litellm passes through, so an embedded status can never render
    # as success. Pinned by test_litellm_top_level_error_contract.py.
    """
    if error is None:
        return False
    if isinstance(error, dict):
        return (
            bool(error.get("message", ""))
            or error.get("code") is not None
            or error.get("status") is not None
            or error.get("status_code") is not None
        )
    if isinstance(error, str):
        return bool(error)
    # Non-dict/non-str non-None: litellm :507-509 treats it as unconditionally
    # meaningful — bool(error) would diverge on 0/False/[].
    return True


def _find_embedded_error(payload: dict[str, Any]) -> tuple[bool, int | None]:
    """Detect OpenRouter errors embedded in a nominal HTTP-200 body (D9).

    Inspects the top-level ``error``, each choice's ``error``, and LiteLLM's
    ``provider_specific_fields`` (``error`` / ``native_finish_reason`` — 1.87.0
    maps the native reason "error" to "stop", which would otherwise render as
    success). Returns (found, first numeric 4xx/5xx status or None).
    """
    found = False
    status: int | None = None

    def _inspect(error: Any) -> None:
        nonlocal found, status
        if error is None:
            return
        found = True
        if status is None:
            status = _embedded_error_status(error)

    # CODE-1: only a meaningful top-level error counts; benign shapes on a
    # billed 200 pass through. The choice/message-level branches below stay
    # ungated — litellm relocates those without any benign-shape guard.
    top_level_error = payload.get("error")
    if _top_level_error_is_meaningful(top_level_error):
        _inspect(top_level_error)
    choices = payload.get("choices")
    for choice in choices if isinstance(choices, list) else []:
        if not isinstance(choice, dict):
            continue
        _inspect(choice.get("error"))
        for holder in (choice, choice.get("message")):
            if not isinstance(holder, dict):
                continue
            fields = holder.get("provider_specific_fields")
            if not isinstance(fields, dict):
                continue
            _inspect(fields.get("error"))
            if fields.get("native_finish_reason") == "error":
                found = True
    return found, status


def _embedded_error_exception(status: int | None) -> HTTPException:
    """Sanitized gateway error for an embedded provider failure.

    Only the numeric status survives; raw provider message/metadata is
    discarded. Malformed/status-less embedded errors map to 502 (D9).

    # INVARIANT (CODE-2): the upstream call already returned this payload, so
    # the error is non-retryable — an embedded 429/503/529 must make exactly
    # one upstream call. No Retry-After is invented: the embedded JSON schema
    # was not shown to carry one; validated hints survive only on actual
    # transport exceptions.
    """
    resolved = status if status is not None else 502
    code = "provider_error"
    if resolved == 401:
        code = "auth_required"
    elif resolved == 400:
        code = "bad_request"
    elif resolved == 429:
        code = "rate_limited"
    elif resolved >= 500 and status is not None:
        code = "provider_unavailable"
    return NonRetryableProviderError(
        status_code=resolved,
        detail={"code": code, "message": "OpenRouter reported a provider error"},
    )


class OpenRouterProviderPlugin(ProviderPluginBase[OpenRouterPluginSettings]):
    custom_llm_provider = "openrouter"
    settings_cls = OpenRouterPluginSettings

    def register_models(self) -> list[ModelEntry]:
        if not self.settings.enabled:
            # D2: a disabled provider exposes no models.
            return []
        return [
            ModelEntry(model_name=slug, litellm_params={"model": slug})
            for slug in self.settings.default_models
        ]

    def supports_api_key(self) -> bool:
        return True

    def supports_chat_streaming(self) -> bool:
        # D5: enforced in every credential mode; the route rejects stream:true
        # before _inject_credentials so no credential is ever read for it.
        return False

    def api_key_strategy_for(
        self,
        profile_name: str,
        *,
        credential_store: CredentialBlobStore | None = None,
    ) -> CredentialStrategy | None:
        if not self.settings.enabled:
            # D2 fail closed: no strategy means the api-key connection routes
            # answer 400 api_key_not_supported and chat cannot resolve
            # credentials, without any provider branch in core.
            return None
        return ApiKeyStrategy(
            profile_name,
            service=_credential_service_for(profile_name),
            account="default",
            header_builder=lambda api_key: {"Authorization": f"Bearer {api_key}"},
            credential_store=credential_store,
        )

    def should_mark_profile_error_on_dispatch_status(self, status_code: int) -> bool:
        # D9: only 401 proves the stored key is bad. 402 (credits), 403
        # (policy), 408/429/5xx (transient) must not invalidate a valid key.
        return status_code == 401

    def prepare_chat_body(self, body: dict[str, Any]) -> dict[str, Any]:
        out = _strip_openrouter_litellm_controls(body)
        model = out.get("model")
        if not isinstance(model, str) or not model.startswith(GATEWAY_MODEL_PREFIX):
            raise _invalid_model_error()
        if not is_valid_upstream_model_id(model[len(GATEWAY_MODEL_PREFIX) :]):
            raise _invalid_model_error()
        # Keep the model unchanged: the gateway prefix IS LiteLLM's provider
        # prefix, so LiteLLM strips it exactly once at the wire (D8).
        out.pop("api_key", None)  # gateway-owned; injected after this hook
        extra_headers = out.get("extra_headers")
        headers: dict[str, Any] = {}
        if isinstance(extra_headers, dict):
            headers = {
                key: value
                for key, value in extra_headers.items()
                if str(key).lower() not in _STRIPPED_CALLER_HEADERS
            }
        headers.update(_TRUSTED_ATTRIBUTION)
        out["extra_headers"] = headers
        # Pinned official base (D7): the ingress strip removed any caller
        # value; request-local api_base beats every LiteLLM global/env
        # fallback (litellm 1.87.0 main.py precedence).
        out["api_base"] = OFFICIAL_API_BASE
        return out

    async def chat_completion(self, body: dict[str, Any]) -> Any:
        import litellm

        # INVARIANT: process-global LiteLLM routing and callbacks must never
        # receive or redirect an account-scoped OpenRouter credential.
        if _has_unsafe_litellm_global_state(litellm, body.get("model")):
            raise _unsafe_litellm_state_error()

        dispatch_body = dict(body)
        # WHY: these gateway-owned values override ambient SSL_VERIFY and
        # process-global LiteLLM cache state. AIGateway's own encrypted,
        # account-scoped request cache is handled before this provider call.
        dispatch_body["ssl_verify"] = True
        dispatch_body["caching"] = False
        dispatch_body["cache"] = {"no-cache": True, "no-store": True}

        # cast: acompletion's static type is a ModelResponse|CustomStreamWrapper
        # union, but D5 guarantees non-streaming here (stream rejected at the
        # route before dispatch), so model_dump is always present.
        try:
            response = cast("Any", await litellm.acompletion(**dispatch_body))
        except Exception as exc:
            # WHY (FINDING A): litellm 1.87.0 RAISES while converting a nominal
            # HTTP-200 body that carries a meaningful top-level error — it never
            # returns a payload for _find_embedded_error to scan below. Such an
            # error came from an already-returned (billable) upstream call, so
            # route it through the SAME sanitizer as a scanned embedded error:
            # non-retryable, status sanitized, raw provider text discarded.
            # INVARIANT: a genuine transport failure is re-raised unchanged so
            # the shared overload-retry loop (core.retry) still applies to it.
            if is_http200_body_error(exc):
                raise _embedded_error_exception(converter_error_status(exc)) from exc
            raise
        payload: Any = response.model_dump() if hasattr(response, "model_dump") else response
        if isinstance(payload, dict):
            found, status = _find_embedded_error(payload)
            if found:
                # A 401 here flows through the route's dispatch-failure path
                # and marks only the selected connection (D9 local).
                raise _embedded_error_exception(status)
        # Return the dumped dict so native usage/cost/generation metadata
        # reaches the caller byte-for-byte (D10 — URL4 per-leaf telemetry).
        return payload


PLUGIN = OpenRouterProviderPlugin()
