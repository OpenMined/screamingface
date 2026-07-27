"""OME-639 — benchmark card adopts the evaluate/report visual language.

STORY: a researcher reads a benchmark at a glance — a stat grid of the key scalars, tools as
chips, and the grader detail in its own section — matching the polished Report widget.
INVARIANT: near-monochrome, honest fields only, injected text escaped.
"""

from __future__ import annotations

import screamingface as sf


def _rubric_benchmark() -> sf.Benchmark:
    return sf.Benchmark(
        "draco-lite@1",
        title="DRACO Lite",
        cases=[sf.Case("c1", "q", reference="a")],
        grader=sf.graders.Rubric(
            model="openrouter/google/gemini-3.1-pro-preview",
            prompt="Evaluate the response against a single criterion. " * 8,
            passes=5,
        ),
        tools=[sf.tools.WebSearch(), sf.tools.WebFetch()],
        max_tool_calls=12,
    )


def test_benchmark_card_has_a_stat_grid_with_the_key_scalars() -> None:
    html = _rubric_benchmark()._repr_html_()

    assert "sf-stats" in html
    # labels
    for label in ("aggregator", "grader", "passes", "max tool calls"):
        assert f">{label}</div>" in html or f">{label}<" in html
    # values
    assert ">mean<" in html
    assert ">rubric<" in html
    assert ">5<" in html  # passes
    assert ">12<" in html  # max tool calls


def test_benchmark_card_renders_tools_as_chips() -> None:
    html = _rubric_benchmark()._repr_html_()

    assert "sf-chip" in html
    assert "web_search" in html
    assert "web_fetch" in html


def test_benchmark_grader_section_shows_model_and_collapsible_prompt() -> None:
    html = _rubric_benchmark()._repr_html_()

    assert "<div class='sf-section__title'>grader</div>" in html
    assert "openrouter/google/gemini-3.1-pro-preview" in html
    assert "<details class='sf-more'" in html  # long prompt collapses


def test_deterministic_grader_reads_as_deterministic() -> None:
    bench = sf.Benchmark(
        "m@1", cases=[sf.Case("c1", "q", reference="a")], grader=sf.graders.ExactChoice()
    )

    html = bench._repr_html_()

    assert ">exact choice<" in html  # grader stat value
    assert "deterministic" in html


def test_benchmark_card_stays_monochrome_and_escapes_injected_text() -> None:
    bench = sf.Benchmark(
        "x@1",
        title="<script>alert(1)</script>",
        cases=[sf.Case("c1", "q", reference="a")],
        grader=sf.graders.ExactChoice(),
    )

    html = bench._repr_html_()

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "purple" not in html.lower()
