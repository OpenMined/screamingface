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
from typing import TYPE_CHECKING, Any, Protocol, cast

from aigateway.core.api_key_strategy import ApiKeyStrategy
from aigateway.core.api_key_validation import ApiKeyValidator
from aigateway.core.parameter_discovery import DiscoverySourceRef
from aigateway.core.parameter_projection import IncompatibleParametersError
from aigateway.core.plugin_base import (
    CredentialStrategy,
    ModelEntry,
    ProviderPluginBase,
)
from aigateway.core.standard_parameters import (
    direct_parameter_observations,
    tool_parameter_observations,
)

from .api_key_validation import OpenRouterApiKeyValidator
from .discovery import (
    LOCAL_SOURCE,
    MODEL_SOURCE,
    REVIEWED_ENDPOINT_OBSERVATIONS,
    SNAPSHOT_SOURCE_REVISION,
    discover_openrouter_snapshot,
)
from .dispatch_errors import (
    _embedded_error_exception,
    _invalid_model_error,
    _unsafe_litellm_state_error,
)
from .litellm_controls import (
    _has_unsafe_litellm_global_state,
    _strip_openrouter_litellm_controls,
)
from .parameters import openrouter_chat_parameter_rules, openrouter_chat_parameter_tools
from .provenance import converter_error_status, is_http200_body_error
from .response_errors import (
    _embedded_error_status as _embedded_error_status,
)
from .response_errors import (
    _find_embedded_error,
)
from .response_errors import (
    _top_level_error_is_meaningful as _top_level_error_is_meaningful,
)
from .settings import (
    GATEWAY_MODEL_PREFIX,
    OpenRouterPluginSettings,
    is_valid_upstream_model_id,
)

if TYPE_CHECKING:
    from aigateway.core.chat_parameters import (
        ParameterProjectionRule,
        ProviderDiscoverySnapshot,
        ProviderParameterObservation,
        ToolCapability,
    )
    from aigateway.core.credential_blob.store import CredentialBlobStore
    from aigateway.core.parameter_discovery import DiscoveryHttpClient, DiscoveryLimits
    from aigateway.core.profile_models import AuthMode


def _credential_service_for(profile_name: str) -> str:
    """Namespace the stored credential slot by provider + profile/connection."""
    return f"aigateway:openrouter:{profile_name}"


def _upstream_model_for_discovery(model: str) -> str | None:
    """The upstream catalog key for a gateway id, or None when there is none.

    ONE predicate shared by ``chat_discovery_source`` and
    ``discover_chat_parameter_snapshot``: the source declaration and the fetch must
    agree on exactly which ids are discoverable, or the runtime sees a provider that
    promised evidence and then reported NO ATTEMPT. It applies the SAME strip as
    ``prepare_chat_body``, so discovery and dispatch also agree on model identity.
    """
    if not model.startswith(GATEWAY_MODEL_PREFIX):
        return None
    upstream = model[len(GATEWAY_MODEL_PREFIX) :]
    return upstream if is_valid_upstream_model_id(upstream) else None


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

# OME-651: the gateway-owned strict-routing policy, forced on EVERY chat dispatch.
#
# WHY: OpenRouter defaults ``provider.require_parameters`` to false and documents
# that an endpoint which does not support a supplied parameter may still receive the
# request and ignore the unknown field. Without this, gateway acceptance, a published
# ``enabled`` status and a successful projection can all hold while the parameter has
# no effect — HTTP 200, silently wrong. Per-model evidence cannot close the gap: one
# OpenRouter model is served by several endpoints with different parameter support,
# so only the provider knows which one can honor this request.
#
# INVARIANT: a successful OpenRouter completion means the selected endpoint declared
# support for EVERY supplied parameter. The alternative is an explicit provider
# refusal, never a silent discard.
#
# AIDEV-NOTE: this is policy, NOT a projected caller parameter — which is why it sits
# beside ``api_base``/``extra_headers`` rather than in ``extra_body`` (the projection's
# native-target output). The two are equivalent on the wire: litellm folds a non-OpenAI
# dispatch kwarg into ``extra_body``, then the OpenRouter transform flattens
# ``extra_body`` onto the top level. That double indirection is a litellm behaviour, not
# a promise, so ``test_openrouter_strict_routing`` pins the FINAL wire JSON against the
# installed version — if it ever changes, strictness would vanish silently.
_STRICT_ROUTING_PROVIDER = {"require_parameters": True}

# --- server-side web search: caller intent -> the provider's native envelope ------------------
#
# The caller says `web_search: true`. OpenRouter's spelling is `plugins: [{"id": "web", ...}]`,
# an extensibility envelope that stays REFUSED as a caller path (OME-646) — so the translation
# happens HERE, in the same hook and by the same rule as `provider`: the gateway ASSIGNS the
# native field, the caller can never reach it.
WEB_SEARCH_PARAM = "web_search"
WEB_SEARCH_EXCLUDED_DOMAINS_PARAM = "web_search_excluded_domains"

# Gateway-owned plugin options. `native` routes to each provider's own search engine — one of
# exactly five OpenRouter accepts (native|exa|firecrawl|parallel|perplexity); `auto` is NOT
# among them, despite being valid on the inert `openrouter:web_search` tools surface.
_WEB_SEARCH_POLICY: dict[str, object] = {"id": "web", "engine": "native"}

EXCLUDE_DOMAINS_KEY = "exclude_domains"
"""OpenRouter's wire spelling for the blocklist. NOT `excluded_domains`.

AIDEV-NOTE: this was `excluded_domains` from `26858fc1` until 2026-07-31, and it silently did
NOTHING for that whole time. OpenRouter does not validate the `plugins` envelope — a deliberately
invented key returns HTTP 200 exactly like a real one (measured) — so the wrong spelling produced
a normal answer, a normal bill, and zero exclusion. Every benchmark candidate could reach the
rubric it was being graded against, which INFLATES scores and therefore never looks like a bug.

MEASURED 2026-07-31, live, against `google/gemini-3-flash-preview` (exa) and `openai/gpt-5.5`
(native), counting citations from hosts we asked to exclude:

    exclude_domains  = every cited host  ->  0 blocked-host citations   (both engines)
    excluded_domains = every cited host  ->  unchanged from baseline    (both engines)
    exclude_domains  = one host          ->  that host alone disappears (rules out search noise)

INVARIANT: a status code can never verify this key. Assert on an EFFECT — annotations, cost, or a
changed answer. `test_the_wire_key_is_openrouters_spelling` pins the name so a rename fails loudly
instead of quietly restoring the bug. The documented keys are `engine`, `max_results`,
`search_prompt`, `include_domains` and `exclude_domains`; path prefixes and wildcards are
supported values (`openai.com/blog`, `*.substack.com`).
"""


class _WebSearchSettings(Protocol):
    """The ONE setting `_apply_web_search` reads.

    A Protocol rather than `Any`: this function assembles a security-relevant blocklist, and an
    untyped parameter means the type checker cannot tell a renamed setting from a missing one —
    the failure mode being an empty deployment list, i.e. a guard that silently does nothing.
    Structural, so the plugin's real settings object and a test's minimal stub both satisfy it
    without either importing the other.
    """

    web_search_excluded_domains: list[str]


def _apply_web_search(body: dict[str, Any], settings: _WebSearchSettings) -> None:
    """Translate the caller's `web_search` intent into OpenRouter's `plugins` envelope.

    INVARIANT: both caller-facing keys are POPPED. Neither is an OpenRouter field, and leaving
    one on the body would reach the wire as an unknown parameter.

    INVARIANT: exclusions are a UNION of the deployment's own list and the caller's, so a caller
    can only ever TIGHTEN the guard. The motivating case is a benchmark candidate that must not
    retrieve the rubric it is graded against — a blocklist a caller could shorten is not one.
    """
    wanted = body.pop(WEB_SEARCH_PARAM, None)
    caller_excluded = body.pop(WEB_SEARCH_EXCLUDED_DOMAINS_PARAM, None) or []
    if wanted is not True:
        return
    excluded = sorted({*settings.web_search_excluded_domains, *caller_excluded})
    plugin = dict(_WEB_SEARCH_POLICY)
    if excluded:
        plugin[EXCLUDE_DOMAINS_KEY] = excluded
    # Assignment, never a merge — as with `provider`. A `plugins` that somehow survived the
    # classifier must not be extended by this, only replaced.
    body["plugins"] = [plugin]


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

    def api_key_validator(self) -> ApiKeyValidator | None:
        if not self.settings.enabled:
            return None
        return OpenRouterApiKeyValidator(settings=self.settings)

    def should_mark_profile_error_on_dispatch_status(self, status_code: int) -> bool:
        # D9: only 401 proves the stored key is bad. 402 (credits), 403
        # (policy), 408/429/5xx (transient) must not invalidate a valid key.
        return status_code == 401

    def chat_parameter_rules(
        self, *, model: str, auth_type: AuthMode | None = None
    ) -> tuple[ParameterProjectionRule, ...]:
        # OME-479: one provider-local source drives summary, detail, and
        # fail-closed dispatch. Adding a parameter is a change here, never in core.
        return openrouter_chat_parameter_rules(model=model, auth_type=auth_type)

    def validate_chat_parameter_combination(
        self,
        body: Mapping[str, Any],
        *,
        model: str,
        auth_mode: AuthMode,
    ) -> None:
        del model, auth_mode
        if "top_logprobs" in body and body.get("logprobs") is not True:
            raise IncompatibleParametersError(
                ("logprobs", "top_logprobs"),
                reason="top_logprobs_requires_logprobs_true",
            )

    def chat_parameter_tools(
        self, *, model: str, auth_type: AuthMode | None = None
    ) -> tuple[ToolCapability, ...]:
        # OME-583: OpenRouter is OpenAI-compatible; the installed litellm openrouter
        # transform forwards OpenAI tools (§9), so it advertises the `function` type.
        return openrouter_chat_parameter_tools(model=model, auth_type=auth_type)

    def chat_parameter_observations(
        self, *, model: str, auth_type: AuthMode | None = None
    ) -> tuple[ProviderParameterObservation, ...]:
        # OME-479 §5.3: labelled-local endpoint evidence (NO network) so the detail
        # contract shows every accepted field with its gateway status — an unruled
        # field (e.g. top_p) stays visible-but-DISABLED (projection_not_implemented),
        # while a ruled+observed field (temperature, provider_params.top_k) is
        # ENABLED and carries its provenance. The live per-model catalog overlays
        # this via discover_chat_parameter_snapshot when request-path discovery is
        # wired; endpoint-level evidence is model-independent, so it does not vary
        # by model here.
        # OME-583: tools + tool_choice are ALSO ruled → ENABLED, evidenced here (same
        # labelled-local source) so every enabled tool path is fully backed (§4.4).
        # OME-584: response_format is likewise ruled → ENABLED, evidenced here.
        # OME-585: seed is already evidenced by the sampling constant; n (a non-sampling
        # control) is evidenced here alongside response_format — both ruled → ENABLED.
        # INVARIANT: an observation NEVER enables a parameter — only a rule does.
        return (
            REVIEWED_ENDPOINT_OBSERVATIONS
            + tool_parameter_observations(
                openrouter_chat_parameter_tools(model=model, auth_type=auth_type),
                source=LOCAL_SOURCE,
            )
            + direct_parameter_observations(
                (
                    "response_format",
                    "n",
                    "logprobs",
                    "top_logprobs",
                    "web_search",
                    "web_search_excluded_domains",
                ),
                source=LOCAL_SOURCE,
            )
        )

    def chat_discovery_source(
        self, *, model: str, auth_type: AuthMode | None = None
    ) -> DiscoverySourceRef | None:
        # OME-632: the catalog is public and auth-INDEPENDENT — OpenRouter publishes
        # one row per model whichever credential dispatch will use — so the resolved
        # mode is accepted for port conformance and deliberately ignored.
        # OME-629: declare the public catalog BEFORE any fetch, so the observation
        # cache can judge a stored entry's trustworthiness without paying for a
        # round trip. The revision names the reading as well as the source.
        # INVARIANT: the SAME predicate gates both hooks — a model this provider
        # cannot dispatch has nothing to discover. Owning it here (rather than only
        # in the fetch) makes "declared a source, then reported NOT ATTEMPTED"
        # structurally unreachable, which is the one inconsistency the runtime
        # cannot distinguish from a real outage.
        # AIDEV-NOTE (OME-647): ``source`` is the provider's CACHE-KEY label, not a
        # published claim about which document an observation came from — that
        # provenance rides on each observation. The snapshot now draws on the
        # catalog AND the OpenAPI document, and the REVISION names the pair.
        if _upstream_model_for_discovery(model) is None:
            return None
        return DiscoverySourceRef(source=MODEL_SOURCE, revision=SNAPSHOT_SOURCE_REVISION)

    async def discover_chat_parameter_snapshot(
        self,
        *,
        model: str,
        client: DiscoveryHttpClient,
        limits: DiscoveryLimits | None = None,
        auth_type: AuthMode | None = None,
    ) -> ProviderDiscoverySnapshot | None:
        # OME-479 §5.1: the DYNAMIC source. Strip the gateway prefix to the
        # upstream id the public catalog is keyed by — the SAME rule as
        # prepare_chat_body, so discovery and dispatch agree on identity. A value
        # that is not a valid gateway id is not dispatchable, so there is nothing
        # to discover: return None WITHOUT opening a connection — NOT ATTEMPTED,
        # which is a different claim from "attempted and failed".
        # INVARIANT: never enables a parameter (only a rule does); off the chat
        # dispatch path; a sanitized DiscoveryError from the fetch PROPAGATES so
        # the cache can degrade honestly rather than store a failure as fresh.
        upstream = _upstream_model_for_discovery(model)
        if upstream is None:
            return None
        return await discover_openrouter_snapshot(upstream, client=client, limits=limits)

    def strip_provider_dispatch_controls(self, body: dict[str, Any]) -> dict[str, Any]:
        # OME-479: neutralize LiteLLM orchestration selectors BEFORE the
        # fail-closed classifier, so they are structurally authorized (§4.5 tier a)
        # rather than 400-rejected as unknown params. prepare_chat_body repeats
        # this strip (idempotent) as defense in depth.
        return _strip_openrouter_litellm_controls(body)

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
        # OME-651: assignment, never a merge. The classifier already refuses a caller
        # `provider` as unknown, so nothing should be here — but the two layers are
        # deliberately independent, and a merge would let a `require_parameters: false`
        # that ever slipped through survive. A fresh dict per request keeps one caller
        # from mutating the policy the next one gets.
        out["provider"] = dict(_STRICT_ROUTING_PROVIDER)
        _apply_web_search(out, self.settings)
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
