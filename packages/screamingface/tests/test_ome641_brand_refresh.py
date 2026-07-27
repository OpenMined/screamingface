"""OME-641 — SDK notebook widgets refreshed to the current brand.

INVARIANT: gain is gold (not the pre-refresh green); the gold→blue fusion signature is
card-scoped only (the shared style stays gradient-free so the connection panel does too);
titles are EB Garamond serif; no purple anywhere.
"""

from __future__ import annotations

import screamingface as sf
from screamingface import _card_style
from screamingface._display import STYLE

_OLD_GREEN = ("#0f7a3d", "#35d07f")  # pre-refresh gain


def test_shared_style_is_gold_serif_and_loads_brand_fonts() -> None:
    for green in _OLD_GREEN:
        assert green not in STYLE  # green gain retired
    assert "--sf-gain:" in STYLE.replace(" ", "")
    assert "@import" in STYLE  # brand webfonts pulled
    assert "EB Garamond" in STYLE  # serif display stack
    assert "--sf-display:" in STYLE.replace(" ", "")


def test_shared_style_stays_gradient_free_for_the_connection_panel() -> None:
    # The connection panel injects only the shared STYLE; keeping the gradient out of it
    # preserves the "no linear-gradient" contract there.
    assert "linear-gradient" not in STYLE
    assert "purple" not in STYLE.lower()


def test_card_style_defines_gold_blue_fusion_gradient_and_serif_titles() -> None:
    css = _card_style.CARD_STYLE
    assert "--sf-gain-grad:" in css.replace(" ", "")
    assert "linear-gradient" in css
    assert "var(--sf-display)" in css  # serif card titles
    assert "purple" not in css.lower()


def test_fusion_card_has_gradient_accent_and_model_has_solid_accent() -> None:
    fusion = sf.Fusion("t", members=["gemini/2.5-flash"], reducer=sf.reducers.MajorityVote())
    model = sf.Model("gemini/2.5-flash")

    fhtml = fusion._repr_html_()
    mhtml = model._repr_html_()

    assert "sf-card__accent" in fhtml
    assert "sf-gain-grad" in fhtml  # fusion signature uses the gradient
    assert "sf-card__accent" in mhtml
