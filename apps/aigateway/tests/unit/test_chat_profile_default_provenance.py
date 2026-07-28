"""OME-638: which request paths a profile default actually WROTE.

FEATURE: profile defaults under one parameter contract. ``_apply_defaults``
returns the set of paths it wrote, and that set is what lets a later rejection be
attributed to the profile rather than to the caller.

INVARIANT: the reported paths are the CLASSIFIER's request paths, not the
``ProfileDefaults`` field names — ``timeout_seconds`` is reported as ``timeout``.
A set keyed by field name would never match a rejection, and every profile fault
would be silently misattributed to the caller.

These are pure unit tests over the function: no route, no credentials, no
fixtures. The route-level refusal, attribution, ordering and valid-path cases
live in ``test_chat_profile_default_validation``.
"""

from __future__ import annotations

from aigateway.core.profile_models import ProfileDefaults
from aigateway.routes.chat_credentials import _apply_defaults

# --- provenance -----------------------------------------------------------------


class _Plugin:
    """Applies every default — the base-class behavior."""

    def should_apply_profile_default(self, field: str) -> bool:
        return True


class _SkipsReasoning:
    """The Anthropic shape: opts one field out of profile defaulting."""

    def should_apply_profile_default(self, field: str) -> bool:
        return field != "reasoning_effort"


def test_apply_defaults_reports_the_request_paths_it_wrote() -> None:
    # INVARIANT under test: the reported paths are the CLASSIFIER's request paths,
    # so `timeout_seconds` is reported under its gateway name `timeout`. A set
    # keyed by the ProfileDefaults field name instead would never match a
    # rejection and would silently misattribute every profile fault to the caller.
    body, written = _apply_defaults(
        {"messages": []},
        ProfileDefaults(temperature=0.5, max_tokens=64, timeout_seconds=9.0),
        _Plugin(),
    )
    assert written == frozenset({"temperature", "max_tokens", "timeout"})
    assert body["timeout"] == 9.0


def test_apply_defaults_reports_nothing_for_a_field_the_body_already_carries() -> None:
    body, written = _apply_defaults(
        {"messages": [], "temperature": 0.1},
        ProfileDefaults(temperature=0.5),
        _Plugin(),
    )
    assert written == frozenset()
    assert body["temperature"] == 0.1


def test_apply_defaults_reports_nothing_for_a_field_the_provider_opts_out_of() -> None:
    body, written = _apply_defaults(
        {"messages": []},
        ProfileDefaults(reasoning_effort="medium"),
        _SkipsReasoning(),
    )
    assert written == frozenset()
    assert "reasoning_effort" not in body


def test_apply_defaults_reports_the_system_prompt_as_a_messages_write() -> None:
    # The system prompt REWRITES an existing gateway-owned field rather than
    # adding a new one; it is still this call's doing, so it is still reported.
    body, written = _apply_defaults(
        {"messages": [{"role": "user", "content": "hi"}]},
        ProfileDefaults(system_prompt="be terse"),
        _Plugin(),
    )
    assert written == frozenset({"messages"})
    assert body["messages"][0]["role"] == "system"
