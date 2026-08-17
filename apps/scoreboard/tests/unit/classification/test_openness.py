"""Unit tests for the open/closed classification registry (OME-323, spec §4/§9).

Pure logic, no DB — exercises classify_providers/classify_baseline_name (the
registry internals) and classify_score/classify_baseline (the override-aware
wrappers Phase 2 actually calls).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

import pytest

from scoreboard.classification.openness import (
    classify_baseline,
    classify_baseline_name,
    classify_providers,
    classify_score,
)
from scoreboard.scores.schemas import BaselineSchema, ScoreSchema


def _score(
    *,
    ran_with_providers: list[str],
    openness_override: Literal["open", "closed"] | None = None,
) -> ScoreSchema:
    return ScoreSchema(
        id=uuid4(),
        version=1,
        benchmark_id="hle",
        # OME-852: required since OME-775. None is honest here — frontier and openness
        # classification do not depend on which benchmark revision produced the score.
        benchmark_revision=None,
        # OME-770 made this required: a nullable-but-required field means a construction
        # site cannot silently omit a cost, which would read as free rather than unknown.
        # None is honest here — frontier and openness classification ignore cost.
        run_cost_usd=None,
        spec_id="spec-1",
        url4_expression="url4://benchmark/spec-1",
        submitted_by="tester",
        submitted_at=datetime(2026, 8, 6, tzinfo=UTC),
        accuracy=0.5,
        total_questions=10,
        correct_questions=5,
        ran_with_providers=ran_with_providers,
        ran_at_local=None,
        client_name=None,
        client_version=None,
        client_platform=None,
        verified_by_screamingface=False,
        metadata=None,
        openness_override=openness_override,
    )


def _baseline(
    *,
    model_name: str,
    openness_override: Literal["open", "closed"] | None = None,
) -> BaselineSchema:
    return BaselineSchema(
        id=uuid4(),
        benchmark_id="hle",
        model_name=model_name,
        accuracy=0.5,
        source="lmarena",
        source_url=None,
        imported_at=datetime(2026, 8, 6, tzinfo=UTC),
        metadata=None,
        openness_override=openness_override,
    )


# --- classify_providers ------------------------------------------------------------


def test_known_open_provider_is_open() -> None:
    assert classify_providers(["huggingface"]) == "open"


def test_known_closed_provider_is_closed() -> None:
    assert classify_providers(["openai"]) == "closed"


def test_mixed_open_and_closed_providers_is_closed() -> None:
    """Spec §4's mixed-fusion rule: closed if ANY provider is closed."""
    assert classify_providers(["huggingface", "openai"]) == "closed"


def test_all_open_providers_is_open() -> None:
    assert classify_providers(["huggingface", "mistral"]) == "open"


def test_unrecognized_provider_is_closed(caplog: pytest.LogCaptureFixture) -> None:
    """Fail-closed default, and it must be logged, not silent (spec §4 staleness
    resolution)."""
    with caplog.at_level("WARNING"):
        result = classify_providers(["some-brand-new-provider"])

    assert result == "closed"
    assert "some-brand-new-provider" in caplog.text


def test_empty_providers_is_closed(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING"):
        result = classify_providers([])

    assert result == "closed"


# --- classify_baseline_name --------------------------------------------------------


def test_known_open_baseline_model_is_open() -> None:
    assert classify_baseline_name("meta-llama/Llama-3-70B") == "open"


def test_known_closed_baseline_model_is_closed() -> None:
    assert classify_baseline_name("gpt-5.2") == "closed"


def test_unrecognized_baseline_model_is_closed(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING"):
        result = classify_baseline_name("some-brand-new-model")

    assert result == "closed"
    assert "some-brand-new-model" in caplog.text


# --- classify_score (override-aware) -----------------------------------------------


def test_classify_score_defers_to_registry_when_no_override() -> None:
    assert classify_score(_score(ran_with_providers=["huggingface"])) == "open"


def test_classify_score_override_forces_open_despite_closed_providers() -> None:
    score = _score(ran_with_providers=["openai"], openness_override="open")
    assert classify_score(score) == "open"


def test_classify_score_override_forces_closed_despite_open_providers() -> None:
    score = _score(ran_with_providers=["huggingface"], openness_override="closed")
    assert classify_score(score) == "closed"


# --- classify_baseline (override-aware) --------------------------------------------


def test_classify_baseline_defers_to_registry_when_no_override() -> None:
    assert classify_baseline(_baseline(model_name="gpt-5.2")) == "closed"


def test_classify_baseline_override_forces_open_despite_closed_name() -> None:
    baseline = _baseline(model_name="gpt-5.2", openness_override="open")
    assert classify_baseline(baseline) == "open"


def test_classify_baseline_override_forces_closed_despite_open_name() -> None:
    baseline = _baseline(model_name="meta-llama/Llama-3-70B", openness_override="closed")
    assert classify_baseline(baseline) == "closed"
