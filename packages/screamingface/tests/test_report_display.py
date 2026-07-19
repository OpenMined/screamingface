"""Rich and text presentation contracts for benchmark reports."""

from __future__ import annotations

import screamingface as sf


def _members(score_one: float | None, score_two: float | None) -> dict[str, sf.MemberReport]:
    return {
        "member_1": sf.MemberReport(model="worker/one", score=score_one, metrics={}),
        "member_2": sf.MemberReport(model="worker/two", score=score_two, metrics={}),
    }


def _complete_report() -> sf.Report:
    return sf.Report(
        benchmark_id="example@1",
        fusion_name="complete-fusion",
        fusion_url4="(recipe)",
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
    failure = sf.RunFailure("q3", "timeout", "Judge timed out")
    return sf.Report(
        benchmark_id="example@1",
        fusion_name="partial-fusion",
        fusion_url4="(recipe)",
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
        sf.RunFailure("q1", "url4", "Gateway rejected <request>"),
        sf.RunFailure("q2", "url4", "Gateway rejected <request>"),
        sf.RunFailure("q3", "connection", "Gateway unavailable"),
    )
    return sf.Report(
        benchmark_id="example@1",
        fusion_name="failed-fusion",
        fusion_url4="(recipe)",
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


def test_notebook_display_follows_screamingface_visual_rules_in_both_themes() -> None:
    html = _complete_report()._repr_html_()

    assert 'font-family: "IBM Plex Sans"' in html
    assert 'font-family: "IBM Plex Mono"' in html
    assert "var(--sf-line)" in html
    assert "var(--sf-gain)" in html
    assert "prefers-color-scheme: dark" in html
    assert ".jp-mod-theme-dark .sf-report" in html
    assert ".jp-mod-theme-light .sf-report" in html
    assert "border-radius" not in html
    assert "box-shadow" not in html
    assert "gradient" not in html
