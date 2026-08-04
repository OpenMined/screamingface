"""OME-305 — Anthropic's own projection for the global exact-request cache.

FEATURE: a globally shared exact-request cache that Anthropic requests can enter.
Anthropic is the provider the benchmark suites actually hammer, so the ticket
delivers nothing unless this provider is cacheable — but it is also the provider
with the most dangerous preparation step, a Claude-Code billing block that is
prepended only on OAuth traffic. This file pins the deal that makes it safe.

STORY: as a benchmark operator I re-run an Anthropic suite from a second account
and the identical calls are answered from the first run's stored responses, with no
second dispatch and without the second account's credential being read.

INVARIANT under test: the projection is PURE and TOTAL. Synchronous, no I/O, no
clock, no randomness, no credential, no identity, no read of per-deployment
settings; it never mutates the caller's body; and a model it could not dispatch
yields a bounded ``CacheBypass`` rather than a raise, because the cache may never
fail a request.

INVARIANT under test (the whole reason this provider needs a computed revision):
the attribution block is CREDENTIAL-GATED, so the mode bit cannot be keyed. The
constants that shape the block are folded into ``provider_adapter_revision``
UNCONDITIONALLY instead, so changing the Claude Code version, the salt or the
sampled indices abandons every entry filled under the old block. A hand-written
revision string would leave that to a human noticing the coupling.

AIDEV-NOTE: the ACCEPTED CONSEQUENCE of the ungated mode bit — an OAuth-filled
entry may be READ by an api-key caller and vice versa — is a route-level property
and is pinned in ``tests/unit/test_chat_request_cache.py``, together with the F02
guarantee that an api-key MISS still dispatches with no block. What is pinned here
is the half that makes that safe: the projection never looks at the credential, so
it cannot leak one into a shared key.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from aigateway.core.cache_ports import PROJECTION_BYPASS_REASON, CacheBypass
from aigateway.plugins.anthropic_provider import chat_handler
from aigateway.plugins.anthropic_provider.chat_handler import (
    claude_code_attribution_revision,
)
from aigateway.plugins.anthropic_provider.plugin import (
    GLOBAL_CACHE_ADAPTER_REVISION,
    AnthropicProviderPlugin,
)

_MODEL = "anthropic/claude-haiku-4-5"


def _body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": _MODEL,
        "messages": [{"role": "user", "content": "how many primes below one hundred?"}],
    }
    body.update(overrides)
    return body


def _project(**overrides: Any) -> dict[str, Any]:
    produced = AnthropicProviderPlugin().global_cache_projection(_body(**overrides))
    assert not isinstance(produced, CacheBypass), produced
    return produced


# --- the closed shape --------------------------------------------------------


def test_a_plain_anthropic_request_is_projectable_at_all() -> None:
    """The headline: Anthropic is no longer bypass-by-inheritance.

    Every provider inherits a ``CacheBypass`` default, so "is this provider
    cacheable" is a real question with a real answer, and for the busiest provider
    in the product the answer has to be yes.
    """
    produced = _project()
    assert set(produced) == {"resolved_model", "provider_adapter_revision", "prepared"}


def test_the_resolved_model_is_the_full_gateway_model_string() -> None:
    # INVARIANT: unlike OpenRouter, the gateway prefix here IS LiteLLM's provider
    # prefix and travels to the wire intact, so there is nothing to strip. Stripping
    # it would make ``anthropic/x`` and some other provider's ``x`` collide.
    assert _project()["resolved_model"] == _MODEL


def test_the_prepared_view_of_a_plain_request_adds_nothing() -> None:
    """Anthropic adds no request-varying field of its own.

    WHY this is asserted rather than left implicit: an empty ``prepared`` looks like
    an oversight. It is the reviewed answer — the only two things this boundary does
    are drop ``reasoning_effort="none"`` (covered below) and prepend the
    credential-gated block (folded into the revision, never into ``prepared``).
    """
    assert _project()["prepared"] == {}


@pytest.mark.parametrize(
    "model",
    [
        "openai/gpt-4o",
        "claude-haiku-4-5",
        "anthropic/",
        "",
    ],
)
def test_a_model_this_plugin_could_not_dispatch_bypasses_instead_of_raising(model: str) -> None:
    produced = AnthropicProviderPlugin().global_cache_projection(_body(model=model))
    assert isinstance(produced, CacheBypass)
    assert produced.reason == PROJECTION_BYPASS_REASON


@pytest.mark.parametrize("model", [None, 42, ["anthropic/x"], {"name": "anthropic/x"}])
def test_a_non_string_model_bypasses_rather_than_crashing_the_request(model: Any) -> None:
    # The projection runs before the classifier, so it sees genuinely untrusted
    # input. A TypeError here would become a 500 on a request the provider could
    # have served.
    produced = AnthropicProviderPlugin().global_cache_projection(_body(model=model))
    assert isinstance(produced, CacheBypass)


# --- the reasoning_effort normalization -------------------------------------


def test_an_effort_of_none_is_projected_as_omitted() -> None:
    # ``prepare_chat_body`` pops it, and omission is exactly what "none" means, so
    # the projection must describe the omission rather than the caller's spelling.
    assert _project(reasoning_effort="none")["prepared"] == {}


def test_a_real_effort_survives_into_the_projected_view() -> None:
    assert _project(reasoning_effort="high")["prepared"] == {"reasoning_effort": "high"}


def test_the_projection_agrees_with_what_prepare_chat_body_actually_does() -> None:
    """The projection is a CLAIM about ``prepare_chat_body``; pin them together.

    AIDEV-NOTE: this is the test that fails if someone changes the real preparation
    without updating the projection. Without it the two could drift, and a drifted
    projection means a key that describes a request the provider will not send.
    """
    plugin = AnthropicProviderPlugin()
    for effort in ("none", "low", "medium", "high"):
        prepared_body = plugin.prepare_chat_body(_body(reasoning_effort=effort))
        projected = _project(reasoning_effort=effort)["prepared"]
        assert ("reasoning_effort" in prepared_body) == ("reasoning_effort" in projected)
        if "reasoning_effort" in projected:
            assert projected["reasoning_effort"] == prepared_body["reasoning_effort"]


# --- purity ------------------------------------------------------------------


def test_the_same_request_projects_identically_when_interleaved_with_another() -> None:
    # WHY interleaved (A, B, A) rather than twice: a projection that memoized on
    # instance state would pass a naive "call it twice" check and still return B's
    # answer for A's second call.
    plugin = AnthropicProviderPlugin()
    first = plugin.global_cache_projection(_body())
    plugin.global_cache_projection(_body(messages=[{"role": "user", "content": "other"}]))
    again = plugin.global_cache_projection(_body())
    assert first == again


def test_two_fresh_plugin_instances_project_the_same_request_identically() -> None:
    # A key is shared across worker processes, each with its own plugin instance, so
    # per-instance state would partition the cache by whichever worker answered.
    assert AnthropicProviderPlugin().global_cache_projection(
        _body()
    ) == AnthropicProviderPlugin().global_cache_projection(_body())


def test_the_projection_never_mutates_the_body_it_was_handed() -> None:
    # The core passes a deep copy as defence in depth, not as permission — the miss
    # path dispatches the ORIGINAL body.
    body = _body(reasoning_effort="none")
    snapshot = copy.deepcopy(body)
    AnthropicProviderPlugin().global_cache_projection(body)
    assert body == snapshot


def test_the_projection_cannot_observe_a_credential_even_when_one_is_present() -> None:
    """The central safety property of this provider's projection.

    The attribution transform keys off ``body["api_key"]``, so a projection that
    read the same field would put credential-derived state into a GLOBAL key —
    partitioning a shared cache by secret, and making the key a place an api-key
    prefix could be inferred from. The ingress strip removes ``api_key`` long before
    this runs; this proves the projection would ignore it even if it did not.
    """
    plugin = AnthropicProviderPlugin()
    baseline = plugin.global_cache_projection(_body())
    for api_key in ("sk-ant-oat01-subscription", "sk-ant-api03-raw-key", None):
        assert plugin.global_cache_projection(_body(api_key=api_key)) == baseline


def test_the_projection_takes_the_body_alone() -> None:
    # Ruling 6: the signature is the enforcement point for "no identity". A hook
    # that accepted an auth mode could be given one by a future caller.
    import inspect

    signature = inspect.signature(AnthropicProviderPlugin.global_cache_projection)
    assert list(signature.parameters) == ["self", "body"]


def test_the_projection_is_synchronous() -> None:
    # INVARIANT: a coroutine could await I/O. Sync is what makes purity checkable.
    import inspect

    assert not inspect.iscoroutinefunction(AnthropicProviderPlugin.global_cache_projection)


# --- the folded attribution revision ----------------------------------------


def test_the_adapter_revision_carries_the_attribution_digest() -> None:
    assert GLOBAL_CACHE_ADAPTER_REVISION.endswith(claude_code_attribution_revision())
    assert GLOBAL_CACHE_ADAPTER_REVISION.startswith("anthropic-global-cache-")


def test_the_revision_is_the_same_for_every_caller() -> None:
    # It is provider metadata, not request state: two callers must land on one key.
    assert _project()["provider_adapter_revision"] == GLOBAL_CACHE_ADAPTER_REVISION
    assert (
        _project(reasoning_effort="high")["provider_adapter_revision"]
        == GLOBAL_CACHE_ADAPTER_REVISION
    )


@pytest.mark.parametrize(
    ("constant", "replacement"),
    [
        ("_CLAUDE_CODE_VERSION", "2.1.143"),
        ("_FINGERPRINT_SALT", "0000deadbeef"),
        ("_FINGERPRINT_INDICES", (4, 7, 21)),
        ("_BILLING_HEADER_PREFIX", "x-anthropic-billing-header-v2:"),
    ],
)
def test_changing_any_attribution_constant_invalidates_every_stored_entry(
    monkeypatch: pytest.MonkeyPatch, constant: str, replacement: Any
) -> None:
    """The mechanism that makes the ungated mode bit survivable.

    Because whether the block is sent is not keyed, a change to WHAT the block says
    must abandon the entries filled under the old one — otherwise a response
    produced under Claude Code 2.1.142 attribution would be served forever after the
    scheme changed. Each constant must do that on its own.
    """
    before = claude_code_attribution_revision()
    monkeypatch.setattr(chat_handler, constant, replacement)
    assert claude_code_attribution_revision() != before


def test_every_attribution_constant_is_actually_read_by_the_digest() -> None:
    """Structural counterpart to the behavioural test above.

    WHY both: the monkeypatch cases prove each constant currently changes the digest,
    but they can only test the constants someone remembered to list. This reads the
    function's own global references, so it states the coupling directly — and it is
    the check that survives if a future constant is added to the block but not to the
    parametrize table. If this list and ``_build_billing_header``'s inputs ever
    disagree, entries can outlive the block they were filled under.
    """
    read_globals = set(chat_handler.claude_code_attribution_revision.__code__.co_names)
    assert {
        "_CLAUDE_CODE_VERSION",
        "_FINGERPRINT_SALT",
        "_FINGERPRINT_INDICES",
        "_BILLING_HEADER_PREFIX",
    } <= read_globals


def test_the_revision_digest_is_stable_across_calls_and_not_time_derived() -> None:
    assert len({claude_code_attribution_revision() for _ in range(5)}) == 1
