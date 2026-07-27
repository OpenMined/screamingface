"""OME-637 — members/reducer as separate always-visible sections; grader in its own section.

STORY: a researcher reads the members and reducer without expanding a collapsed block, and the
grader's long prompt collapses within its own section.
"""

from __future__ import annotations

import screamingface as sf


def test_fusion_members_and_reducer_are_separate_uncollapsed_sections() -> None:
    fusion = sf.Fusion(
        "t",
        members=["gemini/2.5-flash"],
        reducer=sf.reducers.Model(model="codex/gpt-5.5", prompt="Synthesize."),
    )

    html = fusion._repr_html_()

    assert "<div class='sf-section__title'>members</div>" in html
    assert "<div class='sf-section__title'>reducer</div>" in html
    assert "<details class='sf-detail'" not in html  # not one collapsed combined block
    assert "codex/gpt-5.5" in html  # reducer model shown inline


def test_benchmark_grader_is_its_own_section_with_collapsible_prompt() -> None:
    bench = sf.Benchmark(
        "d@1",
        cases=[sf.Case("c", "q", reference="a")],
        grader=sf.graders.Rubric(
            model="gemini/3.1-pro-preview", prompt="Judge every criterion carefully. " * 8, passes=5
        ),
    )

    html = bench._repr_html_()

    assert "<div class='sf-section__title'>grader</div>" in html
    assert "<details class='sf-more'" in html  # long grader prompt collapses
    assert "5 passes" in html
