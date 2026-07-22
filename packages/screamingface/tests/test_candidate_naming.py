from __future__ import annotations

import inspect

from screamingface import Benchmark


def test_benchmark_evaluation_names_the_recipe_by_its_role() -> None:
    parameters = inspect.signature(Benchmark.evaluate).parameters

    assert tuple(parameters) == ("self", "candidate", "first", "progress")
    assert "recipe" not in parameters
