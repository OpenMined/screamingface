"""How this provider spells one piece of parameter evidence.

FEATURE: OpenRouter observation overlay — the vocabulary every source this
provider reads shares. Both parsers and the reviewed labelled-local inventory
build their observations through these helpers, which is what keeps a wrapped
native field at the SAME request path no matter which document reported it.

INVARIANT (§5.1): the three source labels are DISTINCT, and they are declared
together here so that stays visible. Endpoint evidence, per-model evidence and
reviewed labelled-local evidence are never merged into one support verdict.
"""

from __future__ import annotations

from aigateway.core.chat_parameters import ProviderParameterObservation, ProviderSupport
from aigateway.core.parameter_projection import WRAPPER_KEY

MODEL_SOURCE = "openrouter:models"
ENDPOINT_SOURCE = "openrouter:openapi"

# Provenance label for REVIEWED labelled-local evidence — deliberately DISTINCT
# from the live labels (openrouter:models / openrouter:openapi) so a reader can
# tell reviewed-static evidence from a live network fetch (§5.1 "labelled").
LOCAL_SOURCE = "openrouter:static"

# OpenRouter params AIGateway addresses through the ``provider_params.*`` wrapper
# (native, non-OpenAI-standard). Mirrors the provider_native rule paths so a
# wrapped field's observation lines up with its rule in the detail overlay — this
# is what lets ``top_k`` show a clean observed→ruled promotion while standard
# fields (``top_p``) surface observed-but-unruled at their identity path.
# AIDEV-NOTE: grows with each native rule added in parameters.py; keep in sync.
_WRAPPED_NATIVE_PARAMS: frozenset[str] = frozenset({"top_k"})


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


def _dedup_sorted(
    obs: list[ProviderParameterObservation],
) -> tuple[ProviderParameterObservation, ...]:
    by_path: dict[str, ProviderParameterObservation] = {}
    for observation in obs:
        by_path.setdefault(observation.request_path, observation)
    return tuple(by_path[path] for path in sorted(by_path))
