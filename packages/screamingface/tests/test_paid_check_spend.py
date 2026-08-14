"""A paid check surface tells the caller the bill before the run starts (OME-829).

FEATURE: rubric benchmarks (DRACO, HealthBench) check drafts with a judge call.
STORY: as a user pointing a three-round panel at DRACO, I learn the check-call
ceiling from a warning at planning time — not from the invoice afterwards.
"""

from __future__ import annotations

import warnings
from typing import Literal

import pytest

import screamingface as sf
from screamingface._evaluation.benchmark import _BenchmarkResource, _CheckSurface
from screamingface._evaluation.runner import _validate_check_surface
from screamingface.discovery import BenchmarkInfo
from screamingface.warnings import EvaluationWarning

_URL4 = "(answer:0.0:/candidate?q=(question)!'$candidate')!'$answer'"


def _resource(cost: Literal["free", "paid"], *, case_count: int = 100) -> _BenchmarkResource:
    return _BenchmarkResource(
        info=BenchmarkInfo(id="draco", revision="r1", case_count=case_count),
        case_count=case_count,
        url4=_URL4,
        check_surface=_CheckSurface(
            check_route="/benchmarks/draco/r1/check-surface/draco-pass.v1",
            feedback_intent="feedback",
            expected_check_cost=cost,
        ),
    )


def test_a_paid_surface_warns_with_the_check_ceiling() -> None:
    loop = sf.CorrectiveLoop(["prov/a", "prov/b"], judge="prov/j", max_rounds=3)
    with pytest.warns(EvaluationWarning, match="600 paid check calls") as caught:
        _validate_check_surface((loop,), "draco", _resource("paid", case_count=100))
    message = str(caught[0].message)
    # 2 members x 3 rounds = 6 checks per case, x 100 cases.
    assert "6 per case" in message
    assert "may retry according to the benchmark's policy" in message


def test_the_ceiling_counts_one_member_for_a_solo_loop() -> None:
    solo = sf.SelfCorrective("prov/a", max_rounds=2)
    with pytest.warns(EvaluationWarning) as caught:
        _validate_check_surface((solo,), "draco", _resource("paid", case_count=10))
    assert "20 paid check calls" in str(caught[0].message)


def test_several_loops_bill_together() -> None:
    loops = (
        sf.CorrectiveLoop(["prov/a", "prov/b"], judge="prov/j", max_rounds=2),
        sf.SelfCorrective("prov/c", max_rounds=2),
    )
    with pytest.warns(EvaluationWarning) as caught:
        _validate_check_surface(loops, "draco", _resource("paid", case_count=5))
    # (2x2) + (1x2) = 6 checks per case, x 5 cases.
    assert "30 paid check calls" in str(caught[0].message)


def test_a_free_surface_stays_silent() -> None:
    # INVARIANT: the warning is about MONEY, so a deterministic checker must never
    # trigger it — a warning that cries wolf on IFEval gets filtered and then the
    # DRACO one goes unread too.
    loop = sf.CorrectiveLoop(["prov/a", "prov/b"], judge="prov/j")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _validate_check_surface((loop,), "ifeval", _resource("free"))


def test_a_non_loop_candidate_is_never_billed_for_checks() -> None:
    fusion = sf.Fusion(["prov/a", "prov/b"], synthesizer="prov/s")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _validate_check_surface((fusion,), "draco", _resource("paid"))
