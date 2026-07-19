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

fusion = sf.Fusion(
    "frontier-trio",
    models=[
        "codex/gpt-5.5",
        "gemini/2.5",
        "claude/sonnet-4.6",
    ],
    prompt=RESEARCH_PROMPT,
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
    first_member = first_result.members["panel_1"]
    return {
        "recipe": run.fusion_url4,
        "case_ids": run.case_ids,
        "first_member_model": first_member.model,
        "first_member_answer": first_member.answer,
        "fusion_answer": first_result.answer,
        "failure": first_result.failure,
        "complete": run.complete,
        "json_compatible": run.to_dict(),
    }


# Choose one workflow. Running both would create two paid evaluations.
