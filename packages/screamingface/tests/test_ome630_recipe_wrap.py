"""OME-630 follow-up — the recipe view wraps long content instead of overflowing.

STORY: a researcher expands a recipe with long routes/structs and it stays inside the card.
INVARIANT: the flex node containers set min-width:0 so long content wraps (flex items default
to min-width:auto, which lets long content push past the card edge).
"""

from __future__ import annotations

import re

from screamingface import _card_display


def test_recipe_node_containers_set_min_width_zero_to_wrap() -> None:
    for selector in ("sf-url4__nodes", "sf-url4__node"):
        match = re.search(rf"\.{selector}\{{([^}}]*)\}}", _card_display._STYLE)
        assert match is not None, f"missing rule for .{selector}"
        assert "min-width:0" in match.group(1), f".{selector} must set min-width:0 to wrap"
