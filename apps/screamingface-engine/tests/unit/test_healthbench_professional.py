"""The HealthBench Professional board — all 525 cases, the official clipped score.

FEATURE: a HealthBench leaderboard whose number reads the same way as a published
HealthBench number.
STORY: as a fan comparing a Fusion against the figures in the HealthBench paper, I get a
board that ran the WHOLE professional exam and reports the official metric, so the
comparison is fair.

INVARIANT under test: this board is a SECOND identity over the SAME immutable answer key.
It differs from the worst-30% challenge in exactly two ways — which cases it selects and
the final clip — and in nothing else: same dataset pin, same preparer, same grader
template bytes, same judge pinning. Its address space is its own, so neither board can
serve the other's expression.
"""

from __future__ import annotations

from screamingface_engine.benchmarks.builtins import BUILTIN_BENCHMARKS
from screamingface_engine.benchmarks.healthbench.definition import (
    HEALTHBENCH_WORST30,
)
from screamingface_engine.benchmarks.healthbench.definition import (
    REVISION as WORST30_REVISION,
)
from screamingface_engine.benchmarks.healthbench.pins import CHECK_CRITERION, JUDGE_MODEL
from screamingface_engine.benchmarks.healthbench.professional import (
    BENCHMARK_ID,
    CASE_COUNT,
    CASE_IDS,
    HEALTHBENCH_PROFESSIONAL,
    REVISION,
)
from url4.core.grammar import parse


def _url4(benchmark, limit=None) -> str:
    value = benchmark.resource(limit)["url4"]
    assert isinstance(value, str)
    return value


def test_the_exam_is_registered_under_its_id() -> None:
    assert BUILTIN_BENCHMARKS.get("healthbench-professional") is HEALTHBENCH_PROFESSIONAL
    assert BENCHMARK_ID == "healthbench-professional"


def test_the_exam_serves_every_baked_professional_case() -> None:
    # WHY 1..525 with no gaps: prepare.py numbers Cases by their 1-based position in the
    # HF file, so "the whole exam" IS the contiguous range — any hole would mean a filter.
    assert CASE_COUNT == 525
    assert CASE_IDS == tuple(range(1, 526))
    assert HEALTHBENCH_PROFESSIONAL.case_count == 525


def test_the_two_boards_have_separate_addresses() -> None:
    # INVARIANT: worst30 keeps its own revision and routes — an existing submission can
    # never be re-interpreted as a professional-board submission, or vice versa.
    assert REVISION != WORST30_REVISION
    professional = _url4(HEALTHBENCH_PROFESSIONAL)
    assert f"/benchmarks/healthbench-professional/{REVISION}" in professional
    assert "healthbench-worst30" not in professional
    assert WORST30_REVISION not in professional


def test_the_exam_routes_are_revision_pinned() -> None:
    assert REVISION in _url4(HEALTHBENCH_PROFESSIONAL)


def test_the_expression_renders_and_reparses() -> None:
    rendered = _url4(HEALTHBENCH_PROFESSIONAL)
    parse(rendered)
    # S-RT1: 525 Cases must not grow the address — the per-Case and per-rubric fan-out is
    # built Engine-side, so this expression is the same size as the 157-case one.
    assert len(rendered) < 4_000


def test_the_judge_call_shape_is_the_worst30_one() -> None:
    # INVARIANT: the judge is pinned identically on both boards, so the only difference
    # between their scores is case selection plus the final clip.
    rendered = _url4(HEALTHBENCH_PROFESSIONAL)
    assert f"/{JUDGE_MODEL}?web_search=false&max_tokens=4096&q=($item.grader_prompt)!''" in rendered
    assert ";retry=2" in rendered
    assert "temperature" not in rendered


def test_the_candidate_is_invoked_without_retrieval() -> None:
    assert "/benchmarks/candidate?web_search=false" in _url4(HEALTHBENCH_PROFESSIONAL)


def test_a_limit_slices_the_run_without_redefining_the_board() -> None:
    limited = HEALTHBENCH_PROFESSIONAL.resource(3)
    # The board still IS the 525-case exam; a smoke run just executes fewer of its Cases.
    assert limited["case_count"] == 525
    assert limited["selected_case_count"] == 3
    assert "slice=0:3" in _url4(HEALTHBENCH_PROFESSIONAL, 3)


def test_the_check_surface_is_advertised_under_this_boards_prefix() -> None:
    # Capability parity with worst30 (owner decision, 2026-08-20): a corrective_loop
    # recipe runs on either board, under the SAME criterion and threshold.
    surface = HEALTHBENCH_PROFESSIONAL.check_surface
    assert surface is not None
    assert surface.check_route == (
        f"/benchmarks/{BENCHMARK_ID}/{REVISION}/check-surface/{CHECK_CRITERION}"
    )
    assert surface.expected_check_cost == "paid"
    worst30_surface = HEALTHBENCH_WORST30.check_surface
    assert worst30_surface is not None
    assert surface.feedback_intent == worst30_surface.feedback_intent
