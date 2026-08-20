"""A criterion chip reads PASS/FAIL — the score consequence — never the raw judge word (OME-900).

FEATURE: rubric benchmarks (DRACO, HealthBench) mix positive and negative criteria and
the judge's MET/UNMET verdict is polarity-blind, so printing it as the chip text made
green chips read "UNMET" and red chips read "MET" on negative criteria.
STORY: as a researcher reading a case, every chip says PASS when the criterion helped
the score and FAIL when it hurt, with the judge's raw verdict kept visible in the chip's
tooltip so archived verdicts stay auditable.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import screamingface as sf
from screamingface._ui.report_view import report_html
from screamingface.case_result import CaseGrade, CaseResult, Check, CheckOutcome
from screamingface.operation import OperationInfo
from screamingface.report import BenchmarkInfo, CandidateResult, Report

_BENCHMARK = BenchmarkInfo(id="draco", revision="r1", case_count=1)
_START = datetime(2026, 8, 20, 10, 0, tzinfo=UTC)
_END = datetime(2026, 8, 20, 10, 5, tzinfo=UTC)


def _check(label: str, outcome: CheckOutcome | None, metadata: dict[str, Any]) -> Check:
    return Check(
        type="criterion",
        id=label,
        label=label,
        evidence=[],
        outcome=outcome,
        metadata=metadata,
    )


def _case(*checks: Check, score: float | None = 0.8) -> CaseResult:
    return CaseResult(
        case_id=1,
        input="the prompt",
        output="the answer",
        finish_reason="stop",
        grade=CaseGrade(method="rubric", score=score, metrics={}, checks=list(checks)),
        failures=[],
        metadata={},
    )


def _report(case: CaseResult) -> Report:
    candidate = CandidateResult(
        benchmark=_BENCHMARK,
        run_id="run-m",
        started_at=_START,
        completed_at=_END,
        name="m",
        kind="model",
        url4="(candidate:0.0:'(m:0.0:/openrouter/x)!\\'$m\\'')!''",
        models=["openrouter/x"],
        operations=[OperationInfo(id="op", kind="model", label="answer", depends_on=())],
        score=case.grade.score if case.grade else None,
        coverage=1.0,
        metrics={"mean": 0.8} if case.grade and case.grade.score else {},
        cases=[case],
        members=[],
        failures=[],
        usage=sf.Usage(input_tokens=10, output_tokens=10),
    )
    return Report(benchmark=_BENCHMARK, case_count=1, candidates=[candidate])


def _chip(check: Check) -> str:
    """The single rendered check row — narrow the haystack to one chip's markup."""

    html = report_html(_report(_case(check)))
    start = html.index("<div class='sf-check'>")
    return html[start : html.index("</div>", start)]


# ── The four display-table rows, DRACO vocabulary (criterion_type) ──────────────


def test_positive_met_reads_pass_in_green() -> None:
    chip = _chip(_check("cites sources", "MET", {"criterion_type": "positive"}))

    assert ">PASS</span>" in chip.replace("<i class='sq'></i>", ">")
    assert "sf-badge--ok" in chip


def test_positive_unmet_reads_fail_in_red() -> None:
    chip = _chip(_check("cites sources", "UNMET", {"criterion_type": "positive"}))

    assert "FAIL" in chip
    assert "sf-badge--bad" in chip


def test_negative_unmet_reads_pass_in_green() -> None:
    # INVARIANT: avoiding the bad thing is good news — the chip must not read like a miss.
    chip = _chip(_check("invents a dosage", "UNMET", {"criterion_type": "negative"}))

    assert "PASS" in chip
    assert "sf-badge--ok" in chip
    assert "UNMET</span>" not in chip  # the raw word never appears as the chip text


def test_negative_met_reads_fail_in_red() -> None:
    chip = _chip(_check("invents a dosage", "MET", {"criterion_type": "negative"}))

    assert "FAIL" in chip
    assert "sf-badge--bad" in chip


# ── HealthBench vocabulary: polarity is the sign of metadata.points ─────────────


def test_healthbench_positive_points_met_reads_pass() -> None:
    chip = _chip(_check("recommends a doctor", "MET", {"points": 5}))

    assert "PASS" in chip
    assert "sf-badge--ok" in chip


def test_healthbench_negative_points_met_reads_fail_in_red() -> None:
    # INVARIANT (the OME-900 color bug): a criterion that subtracted score can never
    # render green — before this fix, signed points were ignored and this chip was
    # a green "MET".
    chip = _chip(_check("invents a dosage", "MET", {"points": -3}))

    assert "FAIL" in chip
    assert "sf-badge--bad" in chip
    assert "sf-badge--ok" not in chip


def test_healthbench_negative_points_unmet_reads_pass() -> None:
    chip = _chip(_check("invents a dosage", "UNMET", {"points": -3}))

    assert "PASS" in chip
    assert "sf-badge--ok" in chip


# ── The raw judge verdict stays auditable on the chip ───────────────────────────


def test_tooltip_keeps_the_raw_judge_verdict() -> None:
    chip = _chip(_check("cites sources", "MET", {"criterion_type": "positive"}))

    assert "judge: MET" in chip


def test_negative_tooltip_glosses_the_inversion() -> None:
    # The one place MET-but-FAIL is explained: the tooltip names what happened.
    met = _chip(_check("invents a dosage", "MET", {"criterion_type": "negative"}))
    unmet = _chip(_check("invents a dosage", "UNMET", {"criterion_type": "negative"}))

    assert "judge: MET (did the thing to avoid)" in met
    assert "judge: UNMET (avoided)" in unmet


# ── Ripple: the case verdict rail inherits the points-sign fix ──────────────────


def test_a_tripped_healthbench_penalty_marks_the_case_incorrect() -> None:
    # INVARIANT: _case_passed shares the polarity rule — a case whose only judged
    # check is a tripped penalty (MET on negative points) cannot read as passed.
    html = report_html(_report(_case(_check("invents a dosage", "MET", {"points": -3}))))

    # The badge markup, not the stylesheet (a CSS comment also says "incorrect").
    assert "</i>incorrect</span>" in html


def test_unjudged_stays_the_neutral_badge() -> None:
    # OME-848 invariant restated at the chip level: no verdict word for the undecided.
    chip = _chip(_check("undecided", None, {"criterion_type": "positive"}))

    assert "unjudged" in chip
    assert "PASS" not in chip and "FAIL" not in chip
