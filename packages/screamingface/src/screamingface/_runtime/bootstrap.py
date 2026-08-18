from __future__ import annotations

import json
from collections.abc import Iterable, MutableMapping
from typing import Protocol


class BenchmarkDefinition(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def title(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def revision(self) -> str: ...


def enable_local_providers(environment: MutableMapping[str, str]) -> None:
    """Enable the local BYOK provider while preserving an explicit operator choice."""

    environment.setdefault("AIGW_OPENROUTER_ENABLED", "true")


def scoreboard_seed_json(benchmarks: Iterable[BenchmarkDefinition]) -> str:
    """Project the Engine-owned registry onto Scoreboard's registration contract."""

    return json.dumps(
        [
            {
                "id": benchmark.id,
                "display_name": benchmark.title,
                "description": benchmark.description,
                "revision": benchmark.revision,
            }
            for benchmark in benchmarks
        ]
    )


__all__: list[str] = []
