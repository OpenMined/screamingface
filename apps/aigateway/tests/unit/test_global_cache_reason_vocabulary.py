"""OME-305 — one published vocabulary for ``X-AIGW-Cache-Reason``.

FEATURE: a globally shared cache whose refusals an operator can actually diagnose.
Every bypassed response carries a reason, and the reason is only useful if the
operator can look it up. The failure mode this file exists to prevent is a reason
string invented at one call site and published nowhere — an operator greps for it
and finds it in no source of truth.

INVARIANT under test: ``PUBLISHED_CACHE_REASONS`` is EXACTLY the set of reason
values the cache layers can emit — no missing member (a reason reaching a header
that is documented nowhere) and no extra member (a documented reason no code can
produce, which sends an operator hunting for a condition that cannot occur).

AIDEV-NOTE: the vocabulary lives in ``core.cache_ports``, which is a LEAF and so
cannot import the modules that define the constants. That duplication is deliberate
and this test is what makes it safe: add a reason without publishing it and this
fails. Four reason-defining modules plus the port constants were spread across two
naming conventions with no aggregate before this existed, and a new member
(``unprojected_parameter``) was added during a single review pass — the drift is
demonstrated, not hypothetical.
"""

from __future__ import annotations

from types import ModuleType
from typing import Final

import aigateway.core.request_cache.global_controls as global_controls
import aigateway.core.request_cache.global_eligibility as global_eligibility
import aigateway.core.request_cache.global_keys as global_keys
import aigateway.core.request_cache.global_plan as global_plan
from aigateway.core.cache_ports import (
    CACHE_UNAVAILABLE_REASON,
    PROJECTION_BYPASS_REASON,
    PUBLISHED_CACHE_REASONS,
)

# Every module allowed to define a cache bypass reason. A new one added here without
# publishing its constants makes the equality test below fail, which is the point.
_REASON_MODULES: Final[tuple[ModuleType, ...]] = (
    global_eligibility,
    global_controls,
    global_keys,
    global_plan,
)

# The two reasons that do NOT follow the ``BYPASS_*`` convention, named explicitly so
# the collector cannot miss them by pattern alone.
_PORT_REASONS: Final[frozenset[str]] = frozenset(
    {PROJECTION_BYPASS_REASON, CACHE_UNAVAILABLE_REASON}
)

# INVARIANT: the exact bytes a caller reads in ``X-AIGW-Cache-Reason``. This is the ONE
# place in the suite that spells the vocabulary out as LITERALS, and it must stay that
# way (owner decision 53).
#
# WHY, and it is not redundant with the equality tests below: every other assertion in
# this file compares one DERIVED set against another. Rename a constant and its
# ``cache_ports`` member together and all of them stay green — which is exactly what
# happened during OME-305, when ``disabled`` became ``cache_disabled`` and no test in
# this file noticed. URL4 reads these bytes, so that rename was a caller-visible break
# that the guard against caller-visible breaks could not see.
#
# AIDEV-NOTE: this is also why the rest of the suite binds header assertions to the
# CONSTANTS instead of literals. Those tests verify plumbing and are deliberately
# tautological about spelling; this one owns the spelling. Do not "simplify" it by
# deriving it — a derived version asserts nothing.
_WIRE_CONTRACT: Final[frozenset[str]] = frozenset(
    {
        "provider_projection",
        "cache_unavailable",
        "disabled",
        "opted_out",
        "malformed_controls",
        "unsupported_control",
        "unsupported_shape",
        "unknown_parameter",
        "unsupported_fields",
        "malformed_parameter",
        "mode_restricted_parameter",
        "unprojected_parameter",
        "provider_rule_set",
        "stream",
        "tools",
        "metadata",
        "canonicalization_failure",
    }
)


def _declared_reasons() -> dict[str, set[str]]:
    """Every ``BYPASS_*`` constant, as {value: {"module.NAME", ...}}."""
    found: dict[str, set[str]] = {}
    for module in _REASON_MODULES:
        for name, value in vars(module).items():
            if name.startswith("BYPASS_") and isinstance(value, str):
                found.setdefault(value, set()).add(f"{module.__name__.split('.')[-1]}.{name}")
    return found


def test_the_reason_collector_is_not_vacuous() -> None:
    # Guards the guard: an introspection sweep that finds nothing would make every
    # assertion below trivially true.
    declared = _declared_reasons()
    assert len(declared) >= 15, declared
    assert {module for names in declared.values() for module in names}


def test_every_reason_a_layer_can_emit_is_published() -> None:
    # The direction that matters operationally: a reason reaching a response header
    # while appearing in no published vocabulary.
    declared = _declared_reasons()
    unpublished = {
        value: sorted(names)
        for value, names in declared.items()
        if value not in PUBLISHED_CACHE_REASONS
    }
    assert unpublished == {}, unpublished
    assert _PORT_REASONS <= PUBLISHED_CACHE_REASONS


def test_the_published_vocabulary_has_no_reason_no_code_can_produce() -> None:
    # The opposite direction: a stale published member outlives the code that emitted
    # it and sends an operator hunting for a condition that can no longer occur.
    producible = set(_declared_reasons()) | _PORT_REASONS
    assert PUBLISHED_CACHE_REASONS - producible == set()


def test_the_published_vocabulary_is_exactly_what_the_code_declares() -> None:
    # Both directions as one equality, so the set cannot drift in either direction.
    assert PUBLISHED_CACHE_REASONS == set(_declared_reasons()) | _PORT_REASONS


def test_one_condition_never_hides_behind_two_different_constant_names() -> None:
    """One condition, one constant — otherwise the header is ambiguous to its reader.

    Two DIFFERENT constants sharing a value means two distinct causes report
    identically and an operator cannot tell which happened.

    AIDEV-NOTE: comparing bare constant names, not module-qualified ones, is the
    load-bearing detail. ``global_keys`` deliberately re-exports every eligibility
    reason (its docstring commits to that), so one value legitimately appears in two
    modules under the SAME name. A re-export is not a collision; two names are.
    """
    names_by_value: dict[str, set[str]] = {}
    for value, qualified in _declared_reasons().items():
        names_by_value[value] = {name.split(".", 1)[1] for name in qualified}
    collisions = {value: sorted(names) for value, names in names_by_value.items() if len(names) > 1}
    assert collisions == {}, collisions


def test_the_published_vocabulary_matches_the_wire_contract_byte_for_byte() -> None:
    """The caller-visible contract, asserted as literals — see ``_WIRE_CONTRACT``.

    A failure here is never "update the test to match": it means a reason's SPELLING
    moved, which is a break for every consumer reading the header, URL4 included.
    Either restore the spelling or take the break deliberately with the owner.
    """
    assert PUBLISHED_CACHE_REASONS == _WIRE_CONTRACT


def test_the_two_reverted_spellings_keep_their_v1_bytes() -> None:
    """Pins owner decision 53 — "rename only what must change" — at the constants.

    Both of these were renamed during OME-305 and reverted. The rename argument (that
    a bare ``disabled`` reads as "something was disabled" beside siblings like
    ``opted_out``) was made and REJECTED, so a future reader who finds it persuasive
    is re-opening a settled decision. Asserting the constants rather than only the
    aggregate names WHICH two values carry that history.
    """
    assert global_plan.BYPASS_DISABLED == "disabled"
    assert global_eligibility.BYPASS_DECLARED == "unsupported_fields"


def test_the_only_retired_v1_reason_is_the_one_whose_condition_disappeared() -> None:
    """``not_requested`` is the single accepted break, and it is a REMOVAL.

    v1 required an opt-in, so "the caller did not ask for caching" was a real
    condition with a real reason. v2 is default-on: the condition cannot occur, so
    publishing the reason would send an operator hunting for a state that no longer
    exists. That is why removing it is safe where renaming the others was not.
    """
    assert "not_requested" not in PUBLISHED_CACHE_REASONS
    assert "not_requested" not in _declared_reasons()


def test_no_reason_can_carry_a_caller_value_or_prompt_fragment() -> None:
    # INVARIANT: the vocabulary is CLOSED and gateway-owned, so every member is a
    # fixed lowercase token. A reason built by interpolating a model name, a caller
    # value or an upstream error message would not survive this shape check.
    for reason in PUBLISHED_CACHE_REASONS:
        assert reason
        assert reason == reason.strip().lower()
        assert reason.replace("_", "").isalnum(), reason
        assert len(reason) <= 40, reason
