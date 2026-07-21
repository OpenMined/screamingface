"""Rich and text presentation contracts for benchmark reports."""

from __future__ import annotations

from typing import Any, cast

import pytest

import screamingface as sf


def _members(score_one: float | None, score_two: float | None) -> dict[str, sf.MemberReport]:
    return {
        "member_1": sf.MemberReport(model="worker/one", score=score_one, metrics={}),
        "member_2": sf.MemberReport(model="worker/two", score=score_two, metrics={}),
    }


def _complete_report() -> sf.Report:
    return sf.Report(
        benchmark_id="example@1",
        recipe_name="complete-fusion",
        url4="(benchmark-run)",
        n_cases=2,
        n_scored=2,
        coverage=1.0,
        score=0.75,
        baseline=0.5,
        gain=0.25,
        members=_members(0.5, 0.25),
        metrics={"pass_rate": 0.75},
        failures=(),
    )


def _partial_report() -> sf.Report:
    failure = sf.EvaluationFailure("q3", "timeout", "Judge timed out")
    return sf.Report(
        benchmark_id="example@1",
        recipe_name="partial-fusion",
        url4="(benchmark-run)",
        n_cases=3,
        n_scored=2,
        coverage=2 / 3,
        score=0.75,
        baseline=0.5,
        gain=0.25,
        members=_members(0.5, 0.25),
        metrics={},
        failures=(failure,),
    )


def _failed_report() -> sf.Report:
    failures = (
        sf.EvaluationFailure("q1", "url4", "Gateway rejected <request>"),
        sf.EvaluationFailure("q2", "url4", "Gateway rejected <request>"),
        sf.EvaluationFailure("q3", "connection", "Gateway unavailable"),
    )
    return sf.Report(
        benchmark_id="example@1",
        recipe_name="failed-fusion",
        url4="(benchmark-run)",
        n_cases=3,
        n_scored=0,
        coverage=0.0,
        score=None,
        baseline=None,
        gain=None,
        members=_members(None, None),
        metrics={},
        failures=failures,
    )


def _stopped_report() -> sf.Report:
    failures = (
        sf.EvaluationFailure(
            "q1",
            "url4",
            "AI Gateway returned HTTP 502 (provider_unavailable) for 'gemini/2.5-flash'",
            status=502,
            code="provider_unavailable",
        ),
        *(
            sf.EvaluationFailure(
                f"q{index}",
                "skipped",
                "Case was not scheduled after evaluation stopped on 'provider_unavailable'.",
                code="not_scheduled",
            )
            for index in range(2, 6)
        ),
    )
    return sf.Report(
        benchmark_id="gpqa@1",
        recipe_name="frontier-trio",
        url4="(benchmark-run)",
        n_cases=5,
        n_scored=0,
        coverage=0.0,
        score=None,
        baseline=None,
        gain=None,
        members=_members(None, None),
        metrics={},
        failures=failures,
    )


def test_complete_report_has_rich_metrics_and_concise_text() -> None:
    report = _complete_report()

    text = repr(report)
    html = report._repr_html_()

    assert "status='complete'" in text
    assert "scored=2/2" in text
    assert "score=0.750" in text
    assert "sf-report-status complete'>complete · 2/2 cases scored" in html
    assert "75.0<span class='sf-report-unit'>%</span>" in html
    assert "+25.0<span class='sf-report-unit'> pp</span>" in html
    assert "Additional metrics" in html
    assert "pass rate" in html
    assert "Member scores" in html


def test_partial_report_preserves_metrics_and_surfaces_failures() -> None:
    report = _partial_report()

    text = repr(report)
    html = report._repr_html_()

    assert "status='partial'" in text
    assert "scored=2/3" in text
    assert "failures=1" in text
    assert "sf-report-status partial'>partial · 2/3 cases scored" in html
    assert "Judge timed out" in html
    assert "paired coverage 66.7%" in html


def test_failed_report_explains_missing_metrics_without_rendering_none() -> None:
    report = _failed_report()

    text = repr(report)
    html = report._repr_html_()

    assert "status='failed'" in text
    assert "scored=0/3" in text
    assert "failures=3" in text
    assert "None" not in text
    assert "sf-report-status failed'>failed · 0/3 cases scored" in html
    assert "No benchmark score was calculated." in html
    assert "fusion score" not in html
    assert "None" not in html
    assert "Gateway rejected &lt;request&gt;" in html
    assert "×2" in html
    assert report.to_dict()["score"] is None


def test_stopped_report_distinguishes_one_failure_from_four_skipped_cases() -> None:
    report = _stopped_report()

    text = repr(report)
    html = report._repr_html_()

    assert "status='stopped'" in text
    assert "failures=1" in text
    assert "skipped=4" in text
    assert "sf-report-status stopped'>stopped · 0/5 cases scored" in html
    assert "1 case failed; 4 later cases were not run." in html
    assert "Every selected case failed" not in html
    assert "Evaluation failures · 1" in html
    assert "Skipped cases · 4" in html
    assert "provider_unavailable" in html
    assert "×4" in html


def test_notebook_display_follows_screamingface_visual_rules_in_both_themes() -> None:
    html = _complete_report()._repr_html_()

    assert 'font-family:"IBM Plex Sans"' in html
    assert 'font-family: "IBM Plex Mono"' in html
    assert "var(--sf-line)" in html
    assert "var(--sf-gain)" in html
    assert "prefers-color-scheme:dark" in html
    assert ".jp-mod-theme-dark .sf-ui" in html
    assert ".jp-mod-theme-light .sf-ui" in html
    assert "class='sf-ui sf-report'" in html
    assert "border-radius" not in html
    assert "box-shadow" not in html
    assert "gradient" not in html


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: sf.EvaluationFailure("", "url4", "failed"), "case ID"),
        (
            lambda: sf.EvaluationFailure("q1", cast(Any, "unknown"), "failed"),
            "unknown evaluation failure kind",
        ),
        (lambda: sf.EvaluationFailure("q1", "url4", ""), "message"),
        (lambda: sf.EvaluationFailure("q1", "url4", "failed", status=99), "status"),
        (lambda: sf.EvaluationFailure("q1", "url4", "failed", code=" "), "code"),
    ],
)
def test_evaluation_failure_is_strict(factory, message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        factory()


def _report_changes(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "benchmark_id": "example@1",
        "recipe_name": "fusion",
        "url4": "(run)",
        "n_cases": 2,
        "n_scored": 2,
        "coverage": 1.0,
        "score": 0.75,
        "baseline": 0.5,
        "gain": 0.25,
        "members": _members(0.5, 0.25),
        "metrics": {},
        "failures": (),
    }
    values.update(changes)
    return values


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"n_cases": 0}, "positive integer"),
        ({"n_scored": -1}, "non-negative"),
        ({"n_scored": 3}, "cannot exceed"),
        ({"coverage": 0.5}, "must equal"),
        ({"score": None}, "requires all headline"),
        ({"members": _members(None, 0.25)}, "requires every member score"),
        ({"baseline": 0.25}, "best member"),
        ({"gain": 0.0}, "score - baseline"),
        ({"members": {}}, "at least one member"),
        ({"members": {"panel": sf.MemberReport(model="m", score=0.5, metrics={})}}, "contiguous"),
        ({"members": {"member_1": "wrong"}}, "sf.MemberReport"),
        ({"metrics": cast(Any, [])}, "mapping"),
        ({"score": 2.0}, "between 0 and 1"),
        ({"gain": 2.0}, "between -1 and 1"),
        ({"failures": cast(Any, ["wrong"])}, "sf.EvaluationFailure"),
    ],
)
def test_report_rejects_incoherent_states(changes: dict[str, object], message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        sf.Report(**cast(Any, _report_changes(**changes)))


def test_unscored_report_rejects_hidden_scores_and_metrics() -> None:
    common = {
        "n_cases": 1,
        "n_scored": 0,
        "coverage": 0.0,
        "score": None,
        "baseline": None,
        "gain": None,
        "failures": (sf.EvaluationFailure("q1", "url4", "failed"),),
    }
    with pytest.raises(ValueError, match="headline"):
        sf.Report(**cast(Any, _report_changes(**{**common, "score": 0.0})))
    with pytest.raises(ValueError, match="member scores or metrics"):
        sf.Report(**cast(Any, _report_changes(**{**common, "metrics": {"accuracy": 0.0}})))
    members = {
        "member_1": sf.MemberReport(model="worker/one", score=None, metrics={"x": 0.0}),
        "member_2": sf.MemberReport(model="worker/two", score=None, metrics={}),
    }
    with pytest.raises(ValueError, match="member metrics"):
        sf.Report(**cast(Any, _report_changes(**{**common, "members": members})))
