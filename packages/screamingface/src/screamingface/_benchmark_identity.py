"""One normalization rule for benchmark identities at every Client boundary."""

from __future__ import annotations

import re

_BENCHMARK_ID = re.compile(r"[a-z0-9][a-z0-9._-]*")


def benchmark_id(value: object, label: str = "Benchmark id") -> str:
    """Return one canonical flat id or reject the value without translating it."""

    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    selected = value.strip()
    if _BENCHMARK_ID.fullmatch(selected) is None:
        raise ValueError(f"{label} must be one flat lowercase identifier")
    return selected


__all__: list[str] = []
