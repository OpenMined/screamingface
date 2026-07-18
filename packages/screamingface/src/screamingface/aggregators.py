"""Aggregation definitions; aggregation execution is introduced in Phase 3."""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from typing import ClassVar


class Aggregator(ABC):
    """Base type for deterministic grade aggregation strategies."""

    kind: ClassVar[str]


@dataclass(frozen=True, slots=True)
class Mean(Aggregator):
    """Average paired valid grades."""

    kind: ClassVar[str] = "mean"
