"""Deterministic paired aggregation for immutable benchmark grades."""

from __future__ import annotations

from collections.abc import Sequence
from statistics import fmean

from screamingface.aggregators import Mean
from screamingface.grades import CaseGrades, Grade, Grades
from screamingface.report import MemberReport, Report


def aggregate_grades(grades: Grades) -> Report:
    """Aggregate one Grades artifact with its Benchmark strategy."""

    if not isinstance(grades, Grades):
        raise TypeError("aggregation requires an sf.Grades value")
    aggregator = grades._run._benchmark.aggregator
    if not isinstance(aggregator, Mean):
        raise TypeError(f"unsupported aggregator {type(aggregator).__name__!r}")
    return _mean_report(grades)


def _mean_report(grades: Grades) -> Report:
    paired = tuple(case for case in grades.results if _is_paired(case))
    recipe_grades = tuple(case.recipe for case in paired if case.recipe is not None)

    member_reports: list[tuple[str, MemberReport]] = []
    for member_id, model in grades.members.items():
        member_grades = tuple(case.members[member_id] for case in paired)
        member_reports.append(
            (
                member_id,
                MemberReport(
                    model=model,
                    score=_mean_scores(member_grades),
                    metrics=_mean_metrics(member_grades),
                ),
            )
        )

    recipe_score = _mean_scores(recipe_grades)
    member_scores = tuple(member.score for _, member in member_reports)
    baseline = None if not paired else max(score for score in member_scores if score is not None)
    gain = None if recipe_score is None or baseline is None else recipe_score - baseline
    n_cases = len(grades.results)
    n_scored = len(paired)
    return Report(
        benchmark_id=grades.benchmark_id,
        recipe_name=grades.recipe_name,
        recipe_url4=grades.recipe_url4,
        n_cases=n_cases,
        n_scored=n_scored,
        coverage=n_scored / n_cases,
        score=recipe_score,
        baseline=baseline,
        gain=gain,
        members=member_reports,
        metrics=_mean_metrics(recipe_grades),
        failures=grades.failures,
    )


def _is_paired(case: CaseGrades) -> bool:
    return (
        case.run_failure is None
        and case.recipe is not None
        and case.recipe.valid
        and all(grade.valid for grade in case.members.values())
    )


def _mean_scores(grades: Sequence[Grade]) -> float | None:
    if not grades:
        return None
    return fmean(grade.score for grade in grades if grade.score is not None)


def _mean_metrics(grades: Sequence[Grade]) -> dict[str, float]:
    if not grades:
        return {}
    first = grades[0]
    return {
        metric: fmean(grade.metrics[metric] for grade in grades)
        for metric in first.metrics
        if all(metric in grade.metrics for grade in grades)
    }


__all__ = ["aggregate_grades"]
