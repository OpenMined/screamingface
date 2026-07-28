"""OME-637 follow-up — consistent single-line spacing between benchmark card blocks.

INVARIANT: the grid no longer draws its own bottom border (the following section's top border
is the single separator), and engine routes is a section-styled collapsible so it is separated
from the grader the same way every other block is.
"""

from __future__ import annotations

from screamingface import _card_style
from screamingface.aggregators import Mean
from screamingface.benchmark import Benchmark
from screamingface.graders import ExactChoice


def test_engine_routes_is_a_separated_collapsible_section() -> None:
    bench = Benchmark._from_engine(
        "g@1",
        title="G",
        cases_route="/benchmarks/g/1/cases",
        grader=ExactChoice(),
        grader_route="/graders/exact-choice/1",
        aggregator=Mean(),
        aggregator_route="/aggregators/mean/1",
    )

    html = bench._repr_html_()

    assert "<details class='sf-section'>" in html  # separated like other sections + collapsible
    assert "engine routes" in html


def test_grid_has_no_bottom_border_so_sections_are_the_single_separator() -> None:
    import re

    match = re.search(r"\.sf-card__grid\{([^}]*)\}", _card_style.CARD_STYLE)
    assert match is not None
    assert "border-bottom" not in match.group(1)
