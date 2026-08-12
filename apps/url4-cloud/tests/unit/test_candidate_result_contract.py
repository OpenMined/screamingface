"""`CandidateResult` — the producer-side wire contract every aggregate constructs."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from url4_cloud.benchmarks.contract import CANDIDATE_RESULT_SCHEMA, CandidateResult


def _scored_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "benchmark_id": "ifeval",
        "benchmark_revision": "rev",
        "case_count": 1,
        "score": 0.5,
        "metrics": {"pass_rate": 0.5, "coverage": 1.0, "anything_else": 12},
        "cases": [{"case_id": 1}],
        "failures": [],
    }
    kwargs.update(overrides)
    return kwargs


def test_wire_payload_matches_the_hand_built_v1_dict() -> None:
    """INVARIANT: migrating aggregates from dict literals to the model must be
    invisible on the wire — same keys, same order, same values."""

    payload = CandidateResult(**_scored_kwargs()).as_payload()

    assert payload == {
        "schema": CANDIDATE_RESULT_SCHEMA,
        "benchmark_id": "ifeval",
        "benchmark_revision": "rev",
        "case_count": 1,
        "score": 0.5,
        "metrics": {"pass_rate": 0.5, "coverage": 1.0, "anything_else": 12},
        "cases": [{"case_id": 1}],
        "failures": [],
    }
    assert list(payload) == [
        "schema",
        "benchmark_id",
        "benchmark_revision",
        "case_count",
        "score",
        "metrics",
        "cases",
        "failures",
    ]


def test_a_scored_result_without_the_canonical_trio_is_rejected() -> None:
    """INVARIANT: scored ⇒ metrics carries pass_rate AND coverage in [0, 1] — the SDK
    report tiles and its low-coverage warning read exactly these keys, so an aggregate
    that omits one ships dash tiles; the model makes that a unit-test failure."""

    for missing in ("pass_rate", "coverage"):
        metrics = {"pass_rate": 0.5, "coverage": 1.0}
        del metrics[missing]
        with pytest.raises(ValidationError, match=missing):
            CandidateResult(**_scored_kwargs(metrics=metrics))


def test_canonical_metrics_must_be_fractions() -> None:
    with pytest.raises(ValidationError, match="pass_rate"):
        CandidateResult(**_scored_kwargs(metrics={"pass_rate": 1.5, "coverage": 1.0}))
    with pytest.raises(ValidationError, match="coverage"):
        CandidateResult(**_scored_kwargs(metrics={"pass_rate": 0.5, "coverage": True}))


def test_a_negative_score_is_valid_on_the_wire() -> None:
    """INVARIANT: `score` has NO lower bound — healthbench's unclipped mean goes
    negative when rubric penalties dominate, and those scores are rankable challenge
    results. Only the upper bound (1.0) and the trio metrics' [0, 1] range hold."""

    payload = CandidateResult(
        **_scored_kwargs(score=-3.0, metrics={"pass_rate": 1.0, "coverage": 1.0})
    ).as_payload()
    assert payload["score"] == -3.0
    with pytest.raises(ValidationError):
        CandidateResult(**_scored_kwargs(score=1.5))


def test_an_unscored_result_cannot_carry_metrics() -> None:
    """INVARIANT: score None ⇒ metrics {} — a failed run never publishes a plausible
    partial score (nor plausible partial metrics)."""

    unscored = CandidateResult(**_scored_kwargs(score=None, metrics={}))
    assert unscored.as_payload()["score"] is None

    with pytest.raises(ValidationError, match="unscored"):
        CandidateResult(**_scored_kwargs(score=None))


def test_case_count_must_equal_the_retained_cases() -> None:
    """INVARIANT: case_count is EXACT — one entry per selected Case, scored or failed."""

    with pytest.raises(ValidationError, match="case_count"):
        CandidateResult(**_scored_kwargs(case_count=2))


def test_score_must_be_a_fraction_or_none() -> None:
    with pytest.raises(ValidationError):
        CandidateResult(**_scored_kwargs(score=1.2))
