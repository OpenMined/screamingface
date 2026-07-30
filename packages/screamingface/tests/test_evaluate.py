from __future__ import annotations

from typing import Any, cast

import pytest

import screamingface as sf


def test_evaluate_requires_a_benchmark() -> None:
    with sf.Client() as client:
        with pytest.raises(TypeError, match="benchmark"):
            cast(Any, client.evaluate)(sf.Model("provider/model"))


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


def test_public_interface_has_one_evaluation_operation() -> None:
    for removed in ("Plan", "Candidate", "evaluate", "plan", "run"):
        assert removed not in sf.__all__
        assert not hasattr(sf, removed)

    assert hasattr(sf.Client, "evaluate")
    assert hasattr(sf.AsyncClient, "evaluate")
    for client_type in (sf.Client, sf.AsyncClient):
        assert not hasattr(client_type, "plan")
        assert not hasattr(client_type, "run")
