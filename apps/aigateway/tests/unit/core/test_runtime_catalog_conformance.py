"""Conformance coverage for providers whose production catalogs are runtime-only."""

from __future__ import annotations

from aigateway.core.chat_parameters import normalize_rules
from aigateway.core.model_capabilities import canonical_model_id
from aigateway.core.parameter_projection import GATEWAY_OWNED_FIELDS, wrapper_path_conflicts
from aigateway.core.request_cache.keys import PROMPT_KEY_FIELDS
from tests.unit.core.test_provider_contract_conformance import _REGISTRY
from tests.unit.core.test_provider_contract_conformance_hardening import _served_document


def test_every_registered_provider_supplies_conformance_models_and_rules() -> None:
    for plugin in _REGISTRY.all():
        models = plugin.conformance_models()
        assert models, plugin.custom_llm_provider
        for entry in models:
            canonical = canonical_model_id(
                custom_llm_provider=plugin.custom_llm_provider,
                model_name=entry.model_name,
            )
            for mode in plugin.available_auth_modes():
                rules = normalize_rules(
                    rule
                    for rule in plugin.chat_parameter_rules(model=canonical, auth_type=mode)
                    if mode in rule.applicable_auth_modes
                )
                where = (plugin.custom_llm_provider, canonical, mode)
                assert rules, where
                observations = plugin.chat_parameter_observations(model=canonical, auth_type=mode)
                document = _served_document(plugin, canonical, mode, snapshot=None)
                enabled = {
                    path
                    for path, entry_dict in document["parameters"].items()
                    if entry_dict["gateway"]["status"] == "enabled"
                }
                assert enabled == {rule.request_path for rule in rules}, where
                assert (
                    wrapper_path_conflicts(
                        [rule.request_path for rule in rules]
                        + [observation.request_path for observation in observations]
                    )
                    == ()
                ), where
                for rule in rules:
                    rule_where = (*where, rule.request_path)
                    assert rule.parameter_schema is not None, rule_where
                    assert rule.target.split(".", 1)[0] not in GATEWAY_OWNED_FIELDS, rule_where
                    if rule.cache_behavior != "bypass":
                        assert rule.request_path in PROMPT_KEY_FIELDS, rule_where
                    entry_dict = document["parameters"][rule.request_path]
                    assert entry_dict["schema"] is not None, rule_where
                    assert entry_dict["gateway"].get("projection"), rule_where
                    assert entry_dict["gateway"].get("cache_behavior"), rule_where
                    assert entry_dict["provider"]["support"] == "supported", rule_where
                    assert entry_dict["provider"]["source"] != "none", rule_where
                tools = plugin.chat_parameter_tools(model=canonical, auth_type=mode)
                assert set(document["tools"]) == {tool.tool_type for tool in tools}, where
                assert "stream" in document["transport"], where
