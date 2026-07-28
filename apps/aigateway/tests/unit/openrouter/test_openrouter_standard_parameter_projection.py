"""Phase 4 (OME-479) §9: the STANDARD optional parameters, through OpenRouter.

Runs the REAL route + OpenRouterProviderPlugin, capturing the kwargs handed to
``litellm.acompletion`` (the last gateway-controlled point), then re-running the
INSTALLED litellm openrouter transform to prove each one survives onto the wire
body. Covers tools/tool_choice (OME-583), response_format (OME-584), seed + n
(OME-585), the penalties (OME-586) and logprobs/top_logprobs (OME-595).

The provider-native ``provider_params.top_k`` wrapper, unknown-parameter
fail-closed rejection and the model summary live in
``test_openrouter_parameter_projection``.

INVARIANT: every malformed value rejects with HTTP 400 BEFORE any dispatch. A
parameter that reaches the provider and fails there has already cost the caller
a credential read.

AIDEV-NOTE: the harness below (both fixtures and the three helpers) is a verbatim
copy of the one in ``test_openrouter_parameter_projection``, NOT a shared import.
``_api_key_validation_ok`` is autouse, and an autouse fixture applies only to the
module that defines it — importing it would be a different thing than declaring
it, and moving it to a conftest would widen it to every sibling module.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from aigateway.plugins.openrouter_provider import plugin as openrouter_plugin_module
from aigateway.plugins.openrouter_provider.settings import OpenRouterPluginSettings

_KEY = "sk-or-v1-test"
_MODEL = "openrouter/anthropic/claude-fable-5"


@pytest.fixture(autouse=True)
def _api_key_validation_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    # Explicit test double (per tests/unit/conftest.py AIDEV-NOTE): this module
    # is outside the frozen legacy allowlist, so it opts in to a VALID readiness
    # result — key validation is not what these projection tests exercise.
    from aigateway.core.api_key_validation import (
        ApiKeyValidationResult,
        ApiKeyValidationStage,
        ApiKeyValidationState,
    )
    from aigateway.core.api_key_validation_service import ApiKeyValidationService

    async def _valid(_self, _plugin, _provider, _api_key) -> ApiKeyValidationResult:
        return ApiKeyValidationResult(
            state=ApiKeyValidationState.VALID, stage=ApiKeyValidationStage.READINESS
        )

    monkeypatch.setattr(ApiKeyValidationService, "validate", _valid)


@pytest.fixture()
def enabled_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        openrouter_plugin_module.PLUGIN, "settings", OpenRouterPluginSettings(enabled=True)
    )


def _create_connection(client) -> None:
    resp = client.post(
        "/v1/oauth/connections/api-key",
        json={"provider": "openrouter", "label": "work-openrouter", "api_key": _KEY},
    )
    assert resp.status_code == 201, resp.text


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


# --- OME-583 (§9): function calling reaches dispatch + the installed transform ---

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the weather for a city",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
            },
        },
    }
]


def test_tools_and_tool_choice_reach_dispatch(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)
    choice = {"type": "function", "function": {"name": "get_weather"}}
    captured: dict = {}
    with patch("litellm.acompletion", _fake_acompletion(captured)):
        resp = _post_chat(authenticated_client, {"tools": _TOOLS, "tool_choice": choice})
    assert resp.status_code == 200, resp.text
    assert captured["tools"] == _TOOLS
    assert captured["tool_choice"] == choice


def test_malformed_tool_type_rejects_before_dispatch(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)
    captured: dict = {}
    with patch("litellm.acompletion", _fake_acompletion(captured)):
        resp = _post_chat(authenticated_client, {"tools": [{"type": "web_search"}]})
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["rejected"] == {"tools": "malformed"}
    assert captured == {}  # fail closed: no provider call happened


def test_tools_and_tool_choice_survive_installed_litellm_openrouter_transform() -> None:
    # FINAL-TRANSFORM PROOF (plan §6.1/§9): tools + tool_choice are enabled only because
    # the INSTALLED litellm openrouter transform carries them onto the wire body. If
    # litellm changes this, the rule must be re-reviewed — this test is the tripwire.
    from litellm.llms.openrouter.chat.transformation import OpenrouterConfig
    from litellm.utils import get_optional_params

    upstream = "google/gemini-2.0-flash-001"
    optional = get_optional_params(
        model=upstream,
        custom_llm_provider="openrouter",
        tools=_TOOLS,
        tool_choice="auto",
    )
    assert optional.get("tools") == _TOOLS
    assert optional.get("tool_choice") == "auto"
    wire = OpenrouterConfig().transform_request(
        model=upstream,
        messages=[{"role": "user", "content": "hi"}],
        optional_params=dict(optional),
        litellm_params={},
        headers={},
    )
    assert wire["tools"] == _TOOLS
    assert wire["tool_choice"] == "auto"


# --- OME-584 (§9): response_format reaches dispatch + the installed transform --

_RESPONSE_FORMAT_JSON_OBJECT = {"type": "json_object"}
_RESPONSE_FORMAT_JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "weather",
        "schema": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
}


def test_response_format_json_object_reaches_dispatch(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)
    captured: dict = {}
    with patch("litellm.acompletion", _fake_acompletion(captured)):
        resp = _post_chat(authenticated_client, {"response_format": _RESPONSE_FORMAT_JSON_OBJECT})
    assert resp.status_code == 200, resp.text
    assert captured["response_format"] == _RESPONSE_FORMAT_JSON_OBJECT


def test_response_format_json_schema_reaches_dispatch(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)
    captured: dict = {}
    with patch("litellm.acompletion", _fake_acompletion(captured)):
        resp = _post_chat(authenticated_client, {"response_format": _RESPONSE_FORMAT_JSON_SCHEMA})
    assert resp.status_code == 200, resp.text
    assert captured["response_format"] == _RESPONSE_FORMAT_JSON_SCHEMA


def test_malformed_response_format_type_rejects_before_dispatch(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)
    captured: dict = {}
    with patch("litellm.acompletion", _fake_acompletion(captured)):
        resp = _post_chat(authenticated_client, {"response_format": {"type": "xml"}})
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["rejected"] == {"response_format": "malformed"}
    assert captured == {}  # fail closed: no provider call happened


def test_response_format_survives_installed_litellm_openrouter_transform() -> None:
    # FINAL-TRANSFORM PROOF (plan §6.1/§9): response_format is enabled ONLY because the
    # INSTALLED litellm openrouter transform carries both documented forms onto the wire
    # body VERBATIM. This mirrors the §9 probe's exact path (map_openai_params ->
    # transform_request); if litellm changes this, the rule must be re-reviewed — this
    # test is the tripwire.
    from litellm.llms.openrouter.chat.transformation import OpenrouterConfig

    upstream = "google/gemini-2.0-flash-001"
    cfg = OpenrouterConfig()
    for rf in (_RESPONSE_FORMAT_JSON_OBJECT, _RESPONSE_FORMAT_JSON_SCHEMA):
        mapped = cfg.map_openai_params(
            non_default_params={"response_format": rf},
            optional_params={},
            model=upstream,
            drop_params=False,
        )
        wire = cfg.transform_request(
            model=upstream,
            messages=[{"role": "user", "content": "hi"}],
            optional_params=mapped,
            litellm_params={},
            headers={},
        )
        assert wire["response_format"] == rf


# --- OME-585 (§9): seed + n reach dispatch + the installed transform ----------


def test_seed_and_n_reach_dispatch(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)
    captured: dict = {}
    with patch("litellm.acompletion", _fake_acompletion(captured)):
        resp = _post_chat(authenticated_client, {"seed": 42, "n": 3})
    assert resp.status_code == 200, resp.text
    assert captured["seed"] == 42
    assert captured["n"] == 3


def test_malformed_n_rejects_before_dispatch(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)
    captured: dict = {}
    with patch("litellm.acompletion", _fake_acompletion(captured)):
        resp = _post_chat(authenticated_client, {"n": 0})  # below the minimum of 1
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["rejected"] == {"n": "malformed"}
    assert captured == {}  # fail closed: no provider call happened


def test_non_integer_seed_rejects_before_dispatch(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)
    captured: dict = {}
    with patch("litellm.acompletion", _fake_acompletion(captured)):
        resp = _post_chat(authenticated_client, {"seed": 1.5})  # not an integer
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["rejected"] == {"seed": "malformed"}
    assert captured == {}


def test_seed_and_n_survive_installed_litellm_openrouter_transform() -> None:
    # FINAL-TRANSFORM PROOF (plan §6.1/§9): seed + n are enabled ONLY because the
    # INSTALLED litellm openrouter transform carries them onto the wire body VERBATIM.
    # Mirrors the §9 probe's exact path (map_openai_params -> transform_request); this
    # test is the tripwire if litellm changes the behavior.
    from litellm.llms.openrouter.chat.transformation import OpenrouterConfig

    upstream = "google/gemini-2.0-flash-001"
    cfg = OpenrouterConfig()
    mapped = cfg.map_openai_params(
        non_default_params={"seed": 7, "n": 2},
        optional_params={},
        model=upstream,
        drop_params=False,
    )
    wire = cfg.transform_request(
        model=upstream,
        messages=[{"role": "user", "content": "hi"}],
        optional_params=mapped,
        litellm_params={},
        headers={},
    )
    assert wire["seed"] == 7
    assert wire["n"] == 2


# --- OME-586 (§9): frequency_penalty + presence_penalty reach dispatch + transform --


def test_penalties_reach_dispatch(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)
    captured: dict = {}
    with patch("litellm.acompletion", _fake_acompletion(captured)):
        resp = _post_chat(
            authenticated_client, {"frequency_penalty": 0.5, "presence_penalty": -0.5}
        )
    assert resp.status_code == 200, resp.text
    assert captured["frequency_penalty"] == 0.5
    assert captured["presence_penalty"] == -0.5


def test_out_of_range_frequency_penalty_rejects_before_dispatch(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)
    captured: dict = {}
    with patch("litellm.acompletion", _fake_acompletion(captured)):
        resp = _post_chat(authenticated_client, {"frequency_penalty": 3.0})  # above the max of 2
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["rejected"] == {"frequency_penalty": "malformed"}
    assert captured == {}  # fail closed: no provider call happened


def test_penalties_survive_installed_litellm_openrouter_transform() -> None:
    # FINAL-TRANSFORM PROOF (plan §6.1/§9): both penalties are enabled ONLY because the
    # INSTALLED litellm openrouter transform carries them onto the wire body VERBATIM.
    # Mirrors the §9 probe's exact path; this test is the tripwire if litellm changes it.
    from litellm.llms.openrouter.chat.transformation import OpenrouterConfig

    upstream = "google/gemini-2.0-flash-001"
    cfg = OpenrouterConfig()
    mapped = cfg.map_openai_params(
        non_default_params={"frequency_penalty": 0.5, "presence_penalty": -0.5},
        optional_params={},
        model=upstream,
        drop_params=False,
    )
    wire = cfg.transform_request(
        model=upstream,
        messages=[{"role": "user", "content": "hi"}],
        optional_params=mapped,
        litellm_params={},
        headers={},
    )
    assert wire["frequency_penalty"] == 0.5
    assert wire["presence_penalty"] == -0.5


# --- OME-595 (§9): logprobs + top_logprobs reach dispatch + transform --------


def test_logprobs_reach_dispatch(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)
    captured: dict = {}
    with patch("litellm.acompletion", _fake_acompletion(captured)):
        resp = _post_chat(authenticated_client, {"logprobs": True, "top_logprobs": 5})
    assert resp.status_code == 200, resp.text
    assert captured["logprobs"] is True
    assert captured["top_logprobs"] == 5


def test_out_of_range_top_logprobs_rejects_before_dispatch(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)
    captured: dict = {}
    with patch("litellm.acompletion", _fake_acompletion(captured)):
        resp = _post_chat(authenticated_client, {"top_logprobs": 21})  # above the max of 20
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["rejected"] == {"top_logprobs": "malformed"}
    assert captured == {}  # fail closed: no provider call happened


def test_logprobs_survive_installed_litellm_openrouter_transform() -> None:
    # FINAL-TRANSFORM PROOF (plan §6.1/§9): both fields are enabled ONLY because the
    # INSTALLED litellm openrouter transform carries them onto the wire body VERBATIM.
    # Mirrors the §9 probe's exact path; this test is the tripwire if litellm changes it.
    from litellm.llms.openrouter.chat.transformation import OpenrouterConfig

    upstream = "google/gemini-2.0-flash-001"
    cfg = OpenrouterConfig()
    mapped = cfg.map_openai_params(
        non_default_params={"logprobs": True, "top_logprobs": 20},
        optional_params={},
        model=upstream,
        drop_params=False,
    )
    wire = cfg.transform_request(
        model=upstream,
        messages=[{"role": "user", "content": "hi"}],
        optional_params=mapped,
        litellm_params={},
        headers={},
    )
    assert wire["logprobs"] is True
    assert wire["top_logprobs"] == 20
