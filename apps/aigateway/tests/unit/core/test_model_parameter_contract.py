"""Phase 3 (OME-479): detailed /v1/model-parameters document composition.

RED-first for the PURE application-layer composer that overlays a plugin's OWN
observations + gateway rules + tools + transport into the locked v1 detailed
document, and derives the opaque, non-secret ``contract_id`` / ``context.revision``
digests. No route, no network, no clock — the composer is deterministic given its
inputs, so ``freshness`` and the opaque ``context_identity`` token are passed IN.
"""

from __future__ import annotations

from typing import Any

from aigateway.core.chat_parameters import (
    ParameterProjectionRule,
    ParameterSchema,
    ProviderParameterObservation,
    ToolCapability,
    TransportCapability,
    inline_supported_parameters,
    normalize_rules,
)
from aigateway.core.model_parameter_contract import (
    SCHEMA_VERSION,
    build_model_parameter_document,
    upstream_model_id,
)
from aigateway.core.profile_models import AuthType

_LOCAL_FRESHNESS: dict[str, Any] = {"stale": False, "degraded": False}


def _rule(
    request_path: str,
    *,
    auth_modes: tuple[AuthType, ...] = ("api_key",),
    schema: ParameterSchema | None = None,
) -> ParameterProjectionRule:
    return ParameterProjectionRule(
        request_path=request_path,
        applicable_auth_modes=auth_modes,
        projection_kind="direct",
        cache_behavior="bypass",
        projection_revision="r1",
        schema=schema,
    )


def _doc(
    *,
    canonical_id: str = "openrouter/google/gemini-3.6-flash",
    gateway_provider: str = "openrouter",
    auth_mode: AuthType = "api_key",
    scope: str = "account_profile",
    context_identity: str = "acct:a1|prof:p1:authenticated:-",
    rules: tuple[ParameterProjectionRule, ...] = (),
    observations: tuple[ProviderParameterObservation, ...] = (),
    tools: tuple[ToolCapability, ...] = (),
    transport: tuple[TransportCapability, ...] = (),
) -> dict[str, Any]:
    return build_model_parameter_document(
        canonical_id=canonical_id,
        gateway_provider=gateway_provider,
        auth_mode=auth_mode,
        scope=scope,
        context_identity=context_identity,
        rules=rules,
        observations=observations,
        tools=tools,
        transport=transport,
        freshness=dict(_LOCAL_FRESHNESS),
    )


# --- upstream id -------------------------------------------------------------


def test_upstream_id_strips_only_the_gateway_prefix() -> None:
    # the model author id is the canonical id minus its owning-provider segment,
    # NEVER derived from a LiteLLM transport prefix (plan 4.1).
    assert upstream_model_id("openrouter/google/gemini-3.6-flash") == "google/gemini-3.6-flash"
    assert upstream_model_id("ollama/llama3:8b") == "llama3:8b"
    assert upstream_model_id("anthropic/claude-opus-4-8") == "claude-opus-4-8"


# --- locked v1 envelope ------------------------------------------------------


def test_document_emits_locked_v1_envelope() -> None:
    doc = _doc()
    assert doc["schema_version"] == SCHEMA_VERSION == 1
    assert doc["contract_id"].startswith("pc_")
    assert doc["model"] == {
        "id": "openrouter/google/gemini-3.6-flash",
        "gateway_provider": "openrouter",
        "upstream_id": "google/gemini-3.6-flash",
    }
    assert doc["context"]["scope"] == "account_profile"
    assert doc["context"]["auth_mode"] == "api_key"
    assert doc["context"]["revision"].startswith("ctx_")
    assert doc["freshness"] == {"stale": False, "degraded": False}
    for section in ("parameters", "tools", "transport"):
        assert isinstance(doc[section], dict)


def test_parameters_are_keyed_by_path_and_use_the_detail_shape() -> None:
    doc = _doc(
        rules=(_rule("temperature", schema=ParameterSchema(type="number", minimum=0, maximum=2)),),
        observations=(
            ProviderParameterObservation(
                request_path="temperature", support="supported", source="labelled_static"
            ),
            ProviderParameterObservation(
                request_path="provider_params.new_option",
                support="supported",
                source="labelled_static",
            ),
        ),
    )
    params = doc["parameters"]
    assert params["temperature"]["request_path"] == "temperature"
    assert params["temperature"]["schema"] == {"type": "number", "minimum": 0, "maximum": 2}
    assert params["temperature"]["gateway"] == {
        "status": "enabled",
        "projection": "direct",
        "cache_behavior": "bypass",
    }
    # observed-but-unruled field is VISIBLE but never dispatchable.
    disabled = params["provider_params.new_option"]
    assert disabled["gateway"]["status"] == "disabled"
    assert disabled["gateway"]["reason"] == "projection_not_implemented"


def test_tools_and_transport_serialize_with_status() -> None:
    doc = _doc(
        tools=(
            ToolCapability(
                tool_type="function", provider_support="supported", gateway_status="enabled"
            ),
            ToolCapability(
                tool_type="web_search", provider_support="supported", gateway_status="disabled"
            ),
        ),
        transport=(
            TransportCapability(
                name="stream",
                provider_support="supported",
                gateway_status="disabled",
                reason="gateway_transport_not_implemented",
            ),
        ),
    )
    assert doc["tools"]["function"] == {
        "provider_support": "supported",
        "gateway_status": "enabled",
    }
    # detail reports every tool with its status (unlike the enabled-only summary).
    assert doc["tools"]["web_search"]["gateway_status"] == "disabled"
    assert doc["transport"]["stream"] == {
        "provider_support": "supported",
        "gateway_status": "disabled",
        "reason": "gateway_transport_not_implemented",
    }


# --- opaque, deterministic, revision-sensitive digests -----------------------


def test_digests_are_deterministic_for_identical_inputs() -> None:
    a = _doc(rules=(_rule("temperature"),))
    b = _doc(rules=(_rule("temperature"),))
    assert a["contract_id"] == b["contract_id"]
    assert a["context"]["revision"] == b["context"]["revision"]


def test_both_digests_change_when_any_relevant_input_changes() -> None:
    base = _doc(rules=(_rule("temperature"),))
    base_ids = (base["contract_id"], base["context"]["revision"])

    mutations = [
        _doc(canonical_id="openrouter/x/other", rules=(_rule("temperature"),)),  # model
        _doc(auth_mode="oauth", rules=(_rule("temperature", auth_modes=("oauth",)),)),  # auth mode
        _doc(  # context identity (selected profile/connection generation)
            context_identity="acct:a1|prof:p1:authenticated:CHANGED",
            rules=(_rule("temperature"),),
        ),
        _doc(rules=(_rule("temperature"), _rule("max_tokens"))),  # gateway projection revision
        _doc(  # provider evidence revision
            rules=(_rule("temperature"),),
            observations=(
                ProviderParameterObservation(
                    request_path="temperature", support="supported", source="labelled_static"
                ),
            ),
        ),
    ]
    for mutated in mutations:
        assert (mutated["contract_id"], mutated["context"]["revision"]) != base_ids
    # domain separation: the two ids are never equal to each other.
    assert base["contract_id"] != base["context"]["revision"]


def test_digests_never_expose_their_secret_or_identity_inputs() -> None:
    secretish_identity = "acct:11111111-2222-3333-4444-555555555555|prof:super-secret-token"
    doc = _doc(context_identity=secretish_identity, rules=(_rule("temperature"),))
    blob = doc["contract_id"] + doc["context"]["revision"]
    assert "555555555555" not in blob
    assert "super-secret-token" not in blob
    assert secretish_identity not in blob


# --- single-source consistency (summary ⊆ enabled detail) --------------------


def test_inline_summary_entries_are_enabled_in_the_document() -> None:
    # The cross-projection invariant, at the document level: every path the
    # profile-independent summary advertises is ENABLED in the applicable
    # detailed contract, because BOTH read the same rule source.
    rules = normalize_rules(
        (
            _rule("temperature", auth_modes=("api_key", "oauth")),
            _rule("max_tokens", auth_modes=("api_key", "oauth")),
        )
    )
    summary = inline_supported_parameters(rules, available_auth_modes=("api_key", "oauth"))
    assert summary  # guard: the fixture actually advertises something
    doc = _doc(auth_mode="api_key", rules=rules)
    for path in summary:
        assert doc["parameters"][path]["gateway"]["status"] == "enabled"


def test_contract_id_changes_when_only_a_rule_schema_changes() -> None:
    # LIVE facet (OME-579): the contract identity must move when a rule's
    # VALIDATION SCHEMA changes and nothing else — otherwise narrowing a bound
    # (e.g. Anthropic temperature maximum 2 -> 1) leaves a cached contract
    # byte-identical and stale, advertising the wrong range to clients.
    wide = _doc(
        rules=(_rule("temperature", schema=ParameterSchema(type="number", minimum=0, maximum=2)),)
    )
    narrow = _doc(
        rules=(_rule("temperature", schema=ParameterSchema(type="number", minimum=0, maximum=1)),)
    )
    assert wide["contract_id"] != narrow["contract_id"]
    assert wide["context"]["revision"] != narrow["context"]["revision"]
