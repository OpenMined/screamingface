"""The Report panel: gold rationing, real figures, and untrusted-text handling."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import cast

import screamingface as sf
from screamingface._ui.report_view import (
    _axes_html,
    _bytes,
    _cases_html,
    _clip,
    _compact,
    _duration,
    _failures_html,
    _grading_html,
    _money,
    _number,
    _tokens,
    _tokens_total,
    report_html,
)
from screamingface.case_result import CaseGrade, CaseResult, Check, Evidence, EvidenceProducer
from screamingface.operation import OperationInfo
from screamingface.report import BenchmarkInfo, CandidateResult, Report

_START = datetime(2026, 8, 7, 17, 28, 8, tzinfo=UTC)
_END = datetime(2026, 8, 7, 17, 28, 28, tzinfo=UTC)
_METRICS = {"pass_rate": 0.5, "coverage": 1.0, "verdicts_expected": 1, "verdicts_accepted": 1}
_BENCHMARK = BenchmarkInfo("draco/smoke", "74c94830e8de6afd", 1)


def case(*, checks: tuple[Check, ...] = (), score: float | None = 0.0) -> CaseResult:
    return CaseResult(
        case_id=1,
        input="the prompt",
        output="the answer",
        finish_reason="stop",
        grade=CaseGrade(method="rubric", score=score, metrics={}, checks=list(checks)),
        failures=[],
        metadata={},
    )


def candidate(
    name: str, score: float | None, *, cases: tuple[CaseResult, ...] = ()
) -> CandidateResult:
    return CandidateResult(
        benchmark=_BENCHMARK,
        run_id=f"run-{name}",
        started_at=_START,
        completed_at=_END,
        name=name,
        kind="model",
        url4="(candidate:0.0:'(m:0.0:/openrouter/x)!\\'$m\\'')!''",
        models=["openrouter/x"],
        operations=[OperationInfo(id="op", kind="model", label="answer", depends_on=())],
        score=score,
        # the model forbids metrics on an unscored Candidate
        metrics=_METRICS if score is not None else {},
        cases=list(cases) or [case()],
        members=[],
        failures=[],
        usage=sf.Usage(input_tokens=3449, output_tokens=2340),
    )


def body(html: str) -> str:
    """Markup only — every class name also occurs in the embedded stylesheets."""

    return html[html.index("<div class='sf-ui") :]


def report(*candidates: CandidateResult) -> Report:
    return Report(
        benchmark=_BENCHMARK,
        case_count=1,
        candidates=list(candidates),
    )


def test_a_real_score_carries_the_fusion_edge() -> None:
    html = body(report_html(report(candidate("gemini-3-flash-preview", 0.62))))

    assert "sf-report__cell--score" in html
    assert "62.0%" in html


def test_a_zero_score_is_not_gilded() -> None:
    html = body(report_html(report(candidate("m", 0.0))))

    # Colour means something: there is no win in a zero, so the cell stays neutral.
    assert "sf-report__cell--score" not in html
    assert "0.0%" in html


def test_an_ungraded_candidate_is_not_gilded_and_reads_as_incomplete() -> None:
    html = body(report_html(report(candidate("m", None))))

    assert "sf-report__cell--score" not in html
    assert "incomplete" in html


def test_every_candidate_gets_its_own_result_card() -> None:
    html = body(
        report_html(
            report(
                candidate("a", 0.62),
                candidate("fusion-a7f3", 0.814),
                candidate("c", 0.71),
            )
        )
    )

    assert html.count("sf-report__card'") == 3
    assert "81.4%" in html


def test_the_receipt_strip_totals_the_whole_run() -> None:
    html = body(report_html(report(candidate("a", 0.62), candidate("b", 0.71))))

    # Two candidates at 3449/2340 tokens each.
    assert "6.9k / 4.7k tokens" in html
    assert "1 case" in html


def test_zero_score_and_unmet_criterion_render_without_claiming_success() -> None:
    check = Check(
        type="criterion",
        id="twfe",
        label="States TWFE coefficient is a variance-weighted average",
        outcome="UNMET",
        evidence=[
            Evidence(
                sequence=1,
                producer=EvidenceProducer("model", "openrouter/google/gemini-3.1-pro-preview"),
                valid=True,
                raw_output="{}",
                outcome="UNMET",
                explanation="It fails to specify 'variance-weighted'.",
            )
        ],
        metadata={"criterion_type": "positive", "weight": 10},
    )
    html = body(report_html(report(candidate("m", 0.0, cases=(case(checks=(check,)),)))))

    assert "UNMET" in html
    assert "sf-badge--bad" in html
    assert "sf-badge--ok" not in html
    assert "variance-weighted" in html


def test_a_negative_criterion_marked_met_is_not_painted_as_a_pass() -> None:
    check = Check(
        type="criterion",
        id="bad-advice",
        label="States that the patient has celiac disease",
        outcome="MET",
        evidence=[],
        metadata={"criterion_type": "negative"},
    )
    html = body(report_html(report(candidate("m", 0.0, cases=(case(checks=(check,)),)))))

    # MET on a negative criterion means the error IS present — that is a failure.
    assert "sf-badge--bad" in html
    assert "sf-badge--ok" not in html


def test_untrusted_case_and_judge_text_is_escaped() -> None:
    check = Check(
        type="criterion",
        id="x",
        label="<script>alert('label')</script>",
        outcome="UNMET",
        evidence=[
            Evidence(
                sequence=1,
                producer=EvidenceProducer("model", "m"),
                valid=True,
                raw_output="{}",
                outcome="UNMET",
                explanation="<img src=x onerror=alert(1)>",
            )
        ],
        metadata={"criterion_type": "positive"},
    )
    html = body(report_html(report(candidate("m", 0.0, cases=(case(checks=(check,)),)))))

    assert "<script>" not in html
    assert "<img src=x" not in html
    assert "&lt;script&gt;" in html


def test_report_repr_html_is_wired_to_the_panel() -> None:
    value = report(candidate("m", 0.5))

    assert "sf-report__title" in body(value._repr_html_())


def test_report_formatters_keep_artifact_figures_readable() -> None:
    assert _bytes(10) == "10 B"
    assert _bytes(2_048) == "2 KB"
    assert _bytes(2 * 1_024 * 1_024) == "2.0 MB"
    assert _compact(999) == "999"
    assert _compact(2_000) == "2.0k"
    assert _compact(2_000_000) == "2.0M"
    assert _money(Decimal("0.005")) == "$0.0050"
    assert _duration(65_000) == "1m 05s"
    assert _duration(3_660_000) == "1h 01m"


def test_report_formatters_preserve_absent_and_clipped_values() -> None:
    empty_usage = sf.Usage()

    assert _number(True) is None
    assert _tokens(empty_usage) == "—"
    assert _tokens_total(empty_usage) == "—"
    assert _clip(None) == ""
    assert _clip("abcdef", 3) == "abc\n… 3 more characters"


def test_axis_and_grading_details_render_only_meaningful_differences() -> None:
    axes = _axes_html(
        {
            "axis_scores": {"factual-accuracy": 0.5},
            "axis_pass_rates": {"factual-accuracy": 0.75},
        }
    )
    grading = _grading_html(
        {
            "verdicts_rejected": 1,
            "verdicts_invalid": 2,
            "verdicts_missing": 0,
            "verdicts_expected": 5,
        }
    )

    assert "by axis" in axes
    assert "factual-accuracy" in axes
    assert "75.0% pass" in axes
    assert "1 rejected · 2 invalid" in grading
    assert "of 5 verdicts" in grading


def multi_case_report(*cases: CaseResult) -> Report:
    """A Report sized to its cases — Report validation pins case_count to the Benchmark."""

    benchmark = BenchmarkInfo("draco/smoke", "74c94830e8de6afd", len(cases))
    inner = candidate("open_trio", None, cases=cases)
    sized = CandidateResult(
        benchmark=benchmark,
        run_id=inner.run_id,
        started_at=_START,
        completed_at=_END,
        name=inner.name,
        kind=inner.kind,
        url4=inner.url4,
        models=list(inner.models),
        operations=list(inner.operations),
        score=None,
        metrics={},
        cases=list(cases),
        members=[],
        failures=[],
        usage=sf.Usage(input_tokens=3449, output_tokens=2340),
    )
    return Report(benchmark=benchmark, case_count=len(cases), candidates=[sized])


def failed_case(case_id: int = 153) -> CaseResult:
    """A Case the Engine could not grade — the OME-793 incident shape."""

    return CaseResult(
        case_id=case_id,
        input=None,
        output=None,
        finish_reason=None,
        grade=None,
        failures=[
            sf.Failure(
                stage="candidate",
                code="missing_case_row",
                message="no evaluation row for this Case reached the aggregate",
                case_id=case_id,
                metadata={
                    "collected_errors": [
                        {
                            "error": {
                                "kind": "ResolutionError",
                                "message": "malformed aigateway response",
                            }
                        }
                    ]
                },
            )
        ],
        metadata={},
    )


# WHY (OME-793): an infra failure must never present as a wrong answer — the badge is the
# first thing a reader trusts, and "incorrect" on a never-graded case misreports the run.
def test_a_failed_case_is_not_painted_as_incorrect() -> None:
    html = body(report_html(report(candidate("open_trio", None, cases=(failed_case(),)))))

    assert "failed" in html
    assert "incorrect" not in html
    assert "sf-badge--warn" in html
    assert "sf-mark--warn" in html


# INVARIANT (OME-793): the pane must surface the failure chain the report already carries —
# stage, code, message, and the underlying collected error — not an empty body.
def test_a_failed_case_pane_shows_the_failure_chain_not_nothing() -> None:
    html = body(report_html(report(candidate("open_trio", None, cases=(failed_case(),)))))

    assert "missing_case_row" in html
    assert "no evaluation row for this Case reached the aggregate" in html
    assert "ResolutionError: malformed aigateway response" in html
    assert "input unavailable" in html


# WHY (OME-793): three identical banner lines with no ids forced readers into raw JSON;
# grouping keeps the count while naming every case.
def test_the_failure_banner_names_cases_and_groups_identical_failures() -> None:
    value = multi_case_report(failed_case(153), failed_case(149), failed_case(418))
    banner = _failures_html(value)

    assert "3 failures" in banner
    assert "cases 153, 149, 418" in banner
    assert "missing_case_row" in banner
    assert "ResolutionError: malformed aigateway response" in banner
    # Grouped: the shared message appears ONCE in the banner, not three times.
    assert banner.count("no evaluation row for this Case reached the aggregate") == 1


# WHY (OME-793): a bare dash teaches readers that dashes are meaningless; the withheld
# score must say it is withheld and why (B1 keeps metrics empty when any case failed).
def test_an_unscored_candidate_explains_the_withheld_score() -> None:
    html = body(report_html(multi_case_report(case(), failed_case())))

    assert "score withheld" in html
    assert "1 of 2 cases failed" in html


def test_an_absent_cost_says_it_was_not_reported() -> None:
    html = body(report_html(report(candidate("m", 0.5))))

    assert "cost not reported" in html


def test_a_failure_without_case_id_or_collected_errors_still_renders() -> None:
    bare = sf.Failure(stage="aggregation", code="orphan_rows", message="rows without a case")
    html = _failures_html(cast(Report, SimpleNamespace(failures=(bare,))))

    assert "1 failure" in html
    assert "orphan_rows" in html
    assert "rows without a case" in html


def test_empty_cases_and_untrusted_failures_have_safe_markup() -> None:
    empty_report = cast(Report, SimpleNamespace(candidates=()))
    assert _cases_html(empty_report) == ""

    html = _failures_html(
        cast(
            Report,
            SimpleNamespace(
                failures=(SimpleNamespace(stage="run", message="<script>failed</script>"),)
            ),
        )
    )

    assert "1 failure" in html
    assert "run · &lt;script&gt;failed&lt;/script&gt;" in html
    assert "<script>" not in html


def test_an_envelope_input_renders_as_a_transcript_not_wire_json() -> None:
    """INVARIANT: multi-turn (envelope) Cases read as a conversation — the rail
    label is the user's question and the pane is a role-labeled transcript; the
    wire JSON (schema key, escapes) never reaches the researcher's eyes."""

    envelope = (
        '{"schema":"screamingface.candidate-input.v1","messages":['
        '{"role":"user","content":"How do I treat GI bleeding at home?"},'
        '{"role":"assistant","content":"Do not treat it at home."}]}'
    )
    chat_case = CaseResult(
        case_id=1,
        input=envelope,
        output="the answer",
        finish_reason="stop",
        grade=CaseGrade(method="rubric", score=0.0, metrics={}, checks=[]),
        failures=[],
        metadata={},
    )
    html = body(report_html(report(candidate("solo", 0.0, cases=(chat_case,)))))
    assert "How do I treat GI bleeding at home?" in html
    assert "user: How do I treat GI bleeding at home?" in html
    assert "assistant: Do not treat it at home." in html
    assert "candidate-input.v1" not in html
    assert "&quot;schema&quot;" not in html
