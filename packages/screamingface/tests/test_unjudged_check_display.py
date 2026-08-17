"""A check without an outcome renders as unjudged — never as a verdict (OME-848).

FEATURE: DRACO shipped checks with no top-level outcome, and the view's good/bad
logic collapsed None to "not MET" — every positive criterion painted red and every
negative green, verdict-blind, and every case chipped INCORRECT.
STORY: as a researcher reading a case, a criterion the judges never decided shows a
neutral "unjudged" badge and does not tip the case verdict either way; judged
criteria alone decide it.
"""

from __future__ import annotations

from datetime import UTC, datetime

import screamingface as sf
from screamingface._ui.report_view import report_html
from screamingface.case_result import CaseGrade, CaseResult, Check
from screamingface.operation import OperationInfo
from screamingface.report import BenchmarkInfo, CandidateResult, Report

_BENCHMARK = BenchmarkInfo(id="draco", revision="r1", case_count=1)
_START = datetime(2026, 8, 17, 10, 0, tzinfo=UTC)
_END = datetime(2026, 8, 17, 10, 5, tzinfo=UTC)


def _check(label: str, outcome: str | None, *, kind: str = "positive") -> Check:
    return Check(
        type="criterion",
        id=label,
        label=label,
        evidence=[],
        outcome=outcome,
        metadata={"criterion_type": kind},
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


def _body(html: str) -> str:
    return html[html.index("<div class='sf-ui") :]


def test_an_outcomeless_check_renders_unjudged_not_a_verdict() -> None:
    html = _body(report_html(_report(_case(_check("says hi", None)))))

    assert "unjudged" in html
    # Neither verdict color may claim the undecided criterion.
    assert "sf-badge--warn" in html


def test_unjudged_checks_do_not_flip_a_good_case_to_incorrect() -> None:
    # One judged good criterion + one undecided: the case verdict follows the
    # JUDGED evidence — absence must not masquerade as failure (the pre-fix draco
    # state painted every such case INCORRECT).
    html = _body(report_html(_report(_case(_check("says hi", "MET"), _check("undecided", None)))))

    assert "incorrect" not in html


def test_a_judged_miss_still_decides_the_case() -> None:
    # The hardening must not soften real verdicts: one honest UNMET on a positive
    # criterion keeps the case incorrect even beside unjudged neighbours.
    graded = _case(
        _check("says hi", "MET"), _check("cites sources", "UNMET"), _check("undecided", None)
    )
    html = _body(report_html(_report(graded)))

    assert "incorrect" in html


def test_all_unjudged_falls_back_to_the_score() -> None:
    # No judged checks at all: the positive score is the only signal — the case
    # reads as passed, exactly like the pre-existing no-checks fallback.
    html = _body(report_html(_report(_case(_check("says hi", None), score=0.8))))

    assert "incorrect" not in html
