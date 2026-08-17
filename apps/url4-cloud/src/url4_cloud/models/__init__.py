"""The declared model world. See :mod:`url4_cloud.models.registry` for the invariants."""

from url4_cloud.models.registry import (
    EMPTY_MODEL_WORLD,
    ROUTE_ID_RE,
    ModelRegistry,
    ProviderSeed,
    canonical_id,
    is_route_legal,
)

__all__ = [
    "EMPTY_MODEL_WORLD",
    "ROUTE_ID_RE",
    "ModelRegistry",
    "ProviderSeed",
    "canonical_id",
    "is_route_legal",
]
