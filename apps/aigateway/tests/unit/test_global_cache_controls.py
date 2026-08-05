"""OME-305 U1 — the v2 global cache control grammar.

FEATURE: the global cache is ON by default. The control object exists to OPT OUT,
not to opt in.

STORY: as a benchmark operator I send an ordinary chat request with no cache
control at all and it participates in the global cache; as an operator measuring
cold-path latency I send ``cache: {"use-cache": false}`` and it does not.

INVARIANT under test: the grammar is closed and fail-safe — every field except
``use-cache`` makes the request bypass rather than being ignored, and the control
object is stripped from the body in every case so it can never reach a provider.
"""

from __future__ import annotations

from typing import Any

import pytest

from aigateway.core.request_cache.global_controls import (
    BYPASS_MALFORMED_CONTROLS,
    BYPASS_OPTED_OUT,
    BYPASS_UNSUPPORTED_CONTROL,
    CONTROL_FIELD,
    UNSUPPORTED_CONTROL_FIELDS,
    parse_global_cache_controls,
)


def _body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"model": "fake/m", "messages": [{"role": "user", "content": "hi"}]}
    body.update(overrides)
    return body


# --- default-on ---------------------------------------------------------------


def test_a_request_with_no_cache_control_participates() -> None:
    # The v2 product change: v1 required an explicit opt-in, so the runs that most
    # needed caching silently paid full price.
    controls = parse_global_cache_controls(_body())
    assert controls.participate is True
    assert controls.bypass_reason == ""


@pytest.mark.parametrize("stated", [None, {}])
def test_a_control_object_that_states_nothing_participates(stated: Any) -> None:
    assert parse_global_cache_controls(_body(cache=stated)).participate is True


def test_an_explicit_opt_in_participates() -> None:
    # Retained so a v1 client that already sends the opt-in keeps working.
    assert parse_global_cache_controls(_body(cache={"use-cache": True})).participate is True


# --- opting out ---------------------------------------------------------------


def test_an_explicit_opt_out_bypasses() -> None:
    controls = parse_global_cache_controls(_body(cache={"use-cache": False}))
    assert controls.participate is False
    assert controls.bypass_reason == BYPASS_OPTED_OUT


@pytest.mark.parametrize("stated", ["true", 1, 0, [], "", "false"])
def test_a_non_boolean_opt_in_is_malformed_and_bypasses(stated: Any) -> None:
    # WHY not "truthy means yes": ``use-cache: "false"`` is truthy in Python and
    # would enable caching for a caller who plainly meant the opposite.
    controls = parse_global_cache_controls(_body(cache={"use-cache": stated}))
    assert controls.participate is False
    assert controls.bypass_reason == BYPASS_MALFORMED_CONTROLS


@pytest.mark.parametrize("stated", ["yes", 7, [], ["use-cache"], True, 0.5])
def test_a_control_object_that_is_not_an_object_bypasses(stated: Any) -> None:
    controls = parse_global_cache_controls(_body(cache=stated))
    assert controls.participate is False
    assert controls.bypass_reason == BYPASS_MALFORMED_CONTROLS


# --- retired and unknown controls --------------------------------------------


@pytest.mark.parametrize("field", sorted(UNSUPPORTED_CONTROL_FIELDS))
def test_every_unsupported_control_bypasses(field: str) -> None:
    # Plan §8 #14. A v2 entry never expires and is shared by every caller, so a
    # per-request TTL or a write suppression cannot be honored — and must not be
    # silently ignored either.
    controls = parse_global_cache_controls(_body(cache={field: 60}))
    assert controls.participate is False
    assert controls.bypass_reason == BYPASS_UNSUPPORTED_CONTROL


def test_the_retired_control_set_is_explicit_and_closed() -> None:
    assert UNSUPPORTED_CONTROL_FIELDS == {"ttl", "s-maxage", "no-cache", "no-store"}


def test_an_unknown_control_field_bypasses() -> None:
    controls = parse_global_cache_controls(_body(cache={"nonesuch": True}))
    assert controls.participate is False
    assert controls.bypass_reason == BYPASS_UNSUPPORTED_CONTROL


def test_there_is_no_variant_lane_to_ask_for() -> None:
    # Plan §8 #19: an exact request has ONE global response. ``variant`` is not a
    # control this grammar knows, so asking for one bypasses rather than silently
    # returning the single entry.
    controls = parse_global_cache_controls(_body(cache={"variant": "sample-0"}))
    assert controls.bypass_reason == BYPASS_UNSUPPORTED_CONTROL


def test_an_unsupported_field_wins_over_a_present_opt_in() -> None:
    controls = parse_global_cache_controls(_body(cache={"use-cache": True, "ttl": 60}))
    assert controls.participate is False
    assert controls.bypass_reason == BYPASS_UNSUPPORTED_CONTROL


# --- the control object never reaches a provider ------------------------------


@pytest.mark.parametrize(
    "stated",
    [None, {}, {"use-cache": True}, {"use-cache": False}, {"ttl": 60}, "malformed", 7],
)
def test_the_control_object_is_always_stripped_from_the_body(stated: Any) -> None:
    # INVARIANT: unconditional, including the malformed cases — a gateway control
    # object must never be adjudicated as a model parameter or forwarded upstream.
    body = _body(cache=stated)
    parse_global_cache_controls(body)
    assert CONTROL_FIELD not in body


def test_nothing_else_in_the_body_is_touched() -> None:
    body = _body(cache={"use-cache": False}, temperature=0.7)
    parse_global_cache_controls(body)
    assert body == {
        "model": "fake/m",
        "messages": [{"role": "user", "content": "hi"}],
        "temperature": 0.7,
    }
