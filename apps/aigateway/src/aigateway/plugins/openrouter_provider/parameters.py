"""OpenRouter chat-parameter rules (OME-479 §6.1) — currently-proven set only.

INVARIANT: every rule here is backed by a capture/boundary test proving the
field reaches OpenRouter dispatch, so enabling it is earned, not speculative
(plan §12). INVARIANT: every rule here also carries a validation schema — an
enabled ordinary parameter that cannot be validated is not enabled at all
(OME-646). Standard sampling fields are ``direct``; ``top_k`` — not a standard
OpenAI param for OpenRouter — is the P0 promotion, projected through
``extra_body`` where the installed litellm transform carries it onto the wire
(proven in tests).
"""

from __future__ import annotations

from aigateway.core.chat_parameters import (
    ParameterProjectionRule,
    ParameterSchema,
    ToolCapability,
)
from aigateway.core.profile_models import AuthMode
from aigateway.core.standard_parameters import (
    LOGPROBS_SCHEMA,
    MAX_TOKENS_SCHEMA,
    N_SCHEMA,
    PENALTY_SCHEMA,
    RESPONSE_FORMAT_SCHEMA,
    SEED_SCHEMA,
    STOP_SCHEMA,
    TEMPERATURE_SCHEMA,
    TOP_LOGPROBS_SCHEMA,
    TOP_P_SCHEMA,
    WEB_SEARCH_EXCLUDED_DOMAINS_SCHEMA,
    WEB_SEARCH_SCHEMA,
    direct_rule,
    function_calling_rules,
    provider_native_rule,
)

# OpenRouter is API-key only (no OAuth); its auth-mode intersection is a single
# mode, so every proven rule is enabled under it.
_AUTH: tuple[AuthMode, ...] = ("api_key",)
# Bump when a projection's semantics change; folds into the contract digests.
_REVISION = "openrouter-2026-07"

# WHY: OpenRouter documents ``top_k`` as an integer "0 or above" (0 disables top-k
# sampling) and the installed litellm transform forwards 0 verbatim (§9 probe), so
# OpenRouter binds its OWN minimum=0 schema. Do NOT widen the shared ``TOP_K_SCHEMA``
# (minimum=1) — Anthropic and Gemini still bind it and their top-k lower bound is 1.
OPENROUTER_TOP_K_SCHEMA = ParameterSchema(type="integer", minimum=0)

# OME-583: OpenRouter is OpenAI-compatible; the INSTALLED litellm openrouter transform
# forwards tools[] and tool_choice onto the wire (§9), so function calling is enabled
# WITH tool_choice.
_TOOL_CAPABILITIES: tuple[ToolCapability, ...] = (
    ToolCapability(tool_type="function", provider_support="supported", gateway_status="enabled"),
    # AIDEV-NOTE: `openrouter:web_search` / `openrouter:web_fetch` are deliberately ABSENT.
    # OpenRouter documents them as a server-tool surface and ACCEPTS them with HTTP 200 — but
    # measured against the live API on 2026-07-31 they are silently INERT: zero `annotations`,
    # no web-search line in `cost_details`, and an answer written from the model's training
    # cutoff. Server-side web search is reached through the `web_search` rule below, which
    # `plugin.prepare_chat_body` translates into the field that actually retrieves. Enabling a
    # tool type the provider ignores would authorize a request that costs normal money and never
    # searches — the worst failure shape, because it returns 200 and reads like a real answer.
)

# --- server-side web search --------------------------------------------------
# OpenRouter retrieves through `plugins: [{"id": "web", ...}]`, and `plugins` stays REFUSED as a
# caller path (OME-646, pinned by `test_openrouter_security`). That is not an obstacle worked
# around here — it is correct, and the reason is worth stating: `plugins` is an extensibility
# ENVELOPE. Carrying arbitrary provider extensions is its entire purpose, so no schema can bound
# it without defeating it, and a rule enabling it forwards nested JSON verbatim.
#
# The caller instead says `web_search: true` — bounded completely, because it is a boolean — and
# `plugin.prepare_chat_body` ASSIGNS the `plugins` payload from gateway-owned policy, the same
# two-layer shape `provider` already uses: the classifier refuses the native field, the provider
# sets it. The caller can never reach the envelope.

_RULES: tuple[ParameterProjectionRule, ...] = (
    direct_rule(
        "temperature", auth_modes=_AUTH, schema=TEMPERATURE_SCHEMA, projection_revision=_REVISION
    ),
    # OME-479 (closure Unit 2): the P0 promotion of a genuinely observed-but-unruled
    # field. `top_p` was reported by this provider's own evidence (openrouter:static,
    # supported) while no rule authorized it, so the gateway published it as
    # visible-but-disabled and rejected it at dispatch. Enabling it is exactly this one
    # provider-local rule — no shared core/route edit — because the installed litellm
    # openrouter transform forwards the value VERBATIM onto the wire, including the 0.0
    # and 1.0 boundaries (§9 probe against litellm 1.87.0), and OpenRouter's accepted
    # range IS the standard OpenAI [0, 1], so the SHARED schema binds unchanged.
    # Contrast OPENROUTER_TOP_K_SCHEMA below, which exists only because OpenRouter's
    # top_k floor genuinely differs from the shared one.
    direct_rule("top_p", auth_modes=_AUTH, schema=TOP_P_SCHEMA, projection_revision=_REVISION),
    direct_rule(
        "max_tokens", auth_modes=_AUTH, schema=MAX_TOKENS_SCHEMA, projection_revision=_REVISION
    ),
    # direct: standard stop (string | array[string]); the installed litellm OpenRouter
    # path forwards it as the OpenAI-native `stop` (proven in test_openrouter_dispatch).
    direct_rule("stop", auth_modes=_AUTH, schema=STOP_SCHEMA, projection_revision=_REVISION),
    # OME-584: structured output. The installed litellm OpenRouter transform forwards
    # response_format VERBATIM (§9 probe: both json_object and json_schema reach the wire
    # unchanged), so it is a direct passthrough gated by the shared response-format schema.
    direct_rule(
        "response_format",
        auth_modes=_AUTH,
        schema=RESPONSE_FORMAT_SCHEMA,
        projection_revision=_REVISION,
    ),
    # OME-585: seed + n sampling controls. The installed litellm OpenRouter transform
    # forwards both VERBATIM (§9 probe), so each is a direct passthrough gated by its
    # bounded integer schema (seed: any int; n: >= 1).
    direct_rule("seed", auth_modes=_AUTH, schema=SEED_SCHEMA, projection_revision=_REVISION),
    direct_rule("n", auth_modes=_AUTH, schema=N_SCHEMA, projection_revision=_REVISION),
    # OME-586: frequency_penalty + presence_penalty repetition controls. The installed
    # litellm OpenRouter transform forwards both VERBATIM (§9 probe), so each is a direct
    # passthrough gated by the shared [-2, 2] penalty schema.
    direct_rule(
        "frequency_penalty", auth_modes=_AUTH, schema=PENALTY_SCHEMA, projection_revision=_REVISION
    ),
    direct_rule(
        "presence_penalty", auth_modes=_AUTH, schema=PENALTY_SCHEMA, projection_revision=_REVISION
    ),
    # OME-595: logprobs + top_logprobs output-introspection controls. The installed litellm
    # OpenRouter transform forwards both VERBATIM (§9 probe), so each is a direct passthrough:
    # logprobs gated as a boolean, top_logprobs as a bounded integer (0..20).
    direct_rule(
        "logprobs", auth_modes=_AUTH, schema=LOGPROBS_SCHEMA, projection_revision=_REVISION
    ),
    direct_rule(
        "top_logprobs", auth_modes=_AUTH, schema=TOP_LOGPROBS_SCHEMA, projection_revision=_REVISION
    ),
    # AIDEV-NOTE (OME-646): `provider`, `plugins`, `route` and `models` were enabled here
    # by schema-less rules. `_accept` validates only when `rule.parameter_schema is not
    # None`, so each authorized a path and forwarded arbitrary nested JSON verbatim —
    # while §Definition of done requires every enabled ordinary parameter to declare a
    # gateway-owned validation schema, and Excluded scope names fallbacks and arbitrary
    # provider controls outright. `route: "fallback"` and `models: [...]` are OpenRouter's
    # server-side fallback controls; `provider` carries `allow_fallbacks`. Both readings
    # forbid the rules, so they are gone and the fields now fail closed with a named 400.
    # Re-enabling any of them needs an approved bounded schema per field — a permissive
    # object/array union added just to satisfy the conformance gate is NOT that.
    provider_native_rule(
        "provider_params.top_k",
        provider_target="extra_body.top_k",
        auth_modes=_AUTH,
        schema=OPENROUTER_TOP_K_SCHEMA,
        projection_revision=_REVISION,
    ),
    # OME-583: tools + tool_choice (OpenAI-native, §9 proof).
    *function_calling_rules(_TOOL_CAPABILITIES, auth_modes=_AUTH, projection_revision=_REVISION),
    # Server-side web search — the caller-facing half. `direct` is the ADDRESSING kind, not the
    # wire shape: `prepare_chat_body` consumes both fields and emits `plugins` in their place,
    # so neither name reaches OpenRouter. Verified live 2026-07-31 (litellm 1.87.0) that the
    # emitted `plugins` retrieves: same prompt, with it a current cited answer, without it the
    # model's training cutoff.
    direct_rule(
        "web_search", auth_modes=_AUTH, schema=WEB_SEARCH_SCHEMA, projection_revision=_REVISION
    ),
    direct_rule(
        "web_search_excluded_domains",
        auth_modes=_AUTH,
        schema=WEB_SEARCH_EXCLUDED_DOMAINS_SCHEMA,
        projection_revision=_REVISION,
    ),
)


def openrouter_chat_parameter_rules(
    *, model: str, auth_type: AuthMode | None = None
) -> tuple[ParameterProjectionRule, ...]:
    """The proven rule set is identical for every OpenRouter model; auth-mode
    filtering is applied by the core classifier/contract, not here."""
    return _RULES


def openrouter_chat_parameter_tools(
    *, model: str, auth_type: AuthMode | None = None
) -> tuple[ToolCapability, ...]:
    # OME-583: the accepted tools[].type discriminator(s); drives supported_tools +
    # the detail contract's tools section.
    return _TOOL_CAPABILITIES
