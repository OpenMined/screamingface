"""OME-635 — full-form url4 reflow, Fusion member/reducer detail, verbose Benchmark/Rubric.

FEATURE: richer, more readable cards; long fields (prompts) collapse.
INVARIANT: the url4 is kept verbatim (only whitespace added, quote/escape-aware); cards never
fabricate data and HTML-escape injected text.
"""

from __future__ import annotations

import screamingface as sf
from screamingface._url4_format import _pretty_url4

# --- full-form reflow ---------------------------------------------------------------------


def test_pretty_indents_brackets_and_preserves_quoted_intent() -> None:
    # An intent with commas, parens, and an escaped quote must survive verbatim.
    source = "(a:0.0:/x!'hi, (there) it\\'s fine', b:0.0:{k: 'v'})!'$out'"

    out = _pretty_url4(source)

    assert "(\n" in out  # opening bracket breaks + indents
    assert ",\n" in out  # top-level comma breaks
    assert "'hi, (there) it\\'s fine'" in out  # quoted intent untouched (no breaks inside)


def test_pretty_keeps_empty_brackets_inline() -> None:
    assert "()" in _pretty_url4("/reducers/majority-vote/1()!'$x'")


def test_recipe_details_collapsed_pre_and_exact_copy() -> None:
    from html import escape

    url4 = sf.Fusion("t", members=["gemini/2.5-flash"], reducer=sf.reducers.MajorityVote()).url4
    html = sf.Model("gemini/2.5-flash")._repr_html_()

    assert "sf-url4__pre" in html
    from screamingface._url4_format import recipe_details_html

    rendered = recipe_details_html(url4)
    assert " open" not in rendered  # collapsed
    assert f'data-url4="{escape(url4, quote=True)}"' in rendered


# --- Fusion member/reducer detail ---------------------------------------------------------


def test_fusion_card_exposes_member_and_reducer_detail_collapsed() -> None:
    member = sf.Model("gemini/2.5-flash", name="a", prompt="Be concise.", params={"temperature": 0})
    fusion = sf.Fusion(
        "trio", members=[member, "codex/gpt-5.5"], reducer=sf.reducers.MajorityVote()
    )

    html = fusion._repr_html_()

    assert "<div class='sf-section__title'>members</div>" in html
    assert "<div class='sf-section__title'>reducer</div>" in html
    assert "Be concise." in html  # member prompt
    assert "temperature=0" in html  # member params
    assert "deterministic" in html  # MajorityVote reducer has no prompt/params


def test_fusion_detail_shows_model_reducer_prompt_and_model() -> None:
    fusion = sf.Fusion(
        "t",
        members=["gemini/2.5-flash"],
        reducer=sf.reducers.Model(model="codex/gpt-5.5", prompt="Synthesize the answers."),
    )

    html = fusion._repr_html_()

    assert "codex/gpt-5.5" in html  # reducer model
    assert "Synthesize the answers." in html  # reducer prompt (short → inline)


# --- verbose Benchmark / Rubric -----------------------------------------------------------


def test_benchmark_card_verbose_with_collapsed_rubric_prompt() -> None:
    long_prompt = "Judge the answer against every criterion carefully. " * 8  # > 140 chars
    bench = sf.Benchmark(
        "mini@1",
        title="Mini",
        cases=[sf.Case("c1", "2+2?", reference="4")],
        grader=sf.graders.Rubric(model="gemini/3.1-pro-preview", prompt=long_prompt, passes=3),
    )

    html = bench._repr_html_()

    assert "gemini/3.1-pro-preview" in html  # grader model
    assert "3 passes" in html
    assert "<details class='sf-more'" in html  # long prompt collapsed into <details>
    assert "chars" in html  # the collapsed summary shows the length


def test_benchmark_card_marks_deterministic_grader() -> None:
    bench = sf.Benchmark(
        "m@1", cases=[sf.Case("c1", "q", reference="a")], grader=sf.graders.ExactChoice()
    )

    html = bench._repr_html_()

    assert "exact choice" in html.lower()
    assert "deterministic" in html
    assert "engine routes" not in html  # local benchmark has no engine routes


def test_engine_benchmark_shows_collapsed_routes() -> None:
    from screamingface.aggregators import Mean
    from screamingface.benchmark import Benchmark
    from screamingface.graders import ExactChoice

    bench = Benchmark._from_engine(
        "gpqa@1",
        title="GPQA",
        cases_route="/benchmarks/gpqa/1/cases",
        grader=ExactChoice(),
        grader_route="/graders/exact-choice/1",
        aggregator=Mean(),
        aggregator_route="/aggregators/mean/1",
    )

    html = bench._repr_html_()

    assert "engine routes" in html
    assert "/benchmarks/gpqa/1/cases" in html


def test_model_and_rubric_cards_collapse_long_prompts() -> None:
    model = sf.Model("gemini/2.5-flash", prompt="Answer thoroughly and completely. " * 8)
    rubric = sf.graders.Rubric(model="gemini/2.5-flash", prompt="Grade every criterion. " * 8)

    assert "<details class='sf-more'" in model._repr_html_()
    assert "<details class='sf-more'" in rubric._repr_html_()
    # a short prompt stays inline (no collapse)
    assert (
        "<details class='sf-more'"
        not in sf.Model("gemini/2.5-flash", prompt="Answer.")._repr_html_()
    )
