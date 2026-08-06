"""Server-side web search: caller intent in, the provider's native envelope out.

FEATURE: a caller asks OpenRouter to retrieve before answering with `web_search: true`.
STORY: as a benchmark author, a published retrieval-bearing score was produced on the provider's
own search; a client-side loop over a different backend is a different experiment.

WHY the caller does NOT send `plugins` — OpenRouter's own spelling. `plugins` is an
extensibility ENVELOPE: carrying arbitrary provider extensions is its whole purpose, so no
schema can bound it without defeating it, and OME-646 removed it for exactly that reason. It
stays refused (`test_openrouter_security`). The caller sends a BOOLEAN, which is bounded
completely, and `prepare_chat_body` assigns the envelope from gateway-owned policy — the same
two-layer shape `provider` already uses.

WHY this landing does not advertise `tools: [{"type": "openrouter:web_search"}]` — in its
2026-07-31 compatibility probe, that spelling returned HTTP 200 without search evidence, while
the emitted `plugins` envelope retrieved successfully. OpenRouter now documents both surfaces,
so enabling the server-tool form later requires fresh conformance evidence through this
Gateway's pinned LiteLLM/provider path; it is not a compatibility fallback for this contract.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from aigateway.core.parameter_projection import IncompatibleParametersError
from aigateway.plugins.openrouter_provider import plugin as openrouter_plugin_module
from aigateway.plugins.openrouter_provider.parameters import (
    openrouter_chat_parameter_rules,
    openrouter_chat_parameter_tools,
)
from aigateway.plugins.openrouter_provider.plugin import OpenRouterProviderPlugin
from aigateway.plugins.openrouter_provider.settings import OpenRouterPluginSettings
from aigateway.plugins.openrouter_provider.web_search import (
    EXCLUDE_DOMAINS_KEY,
    apply_web_search,
)

_MODEL = "openrouter/google/gemini-3-flash-preview"
_KEY = "sk-or-v1-test"


@pytest.fixture(autouse=True)
def _api_key_validation_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    from aigateway.core.api_key_validation import (
        ApiKeyValidationResult,
        ApiKeyValidationStage,
        ApiKeyValidationState,
    )
    from aigateway.core.api_key_validation_service import ApiKeyValidationService

    async def _valid(_self, _plugin, _provider, _api_key) -> ApiKeyValidationResult:
        return ApiKeyValidationResult(
            state=ApiKeyValidationState.VALID,
            stage=ApiKeyValidationStage.READINESS,
        )

    monkeypatch.setattr(ApiKeyValidationService, "validate", _valid)


@pytest.fixture()
def enabled_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        openrouter_plugin_module.PLUGIN,
        "settings",
        OpenRouterPluginSettings(enabled=True),
    )


def _create_connection(client) -> None:
    response = client.post(
        "/v1/oauth/connections/api-key",
        json={"provider": "openrouter", "label": "work-openrouter", "api_key": _KEY},
    )
    assert response.status_code == 201, response.text


def _fake_acompletion(captured: dict):
    async def fake_acompletion(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            model_dump=lambda: {"id": "or-1", "choices": [{"message": {"content": "ok"}}]}
        )

    return fake_acompletion


def _post_chat(client, body: dict):
    payload = {"model": _MODEL, "messages": [{"role": "user", "content": "hi"}], **body}
    return client.post("/v1/chat/completions", json=payload)


class _Settings:
    def __init__(self, excluded: list[str] | None = None) -> None:
        self.web_search_excluded_domains = excluded or []


def _rule(path: str):
    for rule in openrouter_chat_parameter_rules(model=_MODEL, auth_type="api_key"):
        if rule.request_path == path:
            return rule
    return None


def _prepared(body: dict[str, Any], settings: _Settings | None = None) -> dict[str, Any]:
    out = dict(body)
    apply_web_search(out, settings or _Settings())
    return out


# --- the caller-facing contract --------------------------------------------------


def test_web_search_is_enabled_as_a_plain_boolean() -> None:
    """A boolean is bounded COMPLETELY — there is no nested JSON for a caller to smuggle."""
    rule = _rule("web_search")

    assert rule is not None
    assert rule.parameter_schema is not None
    assert rule.parameter_schema.type == "boolean"


def test_caller_exclusions_are_a_bounded_string_array() -> None:
    rule = _rule("web_search_excluded_domains")

    assert rule is not None
    assert rule.parameter_schema is not None
    assert rule.parameter_schema.type == "array"
    assert rule.parameter_schema.item_type == "string"


def test_the_native_envelope_stays_refused_as_a_caller_path() -> None:
    """INVARIANT: enabling web search must not re-open `plugins`. If this ever passes with a
    rule present, a caller can hand OpenRouter arbitrary extensions again."""
    assert _rule("plugins") is None


def test_the_routing_controls_ome_646_removed_stay_removed() -> None:
    for path in ("provider", "route", "models"):
        assert _rule(path) is None, path


def test_unproven_server_tool_types_stay_unadvertised() -> None:
    """`tools_schema` gates each item's `type`, so leaving these out is what makes a caller
    fail closed until this Gateway path has current conformance evidence for them."""
    enabled = {
        tool.tool_type
        for tool in openrouter_chat_parameter_tools(model=_MODEL, auth_type="api_key")
    }

    assert "openrouter:web_search" not in enabled
    assert "openrouter:web_fetch" not in enabled
    assert "function" in enabled


# --- the translation -------------------------------------------------------------


def test_true_becomes_the_providers_web_plugin() -> None:
    out = _prepared({"web_search": True})

    assert out["plugins"] == [{"id": "web", "engine": "native"}]


def test_the_caller_facing_keys_never_reach_the_wire() -> None:
    """Neither is an OpenRouter field; leaving one on the body sends an unknown parameter."""
    out = _prepared({"web_search": True, "web_search_excluded_domains": ["a.test"]})

    assert "web_search" not in out
    assert "web_search_excluded_domains" not in out


def test_web_search_reaches_dispatch_through_the_real_route_pipeline(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    """Classifier, projection, provider preparation and dispatch preserve one guarded intent."""

    _create_connection(authenticated_client)
    captured: dict = {}
    with patch("litellm.acompletion", _fake_acompletion(captured)):
        response = _post_chat(
            authenticated_client,
            {
                "web_search": True,
                "web_search_excluded_domains": ["rubric.test"],
            },
        )

    assert response.status_code == 200, response.text
    assert "web_search" not in captured
    assert "web_search_excluded_domains" not in captured
    assert captured["plugins"] == [
        {"id": "web", "engine": "native", "exclude_domains": ["rubric.test"]}
    ]


def test_false_and_absent_both_send_no_plugin() -> None:
    assert "plugins" not in _prepared({"web_search": False})
    assert "plugins" not in _prepared({})


def test_online_model_suffix_is_normalized_into_the_guarded_plugin_path() -> None:
    out = _prepared(
        {"model": "openrouter/google/gemini-3-flash-preview:online"},
        _Settings(["rubric.test"]),
    )

    assert out["model"] == "openrouter/google/gemini-3-flash-preview"
    assert out["plugins"] == [{"id": "web", "engine": "native", "exclude_domains": ["rubric.test"]}]


def test_explicit_false_disables_an_online_model_suffix() -> None:
    out = _prepared(
        {
            "model": "openrouter/google/gemini-3-flash-preview:online",
            "web_search": False,
        },
        _Settings(["rubric.test"]),
    )

    assert out["model"] == "openrouter/google/gemini-3-flash-preview"
    assert "plugins" not in out


def test_exclusions_without_web_search_fail_instead_of_becoming_a_silent_noop() -> None:
    """An accepted parameter must have an effect or fail closed; silently dropping a valid
    exclusion list would make a caller believe its retrieval policy was active when no search
    was requested at all."""
    plugin = OpenRouterProviderPlugin(OpenRouterPluginSettings(enabled=True))

    with pytest.raises(
        IncompatibleParametersError,
        match="web_search_excluded_domains_requires_web_search_true",
    ):
        plugin.validate_chat_parameter_combination(
            {"web_search_excluded_domains": ["a.test"]},
            model=_MODEL,
            auth_mode="api_key",
        )


# --- the exclusion union ---------------------------------------------------------


def test_deployment_exclusions_apply_without_the_caller_asking() -> None:
    out = _prepared({"web_search": True}, _Settings(["rubric.test"]))

    assert out["plugins"][0]["exclude_domains"] == ["rubric.test"]


def test_caller_exclusions_are_added_to_the_deployments() -> None:
    out = _prepared(
        {"web_search": True, "web_search_excluded_domains": ["extra.test"]},
        _Settings(["rubric.test"]),
    )

    assert out["plugins"][0]["exclude_domains"] == ["extra.test", "rubric.test"]


def test_a_caller_cannot_drop_a_deployment_exclusion() -> None:
    """INVARIANT: UNION, never substitution. The motivating case is a benchmark candidate that
    must not retrieve the rubric it is graded against — a guard a caller can shorten is not a
    guard, and the caller supplying its own list is exactly when it would try."""
    out = _prepared(
        {"web_search": True, "web_search_excluded_domains": ["unrelated.test"]},
        _Settings(["rubric.test"]),
    )

    assert "rubric.test" in out["plugins"][0]["exclude_domains"]


def test_no_exclusions_omits_the_field_rather_than_sending_an_empty_list() -> None:
    """An empty list reads to the provider as 'exclude nothing' rather than 'use your default'."""
    out = _prepared({"web_search": True})

    # Both spellings: the emitted one must be absent, and the historical typo must never return.
    assert EXCLUDE_DOMAINS_KEY not in out["plugins"][0]
    assert "excluded_domains" not in out["plugins"][0]


def test_the_wire_key_is_openrouters_spelling() -> None:
    """INVARIANT: the blocklist rides `exclude_domains`. `excluded_domains` is IGNORED.

    This is pinned by name because no status code can catch it. OpenRouter does not validate the
    `plugins` envelope — an invented key returns HTTP 200 exactly like a real one — so the wrong
    spelling produced a normal answer, a normal bill, and no exclusion at all, from `26858fc1`
    until 2026-07-31.

    MEASURED live on both engines: `exclude_domains` drove blocked-host citations to zero, while
    `excluded_domains` left them identical to baseline. Excluding a single host removed exactly
    that host, which is what rules out search noise as the explanation.

    A benchmark candidate that can reach its own rubric scores HIGHER, so this failure never looks
    like a bug from the outside. If a future change renames this key, this test fails loudly
    instead of the guard going quiet again.
    """
    out = _prepared({"web_search": True}, _Settings(["rubric.test"]))

    assert EXCLUDE_DOMAINS_KEY == "exclude_domains"
    assert out["plugins"][0]["exclude_domains"] == ["rubric.test"]
    assert "excluded_domains" not in out["plugins"][0]
