"""OME-631 (OME-479 §5.1): discovered evidence restricts the TOOLS section too.

FEATURE: backend-specific tool evidence in the detailed contract. OME-629 gave the
parameters section a merge algebra; a tool type lives in BOTH sections, so without
the same treatment here one document would report `parameters.tools` unsupported
while `tools.function` still claimed support.

STORY: as an API consumer I read /v1/model-parameters for a model pinned to a
backend that cannot do function calling, and every place the document mentions
tools agrees — while the gateway's own decision about what it forwards is unmoved.

INVARIANT (owner decision 2026-07-27): the overlay moves provider_support ONLY. It
never touches gateway_status, so it cannot change the /v1/models supported_tools
summary (which filters on gateway_status) or authorize anything.
"""

from __future__ import annotations

from aigateway.core.chat_parameters import (
    ProviderDiscoverySnapshot,
    ProviderToolObservation,
    ToolCapability,
    overlay_tool_capabilities,
    supported_tool_types,
)
from aigateway.core.plugin_base import ProviderPluginBase

_FUNCTION = ToolCapability(
    tool_type="function", provider_support="supported", gateway_status="enabled"
)
_WEB_SEARCH = ToolCapability(
    tool_type="web_search", provider_support="supported", gateway_status="disabled"
)
_BASE = (_FUNCTION, _WEB_SEARCH)


def _by_type(caps) -> dict[str, ToolCapability]:
    return {c.tool_type: c for c in caps}


# --- the pure merge ----------------------------------------------------------


def test_dynamic_evidence_replaces_the_provider_verdict() -> None:
    merged = _by_type(
        overlay_tool_capabilities(
            _BASE, (ProviderToolObservation(tool_type="function", support="unsupported"),)
        )
    )
    assert merged["function"].provider_support == "unsupported"


def test_the_gateway_decision_survives_the_overlay_untouched() -> None:
    # THE invariant: evidence describes the provider, policy describes the gateway.
    # A backend that cannot do tools does not stop the gateway forwarding them.
    merged = _by_type(
        overlay_tool_capabilities(
            _BASE, (ProviderToolObservation(tool_type="function", support="unsupported"),)
        )
    )
    assert merged["function"].gateway_status == "enabled"


def test_the_models_summary_cannot_move() -> None:
    # supported_tool_types filters on gateway_status, so the inline /v1/models
    # summary is structurally immune to this overlay — pinned, not assumed.
    overlaid = overlay_tool_capabilities(
        _BASE, (ProviderToolObservation(tool_type="function", support="unsupported"),)
    )
    assert supported_tool_types(overlaid) == supported_tool_types(_BASE) == ("function",)


def test_a_tool_type_the_overlay_is_silent_about_keeps_its_verdict() -> None:
    merged = _by_type(
        overlay_tool_capabilities(
            _BASE, (ProviderToolObservation(tool_type="function", support="unsupported"),)
        )
    )
    assert merged["web_search"].provider_support == "supported"
    assert merged["web_search"].gateway_status == "disabled"


def test_an_unknown_tool_type_is_ignored_never_invented() -> None:
    # A ToolCapability bundles BOTH axes, so admitting an unknown type would force
    # the gateway to invent a status for a tool it has no rule for. Restrict-only.
    merged = overlay_tool_capabilities(
        _BASE, (ProviderToolObservation(tool_type="code_interpreter", support="supported"),)
    )
    assert [c.tool_type for c in merged] == ["function", "web_search"]


def test_base_order_is_preserved() -> None:
    # The provider's tuple is curated, so its order is meaningful; the overlay is a
    # substitution, not a re-sort.
    merged = overlay_tool_capabilities(
        _BASE, (ProviderToolObservation(tool_type="web_search", support="unsupported"),)
    )
    assert [c.tool_type for c in merged] == ["function", "web_search"]


def test_an_empty_overlay_returns_the_base_capabilities() -> None:
    assert overlay_tool_capabilities(_BASE, ()) == _BASE


# --- the plugin port ---------------------------------------------------------


class _Plugin(ProviderPluginBase):
    custom_llm_provider = "demo"

    def register_models(self):
        return []


def test_no_snapshot_leaves_the_local_capabilities_untouched() -> None:
    # NO ATTEMPT / degraded: the reviewed labelled-local capabilities serve. A
    # discovery outage must never silently empty or downgrade the tools section.
    assert _Plugin().overlay_discovered_tools(_BASE, None) == _BASE


def test_a_snapshot_without_tool_evidence_changes_nothing() -> None:
    # A provider whose catalog says nothing about tools (the OpenRouter shape)
    # still gets its labelled-local verdicts, not a wall of silence.
    snapshot = ProviderDiscoverySnapshot(source_revision="rev-1")
    assert _Plugin().overlay_discovered_tools(_BASE, snapshot) == _BASE


def test_the_port_applies_the_snapshot_tool_evidence() -> None:
    snapshot = ProviderDiscoverySnapshot(
        source_revision="rev-1",
        tool_observations=(ProviderToolObservation(tool_type="function", support="unsupported"),),
    )
    merged = _by_type(_Plugin().overlay_discovered_tools(_BASE, snapshot))
    assert merged["function"].provider_support == "unsupported"
    assert merged["function"].gateway_status == "enabled"
