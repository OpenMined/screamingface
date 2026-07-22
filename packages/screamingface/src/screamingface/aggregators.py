"""Deterministic benchmark aggregation strategies."""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from typing import ClassVar


class Aggregator(ABC):
    """Base type for deterministic grade aggregation strategies."""

    kind: ClassVar[str]


@dataclass(frozen=True, slots=True)
class Mean(Aggregator):
    """Unweighted arithmetic mean over the common valid paired case set."""

    kind: ClassVar[str] = "mean"
