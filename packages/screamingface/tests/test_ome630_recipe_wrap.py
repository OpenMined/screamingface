"""OME-630 follow-up — the recipe view wraps long content instead of overflowing.

STORY: a researcher expands a recipe with long routes/structs and it stays inside the card.
INVARIANT: the recipe <pre> wraps (white-space:pre-wrap + overflow-wrap:anywhere) so long
lines never push past the card edge.
"""

from __future__ import annotations

import re

from screamingface import _card_style


def test_recipe_pre_wraps_long_content() -> None:
    match = re.search(r"\.sf-url4__pre\{([^}]*)\}", _card_style.CARD_STYLE)
    assert match is not None, "missing .sf-url4__pre rule"
    body = match.group(1)
    assert "white-space:pre-wrap" in body
    assert "overflow-wrap:anywhere" in body
