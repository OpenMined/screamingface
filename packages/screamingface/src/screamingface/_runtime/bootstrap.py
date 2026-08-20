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
    """Project the Engine-owned registry onto Scoreboard's registration contract.

    This is the local twin of what a deployment does over HTTP: the same fields the Engine's
    ``/v1/benchmarks`` catalogue publishes, read by import because a local stack runs the
    Engine and the board in one virtualenv (OME-904). Keeping the two projections in step is
    what makes a local leaderboard look like the deployed one.
    """

    return json.dumps(
        [
            {
                "id": benchmark.id,
                "display_name": benchmark.title,
                "description": benchmark.description,
                "revision": benchmark.revision,
                # Optional in the Engine, so absent stays absent rather than becoming null.
                **({"focus": focus} if (focus := getattr(benchmark, "focus", None)) else {}),
                **(
                    {"dataset_url": dataset_url}
                    if (dataset_url := getattr(benchmark, "dataset_url", None))
                    else {}
                ),
            }
            for benchmark in benchmarks
        ]
    )


__all__: list[str] = []
