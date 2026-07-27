"""OME-640: Anthropic refuses reasoning/max-token pairs the model cannot serve.

FEATURE: one effective parameter contract. ``reasoning_effort`` and ``max_tokens``
are each enabled and each schema-checked, but on a MANUAL-thinking model the
installed transform turns the effort into a thinking BUDGET, and Anthropic
requires that budget to be smaller than ``max_tokens``. The contract has to refuse
the pair it cannot honor instead of advertising both fields as independently safe.

STORY: as a caller I get an immediate, actionable 400 naming the two fields and
the rule that binds them, rather than an opaque provider error after the gateway
has already read my credential and dispatched.

INVARIANT: the constraint is MODEL-specific. Adaptive-thinking models get
``thinking={"type":"adaptive"}`` with no budget at all, so the constraint does not
exist for them and must never be applied to them.
INVARIANT: the constraint is AUTH-specific, and the auth split lives in the
credential layer — the OAuth strategy sends the interleaved-thinking beta header
and the api-key path sends no beta header at all. The seam therefore reads the
RESOLVED auth mode, never a caller-declared one.
INVARIANT: the exemption needs BOTH the beta header AND tools. Interleaved
thinking is defined as extended thinking WITH TOOL USE, so a tool-less OAuth
request is still bound by the ordinary rule.
"""

from __future__ import annotations

import json
import logging
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from aigateway.core.parameter_projection import IncompatibleParametersError
from aigateway.core.profile_index import ProfileIndexStore
from aigateway.core.profile_models import (
    AuthMode,
    AuthType,
    Profile,
    ProfileDefaults,
    ProfileState,
    credential_name_for,
    profile_id_for,
)
from aigateway.core.standard_parameters import REASONING_EFFORT_SCHEMA
from aigateway.plugins.anthropic_provider.auth import credential_service_for
from aigateway.plugins.anthropic_provider.parameters import anthropic_chat_parameter_rules
from aigateway.plugins.anthropic_provider.settings import AnthropicPluginSettings
from aigateway.plugins.anthropic_provider.thinking import (
    INTERLEAVED_BETA_MODELS,
    MANUAL_THINKING_BUDGETS,
    MANUAL_THINKING_MODELS,
    raise_on_thinking_conflict,
)

_PLUGIN = "aigateway.plugins.anthropic_provider.plugin.AnthropicProviderPlugin"
_DISPATCH = f"{_PLUGIN}.chat_completion"

_MANUAL = "anthropic/claude-sonnet-4-5"
_HAIKU = "anthropic/claude-haiku-4-5"
_ADAPTIVE = (
    "anthropic/claude-opus-4-8",
    "anthropic/claude-opus-4-7",
    "anthropic/claude-sonnet-4-6",
)
_TOOLS = [
    {
        "type": "function",
        "function": {"name": "calc", "parameters": {"type": "object", "properties": {}}},
    }
]


# --- seeding ------------------------------------------------------------------


def _account_id(client) -> str:
    return client.get("/v1/auth/me").json()["id"]


def _service(account_id: str) -> str:
    return credential_service_for(credential_name_for(account_id, "default"))


async def _seed_profile(
    credential_blobs,
    account_id: str,
    *,
    auth_type: AuthType,
    defaults: ProfileDefaults | None = None,
) -> None:
    await ProfileIndexStore(credential_store=credential_blobs.store).upsert(
        Profile(
            id=profile_id_for(account_id, "anthropic", "default"),
            account_id=account_id,
            provider="anthropic",
            name="default",
            state=ProfileState.AUTHENTICATED,
            auth_type=auth_type,
            defaults=defaults or ProfileDefaults(),
        )
    )


async def _seed_oauth(credential_blobs, account_id: str, **kwargs) -> None:
    credential_blobs.write(
        _service(account_id),
        "default",
        json.dumps(
            {
                "access_token": "tok",
                "refresh_token": "rt",
                "id_token": "id",
                "expires_at_ms": int(time.time() * 1000) + 3_600_000,
                "token_type": "Bearer",
            }
        ),
    )
    await _seed_profile(credential_blobs, account_id, auth_type="oauth", **kwargs)


async def _seed_api_key(credential_blobs, account_id: str, **kwargs) -> None:
    credential_blobs.write(
        _service(account_id),
        "default",
        json.dumps({"auth_type": "api_key", "api_key": "sk-ant-api03-raw"}),
    )
    await _seed_profile(credential_blobs, account_id, auth_type="api_key", **kwargs)


def _capture(store: dict[str, Any]):
    async def _fake_chat_completion(_self, body):
        store.update(body)
        return SimpleNamespace(
            model_dump=lambda: {"id": "x", "choices": [{"message": {"content": "ok"}}]}
        )

    return _fake_chat_completion


def _post(client, model: str, **extra: Any):
    return client.post(
        "/v1/chat/completions",
        json={"model": model, "messages": [{"role": "user", "content": "hi"}], **extra},
    )


# --- the refusal --------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_manual_thinking_model_refuses_a_budget_exceeding_max_tokens(
    credential_blobs, authenticated_client
) -> None:
    # reasoning_effort="high" becomes thinking.budget_tokens=4096 on this model,
    # and Anthropic requires budget_tokens < max_tokens. Both fields validate
    # alone; the PAIR is what the provider cannot serve.
    account_id = _account_id(authenticated_client)
    await _seed_api_key(credential_blobs, account_id)

    captured: dict[str, Any] = {}
    with patch(_DISPATCH, _capture(captured)):
        resp = _post(authenticated_client, _MANUAL, reasoning_effort="high", max_tokens=128)

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["code"] == "incompatible_parameters"
    assert detail["provider"] == "anthropic"
    assert detail["conflict"] == ["max_tokens", "reasoning_effort"]
    # The message must name the binding rule, not just say "invalid".
    assert "4096" in detail["message"]
    assert captured == {}


@pytest.mark.parametrize("model", _ADAPTIVE)
@pytest.mark.asyncio
async def test_an_adaptive_thinking_model_accepts_the_same_combination(
    credential_blobs, authenticated_client, model: str
) -> None:
    # The whole point of the model split: these three get
    # thinking={"type":"adaptive"} with NO budget, so there is nothing for
    # max_tokens to be smaller than. A provider-wide rule would break them.
    account_id = _account_id(authenticated_client)
    await _seed_api_key(credential_blobs, account_id)

    captured: dict[str, Any] = {}
    with patch(_DISPATCH, _capture(captured)):
        resp = _post(authenticated_client, model, reasoning_effort="high", max_tokens=128)

    assert resp.status_code == 200
    assert captured["reasoning_effort"] == "high"
    assert captured["max_tokens"] == 128


# --- the interleaved-thinking exemption ---------------------------------------


@pytest.mark.asyncio
async def test_the_exemption_applies_on_oauth_with_tools(
    credential_blobs, authenticated_client
) -> None:
    # The OAuth strategy sends anthropic-beta: …interleaved-thinking-2025-05-14…,
    # under which budget_tokens may exceed max_tokens. With tools present the
    # feature is actually in effect, so the same body is legal.
    account_id = _account_id(authenticated_client)
    await _seed_oauth(credential_blobs, account_id)

    captured: dict[str, Any] = {}
    with patch(_DISPATCH, _capture(captured)):
        resp = _post(
            authenticated_client, _MANUAL, reasoning_effort="high", max_tokens=128, tools=_TOOLS
        )

    assert resp.status_code == 200
    assert captured["max_tokens"] == 128
    # Pins the premise the exemption rests on: this path really does carry the beta.
    assert "interleaved-thinking-2025-05-14" in captured["extra_headers"]["anthropic-beta"]


@pytest.mark.asyncio
async def test_the_exemption_needs_tools(credential_blobs, authenticated_client) -> None:
    # Interleaved thinking is extended thinking WITH TOOL USE. The beta header on
    # a tool-less request buys nothing, so the ordinary rule still binds.
    account_id = _account_id(authenticated_client)
    await _seed_oauth(credential_blobs, account_id)

    captured: dict[str, Any] = {}
    with patch(_DISPATCH, _capture(captured)):
        resp = _post(authenticated_client, _MANUAL, reasoning_effort="high", max_tokens=128)

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "incompatible_parameters"
    assert captured == {}


@pytest.mark.asyncio
async def test_the_exemption_is_oauth_only(credential_blobs, authenticated_client) -> None:
    # The api-key credential strategy sends Authorization and nothing else — no
    # beta header — so tools cannot buy the exemption on that path.
    account_id = _account_id(authenticated_client)
    await _seed_api_key(credential_blobs, account_id)

    captured: dict[str, Any] = {}
    with patch(_DISPATCH, _capture(captured)):
        resp = _post(
            authenticated_client, _MANUAL, reasoning_effort="high", max_tokens=128, tools=_TOOLS
        )

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "incompatible_parameters"
    assert captured == {}


@pytest.mark.asyncio
async def test_the_exemption_does_not_extend_to_haiku(
    credential_blobs, authenticated_client
) -> None:
    # AIDEV-NOTE: Haiku 4.5 is manual-thinking but is NOT in the interleaved set.
    # The published documentation groups it with Opus 4.5 as having "different
    # interleaved thinking behaviors" without saying what they are, so this takes
    # the fail-closed reading: an honest 400 on a pair that is invalid on the
    # api-key path regardless, rather than an opaque provider error.
    account_id = _account_id(authenticated_client)
    await _seed_oauth(credential_blobs, account_id)

    captured: dict[str, Any] = {}
    with patch(_DISPATCH, _capture(captured)):
        resp = _post(
            authenticated_client, _HAIKU, reasoning_effort="high", max_tokens=128, tools=_TOOLS
        )

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "incompatible_parameters"
    assert captured == {}


# --- the boundary and the non-triggers ----------------------------------------


@pytest.mark.asyncio
async def test_max_tokens_one_above_the_budget_dispatches(
    credential_blobs, authenticated_client
) -> None:
    # "budget_tokens must be LESS THAN max_tokens" — so budget+1 is the first
    # legal value, and the check must not be off by one in the strict direction.
    account_id = _account_id(authenticated_client)
    await _seed_api_key(credential_blobs, account_id)

    captured: dict[str, Any] = {}
    with patch(_DISPATCH, _capture(captured)):
        resp = _post(authenticated_client, _MANUAL, reasoning_effort="high", max_tokens=4097)

    assert resp.status_code == 200
    assert captured["max_tokens"] == 4097


@pytest.mark.asyncio
async def test_max_tokens_equal_to_the_budget_is_refused(
    credential_blobs, authenticated_client
) -> None:
    # INVARIANT: the boundary is EXCLUSIVE — Anthropic requires the budget to be
    # strictly smaller, so an exact tie is a refusal, not a pass.
    # AIDEV-NOTE: this is the dedicated home for the equal-values case. A profile
    # default in tests/unit/test_chat_x_profile.py used to land on it by accident
    # while testing something else entirely; that fixture moved off the boundary
    # and the boundary itself is asserted here.
    account_id = _account_id(authenticated_client)
    await _seed_api_key(credential_blobs, account_id)

    with patch(_DISPATCH, _capture({})):
        resp = _post(authenticated_client, _MANUAL, reasoning_effort="high", max_tokens=4096)

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "incompatible_parameters"


@pytest.mark.asyncio
async def test_a_tiny_max_tokens_without_reasoning_effort_dispatches(
    credential_blobs, authenticated_client
) -> None:
    # No thinking requested → no budget → nothing to conflict with. The seam must
    # not become a general max_tokens floor.
    account_id = _account_id(authenticated_client)
    await _seed_api_key(credential_blobs, account_id)

    captured: dict[str, Any] = {}
    with patch(_DISPATCH, _capture(captured)):
        resp = _post(authenticated_client, _MANUAL, max_tokens=1)

    assert resp.status_code == 200
    assert captured["max_tokens"] == 1


@pytest.mark.asyncio
async def test_reasoning_effort_none_dispatches(credential_blobs, authenticated_client) -> None:
    # "none" is in the schema enum and maps to NO thinking at all; the plugin then
    # drops it in prepare_chat_body. It must not be treated as a budget request.
    account_id = _account_id(authenticated_client)
    await _seed_api_key(credential_blobs, account_id)

    captured: dict[str, Any] = {}
    with patch(_DISPATCH, _capture(captured)):
        resp = _post(authenticated_client, _MANUAL, reasoning_effort="none", max_tokens=1)

    assert resp.status_code == 200
    assert captured["max_tokens"] == 1
    assert "reasoning_effort" not in captured


@pytest.mark.asyncio
async def test_an_absent_max_tokens_dispatches(credential_blobs, authenticated_client) -> None:
    # litellm raises max_tokens above the budget itself when the caller omitted
    # it, so the gateway must not invent a conflict where the transform fixes it.
    account_id = _account_id(authenticated_client)
    await _seed_api_key(credential_blobs, account_id)

    captured: dict[str, Any] = {}
    with patch(_DISPATCH, _capture(captured)):
        resp = _post(authenticated_client, _MANUAL, reasoning_effort="high")

    assert resp.status_code == 200
    assert "max_tokens" not in captured


# --- ordering: the refusal comes before everything downstream -----------------


@pytest.mark.asyncio
async def test_the_refusal_precedes_provider_preparation_and_everything_after_it(
    credential_blobs, authenticated_client
) -> None:
    # prepare_chat_body is the EARLIEST of the four downstream steps in
    # routes/chat.py (prepare < cache plan < credential injection < dispatch) and
    # sits outside the dispatch try/except, so tripping it proves the whole
    # "before provider preparation, cache planning, credential access and
    # dispatch" claim with one assertion.
    account_id = _account_id(authenticated_client)
    await _seed_api_key(credential_blobs, account_id)

    def _tripwire(_self, _body):
        raise AssertionError("prepare_chat_body ran on a refused parameter combination")

    with patch(f"{_PLUGIN}.prepare_chat_body", _tripwire):
        resp = _post(authenticated_client, _MANUAL, reasoning_effort="high", max_tokens=128)

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "incompatible_parameters"


@pytest.mark.asyncio
async def test_the_refusal_precedes_credential_access(
    credential_blobs, authenticated_client
) -> None:
    # Instrumentation-free ordering proof: the profile is AUTHENTICATED but no
    # credential blob was ever written, so reaching credential injection would
    # produce a 401. A 400 therefore means no credential was read.
    account_id = _account_id(authenticated_client)
    await _seed_profile(credential_blobs, account_id, auth_type="api_key")

    resp = _post(authenticated_client, _MANUAL, reasoning_effort="high", max_tokens=128)

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "incompatible_parameters"


# --- profile defaults participate ---------------------------------------------


@pytest.mark.asyncio
async def test_a_conflicting_profile_default_still_refuses_and_names_the_profile(
    credential_blobs, authenticated_client, caplog
) -> None:
    # max_tokens can arrive from the stored profile (OME-638 merges defaults
    # before classification, so the seam sees the same body dispatch would).
    # The caller keeps ONE code — reasoning_effort is opted out of profile
    # defaulting on this provider, so their own field always participates and
    # they can fix either side — while the operator gets the profile named.
    account_id = _account_id(authenticated_client)
    await _seed_api_key(credential_blobs, account_id, defaults=ProfileDefaults(max_tokens=128))

    captured: dict[str, Any] = {}
    with caplog.at_level(logging.WARNING), patch(_DISPATCH, _capture(captured)):
        resp = _post(authenticated_client, _MANUAL, reasoning_effort="high")

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "incompatible_parameters"
    assert captured == {}
    assert any(
        "profile=default" in record.getMessage() and "max_tokens" in record.getMessage()
        for record in caplog.records
    )


# --- the provider-local decision procedure ------------------------------------


@pytest.mark.parametrize(
    ("model", "auth_mode", "effort", "max_tokens", "tools", "conflicts"),
    [
        # manual model, api_key: the budget ladder, at and around each boundary
        ("claude-sonnet-4-5", "api_key", "minimal", 1024, False, True),
        ("claude-sonnet-4-5", "api_key", "minimal", 1025, False, False),
        ("claude-sonnet-4-5", "api_key", "low", 1024, False, True),
        ("claude-sonnet-4-5", "api_key", "low", 1025, False, False),
        ("claude-sonnet-4-5", "api_key", "medium", 2048, False, True),
        ("claude-sonnet-4-5", "api_key", "medium", 2049, False, False),
        ("claude-sonnet-4-5", "api_key", "high", 4096, False, True),
        ("claude-sonnet-4-5", "api_key", "high", 4097, False, False),
        # tools do not help without oauth
        ("claude-sonnet-4-5", "api_key", "high", 128, True, True),
        # oauth needs BOTH the honoring model and tools
        ("claude-sonnet-4-5", "oauth", "high", 128, True, False),
        ("claude-sonnet-4-5", "oauth", "high", 128, False, True),
        ("claude-haiku-4-5", "oauth", "high", 128, True, True),
        ("claude-haiku-4-5", "api_key", "high", 128, False, True),
        # adaptive models are never constrained
        ("claude-opus-4-8", "api_key", "high", 1, False, False),
        ("claude-opus-4-7", "oauth", "high", 1, False, False),
        ("claude-sonnet-4-6", "api_key", "high", 1, False, False),
        # non-triggers
        ("claude-sonnet-4-5", "api_key", "none", 1, False, False),
        ("claude-sonnet-4-5", "api_key", None, 1, False, False),
        ("claude-sonnet-4-5", "api_key", "high", None, False, False),
    ],
)
def test_the_decision_procedure(
    model: str,
    auth_mode: AuthMode,
    effort: str | None,
    max_tokens: int | None,
    tools: bool,
    conflicts: bool,
) -> None:
    body: dict[str, Any] = {}
    if effort is not None:
        body["reasoning_effort"] = effort
    if max_tokens is not None:
        body["max_tokens"] = max_tokens
    if tools:
        body["tools"] = _TOOLS

    def _run() -> None:
        raise_on_thinking_conflict(body, model=f"anthropic/{model}", auth_mode=auth_mode)

    if conflicts:
        with pytest.raises(IncompatibleParametersError) as excinfo:
            _run()
        assert excinfo.value.paths == ("max_tokens", "reasoning_effort")
    else:
        _run()


def test_an_empty_tools_array_is_not_tool_use() -> None:
    # An empty array is a syntactically valid `tools` value that engages no tool
    # at all, so it cannot bring interleaved thinking into effect.
    with pytest.raises(IncompatibleParametersError):
        raise_on_thinking_conflict(
            {"reasoning_effort": "high", "max_tokens": 128, "tools": []},
            model="anthropic/claude-sonnet-4-5",
            auth_mode="oauth",
        )


def test_an_unregistered_model_is_not_constrained() -> None:
    # The table is a closed world of REGISTERED models. An id it does not name is
    # left alone rather than guessed at — guessing "manual" would refuse a legal
    # request on a model nobody reviewed.
    raise_on_thinking_conflict(
        {"reasoning_effort": "high", "max_tokens": 1},
        model="anthropic/claude-something-new",
        auth_mode="api_key",
    )


# --- the tables are DERIVED, and drift turns the gate red ----------------------


def test_the_budget_table_matches_the_installed_transform() -> None:
    # INVARIANT: the table is not a guess — it is what the INSTALLED litellm
    # AnthropicConfig actually emits. Pinning it here means a litellm upgrade that
    # changes the mapping fails this test instead of silently drifting the
    # gateway's idea of when the constraint applies.
    from litellm.llms.anthropic.chat.transformation import AnthropicConfig

    settings = AnthropicPluginSettings()
    registered = [entry.model_name for entry in settings.models]
    efforts = [value for value in (REASONING_EFFORT_SCHEMA.enum or ()) if value != "none"]

    manual: dict[str, dict[str, int]] = {}
    for model in registered:
        for effort in efforts:
            mapped = AnthropicConfig._map_reasoning_effort(effort, model)
            assert mapped is not None
            budget = mapped.get("budget_tokens")
            if budget is None:
                assert mapped.get("type") == "adaptive"
                continue
            assert mapped.get("type") == "enabled"
            manual.setdefault(model, {})[effort] = budget

    assert set(manual) == MANUAL_THINKING_MODELS
    for model in manual:
        assert manual[model] == MANUAL_THINKING_BUDGETS, model


def test_disabling_thinking_really_emits_no_budget() -> None:
    from litellm.llms.anthropic.chat.transformation import AnthropicConfig

    for model in MANUAL_THINKING_MODELS:
        assert AnthropicConfig._map_reasoning_effort("none", model) is None


def test_litellm_raises_max_tokens_only_when_the_caller_omits_it() -> None:
    # The premise behind "an absent max_tokens never conflicts". If litellm ever
    # stops auto-raising, this fails and the omission branch must be revisited.
    import litellm

    with_max = litellm.get_optional_params(
        model="claude-sonnet-4-5",
        custom_llm_provider="anthropic",
        reasoning_effort="high",
        max_tokens=128,
    )
    without_max = litellm.get_optional_params(
        model="claude-sonnet-4-5",
        custom_llm_provider="anthropic",
        reasoning_effort="high",
    )

    assert with_max["max_tokens"] == 128
    assert with_max["thinking"]["budget_tokens"] == 4096
    assert without_max["max_tokens"] > without_max["thinking"]["budget_tokens"]


def test_every_constrained_model_is_registered() -> None:
    registered = {entry.model_name for entry in AnthropicPluginSettings().models}

    assert MANUAL_THINKING_MODELS <= registered
    assert INTERLEAVED_BETA_MODELS <= MANUAL_THINKING_MODELS


def test_the_interleaved_beta_is_actually_sent_on_the_oauth_path() -> None:
    # The exemption's other premise. If this header ever leaves the OAuth
    # settings, the OAuth branch stops being justified.
    assert "interleaved-thinking-2025-05-14" in AnthropicPluginSettings().beta


def test_the_conflict_fields_project_to_their_request_paths() -> None:
    # The seam reads the PROJECTED body, so it can only see these fields while
    # their rule target equals their request path. If a future rule relocated
    # max_tokens, the check would silently stop firing — this fails first.
    rules = {
        rule.request_path: rule
        for rule in anthropic_chat_parameter_rules(model="anthropic/claude-sonnet-4-5")
    }

    for path in ("reasoning_effort", "max_tokens", "tools"):
        assert rules[path].target == path
