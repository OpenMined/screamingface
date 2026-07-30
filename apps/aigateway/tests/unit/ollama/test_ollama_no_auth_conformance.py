"""Ollama conformance and anonymous provider-auth route coverage."""

from __future__ import annotations

from fastapi.testclient import TestClient

from aigateway.plugins.ollama_provider import plugin as ollama_module
from aigateway.plugins.ollama_provider.plugin import OllamaProviderPlugin


def test_empty_runtime_catalog_has_a_provider_owned_conformance_model(monkeypatch) -> None:
    monkeypatch.setattr(ollama_module, "discover_ollama_models", lambda _host: [])
    plugin = OllamaProviderPlugin()

    assert plugin.register_models() == []
    models = plugin.conformance_models()

    assert len(models) == 1
    assert models[0].model_name.startswith("ollama/")
    canonical = models[0].model_name
    rules = plugin.chat_parameter_rules(model=canonical, auth_type="none")
    assert rules
    assert all("none" in rule.applicable_auth_modes for rule in rules)


def test_model_parameters_route_resolves_ollama_without_provider_profile(
    monkeypatch, authenticated_client: TestClient
) -> None:
    monkeypatch.setattr(
        ollama_module,
        "discover_ollama_models",
        lambda _host: ["conformance-route-model"],
    )

    response = authenticated_client.get(
        "/v1/model-parameters",
        params={"model": "ollama/conformance-route-model"},
    )

    assert response.status_code == 200, response.text
    document = response.json()
    assert document["context"]["auth_mode"] == "none"
    assert any(entry["gateway"]["status"] == "enabled" for entry in document["parameters"].values())
