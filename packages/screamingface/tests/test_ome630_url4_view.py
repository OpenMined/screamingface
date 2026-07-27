"""OME-630 — collapsible, syntax-highlighted url4 recipe view.

FEATURE: the Model/Fusion card recipe becomes a readable, collapsed-by-default structured view.
STORY: as a researcher, I expand the url4 recipe to read each member's route/params/prompt, and
copy the exact recipe with one button.
INVARIANT: display never raises — an unparseable recipe degrades to the raw string; injected
text stays HTML-escaped.
"""

from __future__ import annotations

from html import escape

import screamingface as sf
from screamingface._url4_format import recipe_details_html


def _fusion_url4() -> str:
    a = sf.Model("gemini/2.5-flash", name="a", params={"temperature": 0})
    b = sf.Model("codex/gpt-5.5", name="b")
    return sf.Fusion("trio", members=[a, b], reducer=sf.reducers.MajorityVote()).url4


def test_recipe_is_collapsed_by_default_with_a_copy_button() -> None:
    html = recipe_details_html(_fusion_url4())

    assert "<details class='sf-url4'" in html
    assert " open" not in html  # collapsed by default (no `open` attribute)
    assert "sf-url4__copy" in html
    assert "clipboard" in html  # the copy button wires navigator.clipboard


def test_full_form_keeps_the_recipe_and_carries_the_exact_raw() -> None:
    # The url4 is kept in full form (reflowed in a <pre>), not extracted into fields.
    url4 = _fusion_url4()

    html = recipe_details_html(url4)

    assert "sf-url4__pre" in html  # rendered in a <pre> (MathJax skips pre/code)
    assert "/gemini/2.5-flash" in html
    assert "/codex/gpt-5.5" in html
    assert "temperature" in html
    assert "Answer the question." in html  # the intent text is preserved verbatim
    # the exact original recipe is carried for the copy button (quote-escaped attribute)
    assert f'data-url4="{escape(url4, quote=True)}"' in html


def test_structured_view_escapes_injected_intent() -> None:
    malicious = sf.Model("gemini/2.5-flash", prompt="<script>alert(1)</script>")
    fusion = sf.Fusion("t", members=[malicious], reducer=sf.reducers.MajorityVote())

    html = recipe_details_html(fusion.url4)

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_reflow_of_odd_input_does_not_raise() -> None:
    # Reflow is a pure string transform (no parser), so malformed input never raises — it just
    # reflows oddly and the text is preserved.
    html = recipe_details_html("member_1:broken(")

    assert "<details class='sf-url4'" in html
    assert "member_1:broken(" in html


def test_model_and_fusion_cards_embed_the_collapsible_recipe() -> None:
    model = sf.Model("gemini/2.5-flash")
    fusion = sf.Fusion("t", members=["gemini/2.5-flash"], reducer=sf.reducers.MajorityVote())

    assert "sf-url4" in model._repr_html_()
    assert "sf-url4" in fusion._repr_html_()
