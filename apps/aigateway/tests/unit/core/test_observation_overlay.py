"""OME-629 (OME-479 §4.4/§5.1): dynamic evidence overlays labelled-local evidence.

FEATURE: model-specific provider evidence in the detailed contract. This pins the
PURE merge algebra that lets a live per-model snapshot replace a provider's
reviewed labelled-local verdict for a request path, plus the plugin port that
applies it — so every provider gets the same, reviewed merge instead of inventing
one.

STORY: as an API consumer I read /v1/model-parameters for two models of the same
provider and see evidence that actually differs per model, while the gateway's own
decision about what it will forward stays exactly the same for both.

INVARIANT (§4.4, owner decision 2026-07-27): the overlay moves the EVIDENCE axis
ONLY. It may change provider.support / provider.source / provider.stale and it may
ADD a visible DISABLED row — it never creates a rule, so it can never enable
dispatch, alter the /v1/models summary, or make a warm cache authorize what a cold
cache rejected.
"""

from __future__ import annotations

from aigateway.core.chat_parameters import (
    ProviderDiscoverySnapshot,
    ProviderParameterObservation,
    ProviderSupport,
    compose_contract_entries,
    overlay_observations,
)
from aigateway.core.plugin_base import ProviderPluginBase

_LOCAL = "p:static"
_LIVE = "p:models"


def _obs(
    path: str,
    support: ProviderSupport = "supported",
    source: str = _LOCAL,
    *,
    stale: bool = False,
) -> ProviderParameterObservation:
    return ProviderParameterObservation(
        request_path=path, support=support, source=source, stale=stale
    )


_BASE = (_obs("temperature"), _obs("top_p"), _obs("seed"))


def _by_path(observations) -> dict[str, ProviderParameterObservation]:
    return {o.request_path: o for o in observations}


# --- the pure merge ----------------------------------------------------------


def test_dynamic_evidence_replaces_the_local_verdict_for_that_path() -> None:
    merged = _by_path(
        overlay_observations(_BASE, (_obs("seed", "unsupported", _LIVE),)),
    )
    # the live per-model reading WINS: one path, one verdict, no double row.
    assert merged["seed"].support == "unsupported"
    assert merged["seed"].source == _LIVE


def test_a_path_only_the_local_source_knows_survives_untouched() -> None:
    # the catalog is silent about top_p here; silence must not erase reviewed
    # labelled-local evidence, or a partial source would look like a denial.
    merged = _by_path(overlay_observations(_BASE, (_obs("seed", "supported", _LIVE),)))
    assert merged["top_p"].source == _LOCAL
    assert merged["top_p"].support == "supported"


def test_a_path_only_the_dynamic_source_knows_is_added() -> None:
    merged = _by_path(overlay_observations(_BASE, (_obs("min_p", "supported", _LIVE),)))
    assert merged["min_p"].source == _LIVE


def test_stale_marks_only_the_overlaid_entries() -> None:
    # served from the stale window: the LAST-GOOD dynamic verdict still stands, but
    # it is labelled. The static base was never fetched, so it is never stale.
    merged = _by_path(
        overlay_observations(_BASE, (_obs("seed", "unsupported", _LIVE),), stale=True)
    )
    assert merged["seed"].stale is True
    assert merged["temperature"].stale is False


def test_a_fresh_overlay_clears_a_previously_stale_flag() -> None:
    # the flag is the CACHE's verdict about this read, never a property the parser
    # carries; a fresh read must not inherit a stale label from its input.
    merged = _by_path(
        overlay_observations(_BASE, (_obs("seed", "supported", _LIVE, stale=True),), stale=False)
    )
    assert merged["seed"].stale is False


def test_overlay_is_deterministically_ordered() -> None:
    merged = overlay_observations(_BASE, (_obs("min_p", "supported", _LIVE),))
    paths = [o.request_path for o in merged]
    assert paths == sorted(paths)


def test_an_empty_overlay_returns_the_base_evidence() -> None:
    assert _by_path(overlay_observations(_BASE, ())) == _by_path(_BASE)


# --- the plugin port ---------------------------------------------------------


class _Plugin(ProviderPluginBase):
    custom_llm_provider = "demo"

    def register_models(self):
        return []


def test_no_snapshot_leaves_the_local_evidence_untouched() -> None:
    # NO ATTEMPT / degraded: labelled-local evidence serves unchanged. Never a
    # fabricated verdict, and never a silently emptied contract.
    assert _Plugin().overlay_discovered_observations(_BASE, None) == _BASE


def test_per_model_evidence_outranks_endpoint_evidence() -> None:
    # §5.1: both are real, but "what THIS model supports" is the more specific
    # claim, so it decides the published verdict for the path.
    snapshot = ProviderDiscoverySnapshot(
        source_revision="rev-1",
        endpoint_observations=(_obs("seed", "supported", "p:openapi"),),
        model_observations=(_obs("seed", "unsupported", _LIVE),),
    )
    merged = _by_path(_Plugin().overlay_discovered_observations(_BASE, snapshot))
    assert merged["seed"].support == "unsupported"
    assert merged["seed"].source == _LIVE


def test_an_overlaid_but_unruled_path_is_a_visible_disabled_row_never_a_rule() -> None:
    # THE invariant this unit is built around: evidence can add a ROW, never a
    # rule. A newly discovered field is reported and rejected, not dispatched.
    snapshot = ProviderDiscoverySnapshot(
        source_revision="rev-1",
        model_observations=(_obs("repetition_penalty", "supported", _LIVE),),
    )
    merged = _Plugin().overlay_discovered_observations(_BASE, snapshot)
    entries = {e.request_path: e for e in compose_contract_entries((), merged, auth_mode="api_key")}
    assert entries["repetition_penalty"].gateway_status == "disabled"
    assert entries["repetition_penalty"].gateway_reason == "projection_not_implemented"
    assert entries["repetition_penalty"].provider_support == "supported"
