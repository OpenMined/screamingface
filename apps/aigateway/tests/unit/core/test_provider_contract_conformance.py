"""Phase 10 (OME-479 §Phase 10): provider-AGNOSTIC contract conformance.

FEATURE: the effective-parameter contract's cross-provider guarantees. Instead of
per-provider assertions, this suite DISCOVERS the real registry (`load_plugins`) and
iterates EVERY registered model, so the algebra's invariants are locked for every
current AND future provider — a new plugin that violates them fails here, not in prod.

STORY: as a gateway maintainer adding a provider, I get an automatic guarantee that my
plugin's models route to me, that my summary never overclaims an auth-specific field,
that a locked/transport field cannot be turned on by an ordinary rule, and that every
param I enable is fully evidenced — without editing any central inventory.

INVARIANT (SOLID/hexagonal — plan §12): this file contains NO provider-name literal and
NO hardcoded model/provider inventory. The registry is the single source of truth; the
core composes, the plugins select. (The ONE legitimately-named regression guard — "Codex
GPT-family ids never surface under an `openai` namespace" — lives in the codex-owned test
file, where naming codex is domain-correct, not inventory.)
INVARIANT (§4.4): a RULE is the only thing that enables a parameter; an observation only
adds visibility. Every enabled entry here is proven rule-backed AND fully evidenced.
"""

from __future__ import annotations

from typing import Any

from aigateway.core.chat_parameters import normalize_rules
from aigateway.core.loader import load_plugins
from aigateway.core.model_capabilities import canonical_model_id, model_row
from aigateway.core.model_parameter_contract import build_model_parameter_document
from aigateway.core.parameter_projection import GATEWAY_OWNED_FIELDS
from aigateway.core.profile_models import AuthType
from aigateway.core.registry import ProviderRegistry


def _load_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    load_plugins(registry)
    return registry


# Built once from the SAME discovery the app uses at startup; no names baked in.
_REGISTRY = _load_registry()

# The locked v1 /v1/models row shape (plan §4.1) — asserted structurally, not by value.
_LOCKED_ROW_KEYS = frozenset(
    {
        "id",
        "object",
        "owned_by",
        "supported_parameters",
        "supported_tools",
        "unsupported_parameter_behavior",
        "parameter_contract_url",
    }
)


def _iter_models():
    for plugin in _REGISTRY.all():
        for entry in plugin.register_models():
            canonical = canonical_model_id(
                custom_llm_provider=plugin.custom_llm_provider, model_name=entry.model_name
            )
            yield plugin, entry, canonical


def _document(plugin: Any, canonical: str, auth_mode: AuthType) -> dict[str, Any]:
    # Mirrors routes/model_parameters.py: the plugin's own hooks + the core composer.
    return build_model_parameter_document(
        canonical_id=canonical,
        gateway_provider=plugin.custom_llm_provider,
        auth_mode=auth_mode,
        scope="account_profile",
        context_identity="acct:conformance|prof:1",
        rules=plugin.chat_parameter_rules(model=canonical, auth_type=auth_mode),
        observations=plugin.chat_parameter_observations(model=canonical, auth_type=auth_mode),
        tools=plugin.chat_parameter_tools(model=canonical, auth_type=auth_mode),
        transport=plugin.chat_transport_capabilities(model=canonical, auth_type=auth_mode),
        freshness={"stale": False, "degraded": False},
    )


def test_registry_discovery_is_non_vacuous() -> None:
    # Guard: if load_plugins silently found nothing, every other test below would pass
    # vacuously. Assert a floor WITHOUT naming providers (a count is not an inventory).
    assert len(_REGISTRY.all()) >= 1
    assert sum(len(plugin.register_models()) for plugin in _REGISTRY.all()) >= 1


def test_every_model_id_routes_to_its_owning_plugin() -> None:
    # Routing invariant (plan §4.1): a canonical id's first path segment is the owning
    # plugin's unique registry key, so /v1/chat/completions + /v1/model-parameters both
    # resolve the SAME plugin. This subsumes "Codex never resolves to OpenAI": a codex id
    # whose prefix routed to an `openai` plugin would fail here — no provider names needed.
    for plugin, _entry, canonical in _iter_models():
        prefix = canonical.split("/", 1)[0]
        assert _REGISTRY.get(prefix) is plugin, canonical


def test_every_model_row_has_the_locked_summary_shape() -> None:
    for plugin, entry, canonical in _iter_models():
        row = model_row(plugin, entry)
        assert _LOCKED_ROW_KEYS <= set(row), canonical
        assert row["id"] == canonical
        assert row["object"] == "model"
        assert row["owned_by"] == plugin.custom_llm_provider
        # fail-closed literal: unknown/disabled params never silently pass.
        assert row["unsupported_parameter_behavior"] == "reject", canonical
        assert isinstance(row["supported_parameters"], list)
        assert isinstance(row["supported_tools"], list)
        assert row["parameter_contract_url"].startswith("/v1/model-parameters?model="), canonical


def test_no_rule_enables_a_gateway_owned_or_transport_field() -> None:
    # A locked field (model/messages/stream/extra_headers/metadata/timeout) is authorized
    # STRUCTURALLY, never by a rule; and a transport control (surfaced via
    # chat_transport_capabilities) is never an ordinary parameter rule. Check across the
    # summary view (None) AND every real auth mode — neither request_path nor target,
    # nor any transport name, may collide with a rule path.
    for plugin, _entry, canonical in _iter_models():
        for mode in (None, *plugin.available_auth_modes()):
            rules = plugin.chat_parameter_rules(model=canonical, auth_type=mode)
            rule_paths = {rule.request_path for rule in rules}
            for rule in rules:
                assert rule.request_path not in GATEWAY_OWNED_FIELDS, (canonical, rule.request_path)
                assert rule.target not in GATEWAY_OWNED_FIELDS, (canonical, rule.target)
            transport = plugin.chat_transport_capabilities(model=canonical, auth_type=mode)
            transport_names = {cap.name for cap in transport}
            assert transport_names & rule_paths == set(), canonical


def test_summary_is_the_independent_cross_auth_mode_intersection() -> None:
    # The conservative summary must equal the intersection of per-auth-mode enabled paths,
    # recomputed HERE from per-mode rule filtering (NOT by calling
    # inline_supported_parameters — that would test the impl against itself). A field that
    # only one auth mode can prove must be absent, so /v1/models never overclaims.
    for plugin, entry, canonical in _iter_models():
        rules_none = normalize_rules(plugin.chat_parameter_rules(model=canonical, auth_type=None))
        all_paths = {rule.request_path for rule in rules_none}
        modes = plugin.available_auth_modes()
        if modes:
            expected = set(all_paths)
            for mode in modes:
                mode_rules = plugin.chat_parameter_rules(model=canonical, auth_type=mode)
                enabled = {r.request_path for r in mode_rules if mode in r.applicable_auth_modes}
                expected &= enabled
        else:
            # No auth mode can prove any field → the conservative summary is EMPTY
            # (OME-580). "∅ ⊆ anything" is vacuously true, so advertising every ruled
            # path here would be the exact opposite of conservative.
            expected = set()
        assert set(model_row(plugin, entry)["supported_parameters"]) == expected, canonical


def test_every_enabled_param_is_fully_evidenced() -> None:
    # "Enabling is earned" (§6.2): under each REAL auth mode, an enabled parameter must be
    # backed by a rule applicable to that mode AND carry the full evidence a client relies
    # on — a validation schema, a projection kind, a cache behavior, and a corroborating
    # provider observation (support == supported, with a real source). No enabled-but-blank.
    examined = 0
    for plugin, _entry, canonical in _iter_models():
        for mode in plugin.available_auth_modes():
            rule_by_path = {
                rule.request_path: rule
                for rule in plugin.chat_parameter_rules(model=canonical, auth_type=mode)
                if mode in rule.applicable_auth_modes
            }
            parameters = _document(plugin, canonical, mode)["parameters"]
            for path, entry_dict in parameters.items():
                if entry_dict["gateway"]["status"] != "enabled":
                    continue
                examined += 1
                where = (canonical, mode, path)
                # auth evidence: enabled-ness is rule-driven for THIS mode.
                assert path in rule_by_path, where
                # schema + projection + cache evidence.
                assert entry_dict["schema"] is not None, where
                assert entry_dict["gateway"].get("projection"), where
                assert entry_dict["gateway"].get("cache_behavior"), where
                # final-boundary evidence: a real observation corroborates support.
                assert entry_dict["provider"]["support"] == "supported", where
                assert entry_dict["provider"]["source"] != "none", where
    # item-4 non-vacuity: the loop actually inspected enabled params somewhere.
    assert examined >= 1


def test_registered_provider_rule_sets_have_unique_targets() -> None:
    # INVARIANT (OME-597): within one provider rule set, no two rules write the same provider
    # wire target. normalize_rules enforces it at construction; this locks it for every
    # registered provider (and any future one) under every auth-mode view — a misconfig that
    # points two request paths at one target fails in CI here, never as a caller-facing
    # duplicate_channel 400 in prod. Green today; a future colliding rule turns it red.
    examined = 0
    for plugin, _entry, canonical in _iter_models():
        for mode in (None, *plugin.available_auth_modes()):
            rules = plugin.chat_parameter_rules(model=canonical, auth_type=mode)
            # normalize_rules raises DuplicateParameterRuleError on a target collision; the
            # explicit set-size assertion documents intent and gives a legible failure tuple.
            normalized = normalize_rules(rules)
            targets = [rule.target for rule in normalized]
            assert len(set(targets)) == len(targets), (canonical, mode, targets)
            examined += 1
    assert examined >= 1
