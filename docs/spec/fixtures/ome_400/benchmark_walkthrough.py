"""Phase 0 contract example: quickstart and explicit-stage benchmark UX."""

from __future__ import annotations

import screamingface as sf

RESEARCH_PROMPT = """\
Answer the research question thoroughly. Preserve specific facts and sources, and use
clear prose.
"""

# Uses the SDK's default URL4 engine. Temporarily, that default is the local Docker
# service at http://127.0.0.1:4404. Override it for another deployment:
# sf.config(engine="https://url4.example.org")

researchers = tuple(
    sf.Fusion(
        name,
        model=model,
        prompt=RESEARCH_PROMPT,
    )
    for name, model in (
        ("codex-researcher", "codex/gpt-5.5"),
        ("gemini-researcher", "gemini/2.5-flash"),
        ("claude-researcher", "claude/sonnet-4.6"),
    )
)

fusion = sf.Fusion(
    "frontier-trio",
    inputs=researchers,
    reducer=sf.reducers.Model(
        model="codex/gpt-5.5",
        prompt="Synthesize the labeled panel answers into one final answer.",
    ),
)


def quickstart():
    """Identity loading and all four in-memory stages behind one call."""
    return fusion.evaluate(
        "draco@1",
        first=5,
    )


def research_workflow():
    """The equivalent explicit stages; use this instead when inspecting them."""
    benchmark = sf.benchmarks.load("draco@1")
    run = fusion.run(
        benchmark,
        first=5,
    )
    grades = run.grade()
    report = grades.aggregate()
    return report


def inspect_run(run: sf.Run):
    """Phase 2C result inspection without re-running paid work."""
    first_result = run.results[0]
    first_member = first_result.members["member_1"]
    return {
        "fusion": run.fusion_name,
        "recipe": run.fusion_url4,
        "members": run.members,
        "case_ids": run.case_ids,
        "first_member_model": first_member.model,
        "first_member_answer": first_member.answer,
        "fusion_answer": first_result.answer,
        "failure": first_result.failure,
        "complete": run.complete,
        "json_compatible": run.to_dict(),
    }


def inspect_grades(grades: sf.Grades):
    """Phase 3A nested grading evidence without rerunning captured answers."""
    first_case = next(case for case in grades.results if case.fusion is not None)
    fusion_grade = first_case.fusion
    assert fusion_grade is not None
    first_member_grade = first_case.members["member_1"]
    first_verdict = fusion_grade.verdicts[0] if fusion_grade.verdicts else None
    return {
        "benchmark": grades.benchmark_id,
        "fusion": grades.fusion_name,
        "recipe": grades.fusion_url4,
        "members": grades.members,
        "grader": grades.grader,
        "case_ids": grades.case_ids,
        "fusion_score": fusion_grade.score,
        "fusion_metrics": fusion_grade.metrics,
        "fusion_coverage": fusion_grade.coverage,
        "fusion_valid": fusion_grade.valid,
        "member_score": first_member_grade.score,
        "first_verdict": first_verdict,
        "run_failure": first_case.run_failure,
        "failures": grades.failures,
        "complete": grades.complete,
        "json_compatible": grades.to_dict(),
    }


def inspect_report(report: sf.Report):
    """Phase 3A paired Fusion-versus-member comparison."""
    first_member = report.members["member_1"]
    return {
        "benchmark": report.benchmark_id,
        "fusion": report.fusion_name,
        "recipe": report.fusion_url4,
        "n_cases": report.n_cases,
        "n_scored": report.n_scored,
        "coverage": report.coverage,
        "score": report.score,
        "baseline": report.baseline,
        "gain": report.gain,
        "fusion_metrics": report.metrics,
        "first_member_model": first_member.model,
        "first_member_score": first_member.score,
        "first_member_metrics": first_member.metrics,
        "failures": report.failures,
        "complete": report.complete,
        "json_compatible": report.to_dict(),
    }


# Choose one workflow. Running both would create two paid evaluations.
