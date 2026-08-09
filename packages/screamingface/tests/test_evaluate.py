from __future__ import annotations

import inspect
from typing import Any, cast

import pytest

import screamingface as sf


def test_benchmark_is_required_when_evaluating_recipes() -> None:
    candidate = sf.Model("provider/model")

    inspect.signature(sf.evaluate).bind(candidate, benchmark="draco")
    inspect.signature(sf.Client.evaluate).bind(object(), candidate, benchmark="draco")
    inspect.signature(sf.AsyncClient.evaluate).bind(object(), candidate, benchmark="draco")

    with sf.Client() as client:
        with pytest.raises(TypeError, match="benchmark is required"):
            client.evaluate(candidate)  # type: ignore[call-overload]


@pytest.mark.asyncio
async def test_benchmark_is_required_when_evaluating_recipes_async() -> None:
    client = sf.AsyncClient()

    with pytest.raises(TypeError, match="benchmark is required"):
        await client.evaluate(sf.Model("provider/model"))  # type: ignore[call-overload]

    await client.aclose()


def test_benchmark_override_is_keyword_only() -> None:
    with pytest.raises(TypeError):
        inspect.signature(sf.evaluate).bind(sf.Model("provider/model"), "draco")


def test_candidate_scheduling_is_not_public_configuration() -> None:
    for evaluate in (sf.evaluate, sf.Client.evaluate, sf.AsyncClient.evaluate):
        parameters = inspect.signature(evaluate).parameters
        assert "concurrency" not in parameters
        assert "parallel" not in parameters
        assert "max_workers" not in parameters


@pytest.mark.parametrize("limit", [0, -1, True, "all"])
def test_evaluate_rejects_invalid_limits(limit: object) -> None:
    with sf.Client() as client:
        with pytest.raises((TypeError, ValueError), match="positive integer or None"):
            client.evaluate(
                sf.Model("provider/model"),
                benchmark="draco",
                limit=cast(Any, limit),
            )


def test_evaluate_rejects_duplicate_candidate_names_before_network_work() -> None:
    first = sf.Model("provider/opus", name="same")
    second = sf.Model("provider/gpt", name="same")

    with sf.Client() as client:
        with pytest.raises(ValueError, match="duplicate Candidate name"):
            client.evaluate([first, second], benchmark="draco")


def test_evaluate_validates_event_and_progress_options_before_network_work() -> None:
    with sf.Client() as client:
        with pytest.raises(TypeError, match="on_event"):
            client.evaluate(
                sf.Model("provider/model"),
                benchmark="draco",
                on_event=cast(Any, "not-callable"),
            )
        with pytest.raises(TypeError, match="progress"):
            client.evaluate(
                sf.Model("provider/model"),
                benchmark="draco",
                progress=cast(Any, "yes"),
            )


def test_public_interface_has_one_evaluation_verb() -> None:
    for removed in ("Plan", "Candidate", "plan", "run"):
        assert removed not in sf.__all__
        assert not hasattr(sf, removed)

    assert hasattr(sf, "evaluate")
    assert hasattr(sf.Client, "evaluate")
    assert hasattr(sf.AsyncClient, "evaluate")
    for client_type in (sf.Client, sf.AsyncClient):
        assert not hasattr(client_type, "plan")
        assert not hasattr(client_type, "run")
