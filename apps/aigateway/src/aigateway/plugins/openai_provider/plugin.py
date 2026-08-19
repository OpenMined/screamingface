from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, cast

import httpx
from fastapi import HTTPException
from openai import AsyncOpenAI, Omit

from aigateway.core.api_key_strategy import ApiKeyStrategy
from aigateway.core.api_key_validation import ApiKeyValidator
from aigateway.core.cache_ports import CacheBypass
from aigateway.core.plugin_base import CredentialStrategy, ModelEntry, ProviderPluginBase
from aigateway.core.request_hardening import strip_dispatch_controls
from aigateway.core.standard_parameters import direct_parameter_observations

from .api_key_validation import OpenAIApiKeyValidator
from .global_cache import gateway_dispatch_controls, project_global_cache_request
from .parameters import openai_chat_parameter_rules
from .settings import OFFICIAL_API_BASE, OpenAIPluginSettings, is_route_valid_model_id

if TYPE_CHECKING:
    from aigateway.core.chat_parameters import (
        ParameterProjectionRule,
        ProviderParameterObservation,
    )
    from aigateway.core.credential_blob.store import CredentialBlobStore
    from aigateway.core.profile_models import AuthMode
    from aigateway.plugins.taxonomy.types import CacheReference


logger = logging.getLogger(__name__)

_OBSERVATION_SOURCE = "openai:locked-runtime"
# The environment variable LiteLLM reads to swap the OpenAI dispatch handler. Both the
# handler it selects and the one it replaces are pinned by this plugin's adapter
# revision, so an enabled flag is a runtime the revision does not describe.
_EXPERIMENTAL_HANDLER_ENV = "EXPERIMENTAL_OPENAI_BASE_LLM_HTTP_HANDLER"
_LITELLM_GLOBAL_CALLBACK_FIELDS = (
    "callbacks",
    "input_callback",
    "success_callback",
    "failure_callback",
    "_async_input_callback",
    "_async_success_callback",
    "_async_failure_callback",
)
# Process-global LiteLLM state that disqualifies the runtime when merely TRUTHY. ONE
# tuple rather than one branch each: the verdict and the reason are identical for every
# member — ambient routing, mutation or parameter-dropping that this plugin's adapter
# revision does not describe — so spelling them as separate early returns was a list
# pretending to be control flow. ``callbacks`` stay out of it: they need the ``"cache"``
# exemption below, which is a different question.
_LITELLM_GLOBAL_TRUTHY_FIELDS = (
    "model_fallbacks",
    "headers",
    "pre_call_rules",
    "post_call_rules",
    "drop_params",
    "additional_drop_params",
)


def _credential_service_for(profile_name: str) -> str:
    return f"aigateway:openai:{profile_name}"


def _openai_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        verify=True,
        trust_env=False,
        follow_redirects=False,
    )


def _invalid_model_error() -> HTTPException:
    # OME-884: the refusal is now about the model ID's GRAMMAR, not about catalog
    # membership — ``default_models`` publishes ``/v1/models`` and admits nothing. The
    # ``invalid_model`` code is a caller-visible contract and is unchanged; the message
    # is corrected so it no longer describes a registry check that no longer happens.
    return HTTPException(
        status_code=400,
        detail={
            "code": "invalid_model",
            "provider": "openai",
            "message": "model is not a valid direct OpenAI model id",
        },
    )


def _unsafe_environment_error() -> HTTPException:
    error = HTTPException(
        status_code=503,
        detail={
            "code": "unsafe_openai_environment",
            "provider": "openai",
            "message": "direct OpenAI dispatch is unavailable",
        },
    )
    cast("Any", error).aigw_non_retryable = True
    return error


def litellm_env_flag_is_true(value: object) -> bool:
    """Whether LiteLLM would read ``value`` from the environment as boolean true.

    # INVARIANT: parity with the INSTALLED implementation, not with intuition.
    # ``get_secret_bool`` delegates to ``str_to_bool``, which recognizes only
    # ``"true"`` and ``"false"`` after ``.strip().lower()`` and answers ``None`` for
    # everything else — so ``"yes"``, ``"1"``, ``"on"`` and ``""`` are NOT true, and an
    # unset variable is not either. Guessing more generously here would fail OPEN: the
    # gateway would refuse a runtime LiteLLM never entered.
    # WHY total over ``object``: the caller passes ``os.environ.get(...)``, which is
    # ``None`` when unset. ``None`` must be an answer, never a crash on the cache path.
    # AIDEV-NOTE: this models the ENVIRONMENT branch only. When a secret-manager client
    # is configured LiteLLM resolves the value somewhere this process cannot see, which
    # is why that state is its own refusal in ``_has_unsafe_openai_runtime_state``
    # rather than something this helper pretends to model.
    """
    return isinstance(value, str) and value.strip().lower() == "true"


def _has_unsafe_openai_runtime_state(litellm: Any) -> bool:
    """The fail-closed verdict on ambient state — MODEL-FREE.

    # INVARIANT (OME-884): ONE core, TWO readers — ``participates_in_global_cache`` and
    # ``chat_completion``. The cache is a SECOND route to this provider's answers: a
    # stored row needs neither a registered model nor a credential to be replayed, and
    # the cache stage runs ahead of both checks, so a dispatch-only guard would keep
    # serving rows from a runtime it refuses to dispatch into. Sharing the predicate is
    # what makes the two verdicts incapable of drifting apart.
    # INVARIANT: fail CLOSED. Every read is a defensive ``getattr``, so a LiteLLM whose
    # globals have MOVED costs a bypass, not a request.
    # AIDEV-NOTE: this function is NOT total on its own, and deliberately so. A global
    # that answers by RAISING — ``get_config()``, a hostile ``__bool__`` — still escapes
    # here; totality is enforced once, by its only caller
    # ``_has_unsafe_litellm_global_state``, which converts any such escape into the same
    # "unsafe" verdict. Do not add a second try/except here: two of them would let a
    # future reader believe either one alone is sufficient.
    # WHY each state disqualifies the runtime:
    #   OpenAIConfig            — its entries are merged into ``optional_params`` for
    #                             every OpenAI call, so an operator-set temperature
    #                             changes the answer while the key cannot see it.
    #   OPENAI_CUSTOM_HEADERS   — ambient headers ride along on the request.
    #   secret_manager_client   — an ambient resolver can supply the flag below and
    #                             other values from outside this process, so no
    #                             environment read is authoritative any more.
    #   experimental handler    — swaps the dispatch handler, and therefore the wire
    #                             behaviour this plugin's adapter revision pins.
    #   fallbacks/headers/proxy_auth/rules/callbacks (OME-864) — process-global routing
    #                             and observation that could redirect an account-scoped
    #                             credential or mutate the call.
    """
    if os.environ.get("OPENAI_CUSTOM_HEADERS"):
        return True
    if getattr(litellm, "secret_manager_client", None) is not None:
        return True
    if litellm_env_flag_is_true(os.environ.get(_EXPERIMENTAL_HANDLER_ENV)):
        return True
    if getattr(litellm, "proxy_auth", None) is not None:
        return True
    get_config = getattr(getattr(litellm, "OpenAIConfig", None), "get_config", None)
    if callable(get_config) and get_config():
        return True
    if any(bool(getattr(litellm, field, None)) for field in _LITELLM_GLOBAL_TRUTHY_FIELDS):
        return True
    return any(
        callbacks and any(callback != "cache" for callback in callbacks)
        for callbacks in (
            getattr(litellm, field, None) for field in _LITELLM_GLOBAL_CALLBACK_FIELDS
        )
    )


def _model_is_ambiently_aliased(litellm: Any, model: object) -> bool:
    """Whether a process-global LiteLLM alias REDIRECTS this exact requested model.

    # WHY this is per-model and not folded into the core above: an alias silently sends
    # one id somewhere else, so a row stored under the requested id would be replayed
    # while a miss dispatched something different — a wrong-hit class for THAT model and
    # no reason at all to abandon every other model's cache.
    # INVARIANT: EXACT key match only. An alias for a different model, or for another
    # provider entirely, must leave direct OpenAI fully working.
    """
    aliases = getattr(litellm, "model_alias_map", None)
    return isinstance(model, str) and isinstance(aliases, Mapping) and model in aliases


def _has_unsafe_litellm_global_state(litellm: Any, model: object) -> bool:
    """The verdict both readers share: the ambient core plus this request's own alias.

    # INVARIANT: TOTAL. An ambient read that RAISES counts as unsafe, exactly like one
    # that answers with a poisoned value. The reads below are all defensive about a
    # MISSING attribute, but a LiteLLM global can also answer BY raising —
    # ``OpenAIConfig.get_config()`` is a call, ``model in aliases`` runs a hostile
    # ``__contains__``, and ``bool(...)`` runs a hostile ``__bool__``. Before this guard
    # such a runtime escaped as an ordinary exception, and the two paths degraded
    # differently: the cache stage absorbed it into its own catch-all (reporting this
    # provider's projection bypass for something that was not a projection decision),
    # while dispatch surfaced a generic 502 ``provider_error`` — blaming OpenAI for a
    # runtime the GATEWAY could not certify.
    # WHY one try/except here rather than one per read: this function is the single
    # junction both ``participates_in_global_cache`` and ``chat_completion`` pass
    # through, so guarding it makes BOTH total and keeps the two verdicts structurally
    # incapable of diverging. Guarding each read would be eight places to forget.
    # WHY the verdict is UNSAFE and not merely "unknown": the gate certifies that the
    # process-global state cannot change the answer. A runtime it could not inspect has
    # not been certified, and a cache row may not be filled or replayed on the strength
    # of an inspection that did not complete.
    """
    try:
        return _model_is_ambiently_aliased(litellm, model) or _has_unsafe_openai_runtime_state(
            litellm
        )
    except Exception:
        # Deliberately broad, and deliberately not narrowed: the hazard is arbitrary
        # third-party code reached through ``getattr``, so the set of exception types is
        # open by construction. ``BaseException`` is NOT caught — a ``KeyboardInterrupt``
        # or ``SystemExit`` must still propagate.
        logger.warning("direct OpenAI ambient-state inspection failed; treating runtime as unsafe")
        return True


class OpenAIProviderPlugin(ProviderPluginBase[OpenAIPluginSettings]):
    custom_llm_provider = "openai"
    provider_display_name = "OpenAI"
    settings_cls = OpenAIPluginSettings

    def register_models(self) -> list[ModelEntry]:
        return [
            ModelEntry(model_name=model, litellm_params={"model": model})
            for model in self.settings.default_models
        ]

    def supports_api_key(self) -> bool:
        return True

    def supports_chat_streaming(self) -> bool:
        return False

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
        return status_code == 401

    def api_key_validator(self) -> ApiKeyValidator:
        return OpenAIApiKeyValidator(settings=self.settings)

    def chat_parameter_rules(
        self, *, model: str, auth_type: AuthMode | None = None
    ) -> tuple[ParameterProjectionRule, ...]:
        return openai_chat_parameter_rules(model=model, auth_type=auth_type)

    def chat_parameter_observations(
        self, *, model: str, auth_type: AuthMode | None = None
    ) -> tuple[ProviderParameterObservation, ...]:
        del model, auth_type
        return direct_parameter_observations(("max_tokens",), source=_OBSERVATION_SOURCE)

    def global_cache_projection(self, body: dict[str, Any]) -> dict[str, Any] | CacheBypass:
        # OME-884: delegated to ``global_cache`` so the PURE projection lives in a module
        # that holds nothing impure — see that module for the invariants.
        #
        # AIDEV-NOTE: the runtime-safety gate deliberately is NOT here. It lives in
        # ``participates_in_global_cache`` below, because this method's port contract is
        # that it reads the request body ALONE, and the registry-wide purity sweep
        # poisons the environment to prove it. Gating here would also be the wrong shape:
        # PARTICIPATION and KEY MATERIAL are separate decisions.
        return project_global_cache_request(body)

    def participates_in_global_cache(self, model: object = None) -> bool:
        # OME-884: the same fail-closed verdict dispatch uses, checked HERE too because
        # the cache stage runs before model resolution and before any credential is read
        # — so the dispatch-side 503 never gets a chance to refuse a replayed row.
        import litellm

        return not _has_unsafe_litellm_global_state(litellm, model)

    def cache_reference_from_cached_response(
        self, cached_response: Mapping[str, Any]
    ) -> CacheReference | None:
        # OME-884: direct OpenAI certifies NO historical accounting evidence for a
        # replayed row. It contributes no usage-accounting strategy at all, so there is
        # nothing truthful to attach — and an explicit ``None`` is not the same as not
        # implementing the hook: ``attach_hit_metadata`` reaches it through ``getattr``
        # inside a ``try``, so a missing attribute logs "cache-reference mapper failed"
        # on every hit, reporting a failure that never happened.
        del cached_response
        return None

    def prepare_chat_body(self, body: dict[str, Any]) -> dict[str, Any]:
        out = strip_dispatch_controls(body)
        # OME-884: SYNTAX, not membership. ``default_models`` is the bootstrap catalog
        # ``/v1/models`` publishes; it is not a dispatch allowlist. OpenAI stays the only
        # authority on whether a route-valid model exists and whether the selected
        # credential may use it, and it answers that on the MISS this request is on.
        #
        # INVARIANT: the SAME predicate the projection uses. The cache is read BEFORE
        # this runs, so a request the projection keyed must be one this method forwards
        # — otherwise a stored row could answer 200 for a request the gateway refuses.
        if not is_route_valid_model_id(out.get("model")):
            raise _invalid_model_error()
        out["api_base"] = OFFICIAL_API_BASE
        return out

    async def chat_completion(self, body: dict[str, Any]) -> Any:
        import litellm

        if _has_unsafe_litellm_global_state(litellm, body.get("model")):
            raise _unsafe_environment_error()

        dispatch_body = dict(body)
        api_key = dispatch_body.pop("api_key", None)
        if not isinstance(api_key, str) or not api_key:
            raise _unsafe_environment_error()
        # INVARIANT (OME-884): the SAME table the global-cache projection reports. Adding
        # a control here changes both the wire and the key, which is what keeps "the key
        # describes what dispatch sends" true by construction — and it is a mandatory
        # ``GLOBAL_CACHE_ADAPTER_REVISION`` bump, since older rows were keyed without it.
        dispatch_body.update(gateway_dispatch_controls())

        # Folded into GLOBAL_CACHE_ADAPTER_REVISION rather than into the key: an
        # ``Omit()`` sentinel is not JSON and the key builder refuses it. Suppressing
        # both headers is the explicit condition that licenses cross-account replay —
        # restoring either one is a mandatory revision bump.
        default_headers: dict[str, Any] = {
            "OpenAI-Organization": Omit(),
            "OpenAI-Project": Omit(),
        }
        http_client = _openai_http_client()
        try:
            client = AsyncOpenAI(
                api_key=api_key,
                base_url=OFFICIAL_API_BASE,
                max_retries=0,
                default_headers=default_headers,
                http_client=http_client,
            )
        except Exception:
            await http_client.aclose()
            raise
        dispatch_body["client"] = client
        try:
            response = cast("Any", await litellm.acompletion(**dispatch_body))
        finally:
            await client.close()

        payload = response.model_dump() if hasattr(response, "model_dump") else response
        return cast("Any", payload)


PLUGIN = OpenAIProviderPlugin()
