"""How this provider spells one piece of parameter evidence.

FEATURE: OpenRouter observation overlay — the vocabulary every source this
provider reads shares. Both parsers and the reviewed labelled-local inventory
build their observations through these helpers, which is what keeps a wrapped
native field at the SAME request path no matter which document reported it.

INVARIANT (§5.1): the source labels are DISTINCT, and they are declared together
here so that stays visible. Endpoint evidence, per-model evidence, reviewed
labelled-local sampling evidence and reviewed routing-policy evidence are never
merged into one support verdict.
"""

from __future__ import annotations

from aigateway.core.chat_parameters import ProviderParameterObservation, ProviderSupport
from aigateway.core.parameter_projection import WRAPPER_KEY

from .routing_policy import ROUTING_CONTROL_LEAVES, ROUTING_CONTROLS

MODEL_SOURCE = "openrouter:models"
ENDPOINT_SOURCE = "openrouter:openapi"

# Provenance label for REVIEWED labelled-local evidence — deliberately DISTINCT
# from the live labels (openrouter:models / openrouter:openapi) so a reader can
# tell reviewed-static evidence from a live network fetch (§5.1 "labelled").
LOCAL_SOURCE = "openrouter:static"

# Provenance label for the REVIEWED ROUTING-POLICY surface (OME-704) — distinct
# again, because it is evidence about a different thing. LOCAL_SOURCE is a reviewed
# inventory of the chat endpoint's SAMPLING fields (what the model accepts);
# routing policy is about OpenRouter's ROUTING behaviour (which endpoint serves the
# request). Folding them into one label would let a reader take a routing claim as
# a sampling-inventory claim, and would hide which surface a stale review covers.
ROUTING_POLICY_SOURCE = "openrouter:routing-policy"

# OpenRouter params AIGateway addresses through the ``provider_params.*`` wrapper
# (native, non-OpenAI-standard). Mirrors the provider_native rule paths so a
# wrapped field's observation lines up with its rule in the detail overlay — this
# is what lets ``top_k`` show a clean observed→ruled promotion while standard
# fields (``top_p``) surface observed-but-unruled at their identity path.
# AIDEV-NOTE: grows with each native rule added in parameters.py; keep in sync.
# The routing-policy leaves are folded in from their single source of truth rather
# than restated, so the two files cannot disagree about which fields ride the
# wrapper (``wrapper_path_conflicts`` is the cross-check that would catch it).
_WRAPPED_NATIVE_PARAMS: frozenset[str] = frozenset({"top_k"}) | ROUTING_CONTROL_LEAVES


def _request_path(catalog_param: str) -> str:
    if catalog_param in _WRAPPED_NATIVE_PARAMS:
        return f"{WRAPPER_KEY}.{catalog_param}"
    return catalog_param


def _observation(
    catalog_param: str, *, source: str, support: ProviderSupport = "supported"
) -> ProviderParameterObservation:
    return ProviderParameterObservation(
        request_path=_request_path(catalog_param),
        support=support,
        source=source,
    )


# OME-704 — REVIEWED routing-policy evidence (NO network). OpenRouter documents
# each of these on the chat request's `provider` object; the review is what backs
# the claim, exactly as _REVIEWED_ENDPOINT_PARAMS backs the sampling inventory.
# INVARIANT: an observation NEVER enables a field — the rules in parameters.py do.
# This exists so an ENABLED routing control is not published with "unknown/none"
# provider evidence, and it is derived from ROUTING_CONTROLS so a control can never
# be ruled-but-unevidenced (the registry conformance sweep enforces that pairing).
ROUTING_POLICY_OBSERVATIONS: tuple[ProviderParameterObservation, ...] = tuple(
    _observation(control.leaf, source=ROUTING_POLICY_SOURCE) for control in ROUTING_CONTROLS
)


def _dedup_sorted(
    obs: list[ProviderParameterObservation],
) -> tuple[ProviderParameterObservation, ...]:
    by_path: dict[str, ProviderParameterObservation] = {}
    for observation in obs:
        by_path.setdefault(observation.request_path, observation)
    return tuple(by_path[path] for path in sorted(by_path))
