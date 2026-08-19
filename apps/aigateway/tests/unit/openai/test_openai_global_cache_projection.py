"""OME-884 — direct OpenAI's PURE global-cache projection and its model-ID contract.

FEATURE: one global exact-request cache (OME-305). OME-864 shipped direct `openai/*`
dispatch with the base class's safe-by-default ``CacheBypass``, so no direct OpenAI
request has ever been cacheable. This suite pins the projection that changes that.

STORY: as a benchmark operator I re-run a suite against `openai/*` and the identical
calls are served from the first run's stored responses — including from a second
account, and including for a model I addressed directly without seeding it.

INVARIANT under test: the projection is a PURE, TOTAL function of the request body.
Everything output-affecting that the boundary adds is either described in ``prepared``
(JSON-safe) or folded into ``GLOBAL_CACHE_ADAPTER_REVISION`` (everything else).
"""

from __future__ import annotations

import copy
from collections.abc import Iterator, Mapping
from typing import Any

import litellm
import pytest
from litellm.secret_managers.main import get_secret_bool
from pydantic import ValidationError

from aigateway.core.cache_ports import PROJECTION_BYPASS_REASON, CacheBypass
from aigateway.core.request_cache.global_controls import parse_global_cache_controls
from aigateway.core.request_cache.global_keys import (
    GlobalCacheKeyResult,
    build_global_cache_key,
)
from aigateway.core.request_cache.global_plan import build_global_cache_plan
from aigateway.plugins.openai_provider import global_cache as global_cache_module
from aigateway.plugins.openai_provider.global_cache import (
    GLOBAL_CACHE_ADAPTER_REVISION,
    gateway_dispatch_controls,
    project_global_cache_request,
)
from aigateway.plugins.openai_provider.parameters import openai_chat_parameter_rules
from aigateway.plugins.openai_provider.plugin import (
    _EXPERIMENTAL_HANDLER_ENV,
    PLUGIN,
    litellm_env_flag_is_true,
)
from aigateway.plugins.openai_provider.settings import (
    OFFICIAL_API_BASE,
    OpenAIPluginSettings,
    is_route_valid_model_id,
)

# A model the deployment seeds, and one that is route-valid but deliberately NOT in
# ``default_models`` — the whole point of OME-884 is that these two behave identically
# for cache purposes. The catalog publishes; it does not admit.
_SEEDED = "openai/gpt-5.6-sol"
_UNLISTED = "openai/gpt-4o-2024-11-20"

_MALFORMED_OR_FOREIGN = [
    "openai/",
    "openai/gpt/5",
    "openai/gpt 5",
    "openai/gpt-5?variant=x",
    "openai/https://example.invalid",
    "openai/-leading-dash",
    "openai/gpt-五",
    f"openai/{'x' * 129}",
    "openrouter/openai/gpt-4o",
    "codex/gpt-5",
    "gpt-4o",
    "",
]


def _body(model: str, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": "how many primes below one hundred?"}],
    }
    body.update(overrides)
    return body


def _key(body: dict[str, Any]) -> GlobalCacheKeyResult:
    built = build_global_cache_key(
        provider="openai",
        body=body,
        rules=openai_chat_parameter_rules(model=str(body.get("model")), auth_type=None),
        projection=project_global_cache_request,
        provider_auth_modes=("api_key",),
    )
    assert isinstance(built, GlobalCacheKeyResult), built
    return built


# --- the shared model-ID predicate -------------------------------------------


def test_the_shared_predicate_accepts_exactly_what_settings_validation_accepts() -> None:
    """ONE grammar, four readers (settings, preparation, projection, parameter rules).

    INVARIANT: OME-884 does not widen OME-864's bounded ASCII grammar. It only stops
    the grammar's verdict from being second-guessed by catalog membership.
    """
    for model in (*OpenAIPluginSettings().default_models, _UNLISTED, "openai/o3"):
        assert is_route_valid_model_id(model) is True, model
        # The settings validator is the other reader; the two may never disagree.
        assert OpenAIPluginSettings(default_models=[model]).default_models == [model]

    for model in _MALFORMED_OR_FOREIGN:
        assert is_route_valid_model_id(model) is False, model
        with pytest.raises(ValidationError):
            OpenAIPluginSettings(default_models=[model])


def test_the_predicate_is_total_for_a_non_string_model() -> None:
    # The cache stage hands the projection whatever the caller sent; a body whose
    # ``model`` is a number or absent must be a bypass, never a TypeError.
    for value in (None, 7, ["openai/gpt-4o"], {"model": "openai/gpt-4o"}, b"openai/gpt-4o"):
        assert is_route_valid_model_id(value) is False, value


# --- the projection ------------------------------------------------------------


def test_the_projection_returns_the_closed_member_set_the_core_requires() -> None:
    # ``global_eligibility._projected`` bypasses on an unrecognized member set, so an
    # extra or missing key here would silently un-cache the whole provider.
    projected = project_global_cache_request(_body(_SEEDED))

    assert isinstance(projected, dict)
    assert set(projected) == {"resolved_model", "provider_adapter_revision", "prepared"}
    assert projected["provider_adapter_revision"] == GLOBAL_CACHE_ADAPTER_REVISION


def test_the_resolved_model_is_the_upstream_id_the_wire_actually_carries() -> None:
    # LiteLLM strips its ``openai/`` provider prefix exactly once at the wire — pinned
    # by ``test_openai_dispatch``'s MockTransport payload assertion — so the upstream
    # remainder is what OpenAI resolves. The gateway-prefixed string is still keyed
    # separately as ``requested_model`` by the core.
    projected = project_global_cache_request(_body(_SEEDED))

    assert isinstance(projected, dict)
    assert projected["resolved_model"] == "gpt-5.6-sol"


def test_the_projection_describes_every_output_affecting_constant_dispatch_adds() -> None:
    """The whole JSON-safe half of the adapter contract, spelled out.

    INVARIANT: each of these is a value the gateway adds WITHOUT the caller asking, and
    each of them changes what OpenAI returns or how the answer is produced. A constant
    the boundary adds but the key cannot see is a wrong-hit waiting for the day it
    changes.
    """
    projected = project_global_cache_request(_body(_SEEDED))

    assert isinstance(projected, dict)
    assert projected["prepared"] == {
        "api_base": OFFICIAL_API_BASE,
        "caching": False,
        "cache": {"no-cache": True, "no-store": True},
        "num_retries": 0,
        "max_retries": 0,
        "_skip_responses_api_bridge": True,
    }
    # ONE table, two readers: the projection and ``chat_completion``. Sharing it is what
    # makes "the projection describes what dispatch sends" true by construction rather
    # than by two lists a maintainer must remember to edit together.
    assert projected["prepared"] == gateway_dispatch_controls()


def test_an_unlisted_route_valid_model_projects_exactly_like_a_seeded_one() -> None:
    """The catalog publishes; it does not admit (owner-approved MVP semantics).

    ``default_models`` is the bootstrap ``/v1/models`` catalog. A model absent from it
    must project — and therefore cache — identically apart from its own identity.
    """
    assert _UNLISTED not in OpenAIPluginSettings().default_models

    seeded = project_global_cache_request(_body(_SEEDED))
    unlisted = project_global_cache_request(_body(_UNLISTED))

    assert isinstance(seeded, dict) and isinstance(unlisted, dict)
    assert seeded["resolved_model"] != unlisted["resolved_model"]
    assert seeded["provider_adapter_revision"] == unlisted["provider_adapter_revision"]
    assert seeded["prepared"] == unlisted["prepared"]


@pytest.mark.parametrize("model", _MALFORMED_OR_FOREIGN)
def test_a_malformed_or_foreign_model_id_bypasses_rather_than_raising(model: str) -> None:
    # INVARIANT: a projection may never fail a request, only decline to key it. A
    # malformed id must therefore reach the local invalid-model path with NO cache read
    # and NO cache write, which a bypass is exactly what delivers.
    projected = project_global_cache_request(_body(model))

    assert projected == CacheBypass(reason=PROJECTION_BYPASS_REASON)


def test_a_body_without_a_model_at_all_bypasses() -> None:
    assert project_global_cache_request({"messages": []}) == CacheBypass(
        reason=PROJECTION_BYPASS_REASON
    )


def test_the_projection_is_deterministic_and_never_mutates_the_body() -> None:
    body = _body(_SEEDED, max_tokens=7, system="be terse")
    snapshot = copy.deepcopy(body)

    first = project_global_cache_request(body)
    second = project_global_cache_request(body)

    assert first == second
    assert body == snapshot


def test_the_projection_hands_back_fresh_containers_every_call() -> None:
    # The core hashes ``prepared`` whole and does not copy it. Sharing one mutable dict
    # across requests would let a later reader of the returned mapping alter the key
    # material of every subsequent request in the process.
    first = project_global_cache_request(_body(_SEEDED))
    second = project_global_cache_request(_body(_SEEDED))

    assert isinstance(first, dict) and isinstance(second, dict)
    assert first["prepared"] is not second["prepared"]
    assert first["prepared"]["cache"] is not second["prepared"]["cache"]


# --- what the projection buys: real keys --------------------------------------


def test_prepared_is_json_safe_and_a_key_is_actually_built() -> None:
    """The projection is only worth something if the key builder accepts it.

    ``_require_json_safe`` refuses an ``Omit()`` sentinel, an SDK client, a non-string
    object key or a non-finite number — which is exactly why the transport guarantees
    that cannot be normalized live in the adapter revision instead of in ``prepared``.
    """
    built = _key(_body(_SEEDED))

    assert built.provider == "openai"
    assert built.model == _SEEDED
    assert len(built.key_hash) == 64


def test_an_unlisted_model_is_keyable_and_never_collides_with_a_seeded_one() -> None:
    assert _key(_body(_UNLISTED)).key_hash != _key(_body(_SEEDED)).key_hash


def test_different_messages_never_collide() -> None:
    other = _body(_SEEDED)
    other["messages"] = [{"role": "user", "content": "how many primes below two hundred?"}]

    assert _key(other).key_hash != _key(_body(_SEEDED)).key_hash


def test_an_absent_top_level_system_is_distinguishable_from_a_present_one() -> None:
    # Prompt material is hashed verbatim and "absent" is an unforgeable marker, so a
    # stored system prompt that later disappears cannot replay the answer it shaped.
    with_system = _key(_body(_SEEDED, system="be terse"))
    without_system = _key(_body(_SEEDED))
    empty_system = _key(_body(_SEEDED, system=""))

    assert len({with_system.key_hash, without_system.key_hash, empty_system.key_hash}) == 3


def test_bumping_the_adapter_revision_abandons_every_stored_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The revision is INSIDE the hashed material — that is what makes a bump safe.

    INVARIANT: rows have no expiry and survive deployments, so a change to what this
    boundary sends for an unchanged request MUST be accompanied by a bump. This proves
    a bump actually abandons the generation rather than re-serving it.
    """
    before = _key(_body(_SEEDED))
    monkeypatch.setattr(
        global_cache_module, "GLOBAL_CACHE_ADAPTER_REVISION", f"{GLOBAL_CACHE_ADAPTER_REVISION}-x"
    )

    assert _key(_body(_SEEDED)).key_hash != before.key_hash


def test_a_malformed_model_yields_no_key_at_all() -> None:
    built = build_global_cache_key(
        provider="openai",
        body=_body("openai/gpt 5"),
        rules=openai_chat_parameter_rules(model="openai/gpt 5", auth_type=None),
        projection=project_global_cache_request,
        provider_auth_modes=("api_key",),
    )

    assert built == CacheBypass(reason=PROJECTION_BYPASS_REASON)


# --- the catalog is not an allowlist for readiness either ----------------------


def test_a_route_valid_validation_model_need_not_be_in_the_bootstrap_catalog() -> None:
    # OME-864 required membership; OME-884 removes that coupling in settings so an
    # operator can probe readiness with a model they do not publish.
    settings = OpenAIPluginSettings(default_models=[_SEEDED], validation_model="openai/gpt-5-nano")

    assert settings.validation_model == "openai/gpt-5-nano"
    assert settings.validation_model not in settings.default_models


def test_a_malformed_validation_model_is_still_refused() -> None:
    with pytest.raises(ValidationError):
        OpenAIPluginSettings(default_models=[_SEEDED], validation_model="openai/gpt 5")
    with pytest.raises(ValidationError):
        OpenAIPluginSettings(default_models=[_SEEDED], validation_model="openrouter/openai/gpt-5")


# --- participation: the deployment-local gate, kept OUT of the key -------------
#
# WHY these live beside the projection tests rather than with dispatch: participation
# and projection are the two halves of ONE decision — may this provider take part, and
# what would its key be. Keeping them in one file is what makes the asymmetry between
# them (the gate may read the environment; the projection may not) readable in one pass.


def _safe_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralize every ambient global this provider fails closed on."""
    monkeypatch.delenv("OPENAI_CUSTOM_HEADERS", raising=False)
    monkeypatch.delenv("EXPERIMENTAL_OPENAI_BASE_LLM_HTTP_HANDLER", raising=False)
    monkeypatch.setattr(litellm, "secret_manager_client", None)
    monkeypatch.setattr(litellm, "model_alias_map", {})
    monkeypatch.setattr(litellm, "headers", None)
    monkeypatch.setattr(litellm, "model_fallbacks", None)
    monkeypatch.setattr(litellm, "proxy_auth", None)
    monkeypatch.setattr(litellm, "drop_params", False)


_UNSAFE_RUNTIME_STATES: list[tuple[str, Any]] = [
    ("openai_config", lambda mp: mp.setattr(litellm.OpenAIConfig, "temperature", 1)),
    ("custom_headers", lambda mp: mp.setenv("OPENAI_CUSTOM_HEADERS", '{"X-Leak":"ambient"}')),
    (
        "experimental_handler",
        lambda mp: mp.setenv("EXPERIMENTAL_OPENAI_BASE_LLM_HTTP_HANDLER", "true"),
    ),
    ("secret_manager", lambda mp: mp.setattr(litellm, "secret_manager_client", object())),
    ("headers", lambda mp: mp.setattr(litellm, "headers", {"X-Leak": "ambient"})),
    ("fallbacks", lambda mp: mp.setattr(litellm, "model_fallbacks", ["openai/gpt-4o-mini"])),
    ("proxy_auth", lambda mp: mp.setattr(litellm, "proxy_auth", object())),
    ("drop_params", lambda mp: mp.setattr(litellm, "drop_params", True)),
    ("callbacks", lambda mp: mp.setattr(litellm, "callbacks", [object()])),
    ("pre_call_rules", lambda mp: mp.setattr(litellm, "pre_call_rules", [object()])),
]


def test_a_safe_runtime_participates(monkeypatch: pytest.MonkeyPatch) -> None:
    # Anti-vacuity for every refusal below: without it a hook that returned False
    # unconditionally would pass the whole parametrized sweep.
    _safe_runtime(monkeypatch)

    assert PLUGIN.participates_in_global_cache(_SEEDED) is True
    assert PLUGIN.participates_in_global_cache(_UNLISTED) is True


@pytest.mark.parametrize(
    "name,poison", _UNSAFE_RUNTIME_STATES, ids=[name for name, _ in _UNSAFE_RUNTIME_STATES]
)
def test_unsafe_ambient_state_refuses_participation(
    monkeypatch: pytest.MonkeyPatch, name: str, poison: Any
) -> None:
    """INVARIANT: the cache is a SECOND route to this provider's answers.

    A stored row needs no model entry and no credential to be replayed, and the cache
    stage runs ahead of both — so the dispatch-side 503 cannot protect it. Every state
    that makes DISPATCH unsafe must therefore also stop the READ, or a poisoned runtime
    would keep serving rows the dispatch guard refuses to refill.
    """
    _safe_runtime(monkeypatch)
    poison(monkeypatch)

    assert PLUGIN.participates_in_global_cache(_SEEDED) is False, name


def test_an_ambient_alias_stands_down_only_for_the_model_it_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deliberate asymmetry: an alias is a per-MODEL hazard, not a provider-wide one.

    An entry in ``litellm.model_alias_map`` silently redirects one id to another, so a
    row stored for the requested id would be replayed while a miss dispatched something
    else. That is a wrong-hit class for THAT model — and no reason at all to abandon
    every other model's cache, which is what a provider-wide refusal would do.
    """
    _safe_runtime(monkeypatch)
    monkeypatch.setattr(litellm, "model_alias_map", {_SEEDED: "openai/gpt-4o-mini"})

    assert PLUGIN.participates_in_global_cache(_SEEDED) is False
    assert PLUGIN.participates_in_global_cache(_UNLISTED) is True
    assert PLUGIN.participates_in_global_cache("openai/gpt-4o") is True


def test_participation_is_total_for_a_non_string_or_hostile_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The gate runs before the request's shape is adjudicated, so it must survive a
    # model that is not a string — and a ``model_alias_map`` that is not a mapping.
    _safe_runtime(monkeypatch)
    for value in (None, 7, ["openai/gpt-4o"], {"a": 1}):
        assert PLUGIN.participates_in_global_cache(value) is True

    monkeypatch.setattr(litellm, "model_alias_map", "not-a-mapping")
    assert PLUGIN.participates_in_global_cache(_SEEDED) is True


@pytest.mark.parametrize(
    "value",
    [None, "true", "TRUE", "True", "  true  ", "false", "FALSE", "yes", "1", "0", "", "on"],
)
def test_the_flag_helper_matches_installed_litellm_semantics(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    """Parity with the ACTUAL branch LiteLLM takes, measured rather than assumed.

    ``get_secret_bool`` -> ``str_to_bool`` recognizes only ``"true"``/``"false"`` after
    ``.strip().lower()`` and answers ``None`` for everything else, INCLUDING unset. The
    secret-manager branch is a different code path entirely, which is why a configured
    secret-manager client is its own refusal above rather than something this helper
    tries to model.
    """
    monkeypatch.setattr(litellm, "secret_manager_client", None)
    if value is None:
        monkeypatch.delenv(_EXPERIMENTAL_HANDLER_ENV, raising=False)
    else:
        monkeypatch.setenv(_EXPERIMENTAL_HANDLER_ENV, value)

    assert litellm_env_flag_is_true(value) is (get_secret_bool(_EXPERIMENTAL_HANDLER_ENV) is True)


# --- the plugin's own hooks ----------------------------------------------------


def test_the_plugin_exposes_the_module_projection(monkeypatch: pytest.MonkeyPatch) -> None:
    _safe_runtime(monkeypatch)
    body = _body(_SEEDED)

    assert PLUGIN.global_cache_projection(body) == project_global_cache_request(body)


def test_a_cache_hit_certifies_no_historical_accounting_evidence() -> None:
    """OME-884: an explicit ``None``, not a missing attribute.

    ``attach_hit_metadata`` reaches the mapper through ``getattr`` inside a ``try``, so
    NOT implementing the hook logs "cache-reference mapper failed" on every hit — an
    operator-visible warning describing a failure that never happened. Direct OpenAI has
    no accounting strategy at all, so the truthful answer is "no evidence", quietly.
    """
    assert (
        PLUGIN.cache_reference_from_cached_response(
            {"choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}]}
        )
        is None
    )


# --- OME-884 Unit 3: the keyed ``max_tokens`` contract -------------------------
#
# WHY these proofs run through ``build_global_cache_plan`` rather than calling the key
# builder directly: the plan is what the route actually uses, so it exercises the real
# provider auth modes, the real participation gate, the real rule table and the real
# projection together. A key proof that bypassed it could stay green while the request
# path bypassed every time.


def _plan(body: dict[str, Any]) -> Any:
    return build_global_cache_plan(
        body=body,
        plugin=PLUGIN,
        controls=parse_global_cache_controls({}),
        cache_enabled=True,
    )


def _planned_key(body: dict[str, Any]) -> str:
    planned = _plan(body)
    assert isinstance(planned, GlobalCacheKeyResult), planned
    return planned.key_hash


@pytest.mark.parametrize("model", [_SEEDED, _UNLISTED, "openai/gpt-4o", "openai/o3"])
def test_max_tokens_is_keyed_for_every_route_valid_model(model: str) -> None:
    """Promoted from ``bypass`` — and only now that a real projection backs it.

    A keyed rule on a provider with no projection is unobservable: the missing
    projection bypasses the request regardless of what its rules declare. That is why
    the promotion had to wait for the projection rather than shipping with OME-864.
    """
    rules = PLUGIN.chat_parameter_rules(model=model, auth_type=None)

    assert len(rules) == 1
    assert rules[0].request_path == "max_tokens"
    assert rules[0].cache_behavior == "keyed"
    # INVARIANT (ruling 59): the pre-auth key cannot honor a mode-restricted promise, so
    # a keyed rule must apply in EVERY mode the provider offers.
    assert set(PLUGIN.available_auth_modes()) <= set(rules[0].applicable_auth_modes)


def test_a_request_carrying_max_tokens_is_now_keyed_rather_than_bypassed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _safe_runtime(monkeypatch)

    assert _planned_key(_body(_SEEDED, max_tokens=64))


def test_equal_effective_ceilings_share_one_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    # The body-wins profile-default merge runs BEFORE the cache stage, so by the time a
    # plan is built there is no difference between "the caller sent 64" and "the profile
    # defaulted to 64". One upstream call, one row.
    _safe_runtime(monkeypatch)

    assert _planned_key(_body(_SEEDED, max_tokens=64)) == _planned_key(
        _body(_SEEDED, max_tokens=64)
    )


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ({"max_tokens": 64}, {"max_tokens": 65}),
        ({"max_tokens": 64}, {}),
    ],
)
def test_different_effective_ceilings_never_collide(
    monkeypatch: pytest.MonkeyPatch, left: dict[str, Any], right: dict[str, Any]
) -> None:
    """The wrong-hit class this promotion exists to close.

    ``chat_cache_stage._is_a_whole_answer`` STORES a ``finish_reason: "length"``
    response, on the stated grounds that a truncation is the correct answer to the
    request that asked for it. That is sound ONLY while the ceiling is keyed: with
    ``bypass``, a caller asking for 4000 tokens would be served the answer that stopped
    at 20. An absent ceiling is its own case — it is not "unlimited equals some number".
    """
    _safe_runtime(monkeypatch)

    assert _planned_key(_body(_SEEDED, **left)) != _planned_key(_body(_SEEDED, **right))


def test_the_same_ceiling_on_two_models_never_collides(monkeypatch: pytest.MonkeyPatch) -> None:
    # LiteLLM maps the ceiling to ``max_tokens`` for GPT-4/4o and to
    # ``max_completion_tokens`` for GPT-5/o-series. Two spellings, one meaning — and the
    # model is keyed independently, so the difference can never be papered over.
    _safe_runtime(monkeypatch)

    assert _planned_key(_body("openai/gpt-4o", max_tokens=64)) != _planned_key(
        _body(_SEEDED, max_tokens=64)
    )


def test_an_unlisted_model_reaches_a_key_through_the_real_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # End to end through the plan: participation, rules, auth modes and projection all
    # have to agree before an unlisted model produces a key at all.
    _safe_runtime(monkeypatch)

    assert _planned_key(_body(_UNLISTED, max_tokens=8)) != _planned_key(
        _body(_SEEDED, max_tokens=8)
    )


def test_a_malformed_model_produces_no_plan_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _safe_runtime(monkeypatch)

    assert _plan(_body("openai/gpt 5", max_tokens=8)) == CacheBypass(
        reason=PROJECTION_BYPASS_REASON
    )


def test_an_unsafe_runtime_produces_no_plan_key(monkeypatch: pytest.MonkeyPatch) -> None:
    # The participation gate reached through the real plan, not called directly.
    _safe_runtime(monkeypatch)
    monkeypatch.setattr(litellm, "headers", {"X-Leak": "ambient"})

    assert _plan(_body(_SEEDED, max_tokens=8)) == CacheBypass(reason=PROJECTION_BYPASS_REASON)


def test_a_caller_opt_out_bypasses_a_request_that_would_otherwise_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _safe_runtime(monkeypatch)
    body = _body(_SEEDED, max_tokens=8)
    controls = parse_global_cache_controls({"cache": {"use-cache": False}})

    decision = build_global_cache_plan(
        body=body, plugin=PLUGIN, controls=controls, cache_enabled=True
    )

    assert isinstance(decision, CacheBypass)
    assert decision.reason == controls.bypass_reason


# --- OME-884 review: a RAISING ambient read is itself an unsafe runtime ---------
#
# WHY this is a distinct class from the poisons above: those set a value the guard then
# READS successfully. Here the read itself explodes. The guard's docstring promised
# "fail CLOSED and never raise", but every read was only defensive about a MISSING
# attribute (``getattr(..., None)``) — not about one that answers by raising. A hostile
# or merely broken LiteLLM global therefore escaped as an ordinary exception.


class _ExplodingAliasMap(Mapping[str, str]):
    """A ``model_alias_map`` whose membership test raises instead of answering."""

    def __contains__(self, key: object) -> bool:
        raise RuntimeError("hostile alias map")

    def __getitem__(self, key: str) -> str:
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return iter(())

    def __len__(self) -> int:
        return 0


class _ExplodingTruthiness:
    """An ambient global that cannot even be asked whether it is set."""

    def __bool__(self) -> bool:
        raise RuntimeError("hostile truthiness")


def _raising_get_config() -> dict[str, Any]:
    raise RuntimeError("ambient config read exploded")


_RAISING_AMBIENT_READS: list[tuple[str, Any]] = [
    (
        "get_config",
        lambda mp: mp.setattr(
            litellm.OpenAIConfig, "get_config", staticmethod(_raising_get_config)
        ),
    ),
    ("alias_lookup", lambda mp: mp.setattr(litellm, "model_alias_map", _ExplodingAliasMap())),
    ("truthiness", lambda mp: mp.setattr(litellm, "headers", _ExplodingTruthiness())),
    ("callback_truthiness", lambda mp: mp.setattr(litellm, "callbacks", _ExplodingTruthiness())),
]


@pytest.mark.parametrize(
    "name,poison", _RAISING_AMBIENT_READS, ids=[name for name, _ in _RAISING_AMBIENT_READS]
)
def test_a_raising_ambient_read_refuses_participation(
    monkeypatch: pytest.MonkeyPatch, name: str, poison: Any
) -> None:
    """INVARIANT: unreadable is treated exactly like unsafe.

    The gate cannot certify a runtime it was unable to inspect, so the only sound answer
    is to stand down. Letting the exception escape instead was doubly wrong: it broke the
    hook's own documented totality, and it moved the decision to
    ``build_global_cache_plan``'s catch-all — which reports the outcome as this
    provider's projection bypass whether or not that is what actually happened.
    """
    _safe_runtime(monkeypatch)
    poison(monkeypatch)

    assert PLUGIN.participates_in_global_cache(_SEEDED) is False, name
